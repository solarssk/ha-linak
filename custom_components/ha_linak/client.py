"""Read-only asynchronous DPG client; no movement or settings writes."""

import asyncio
import logging
from time import monotonic
from collections.abc import Callable, Coroutine
from typing import Any
from dataclasses import dataclass, field

from bleak import BleakClient
from bleak.backends import BleakBackend
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .protocol import (
    DPG_UUID,
    HEIGHT_UUID,
    Capabilities,
    PositionSample,
    ReadCommand,
    ReminderSettings,
    StoredPosition,
    decode_capabilities,
    decode_offset,
    decode_position,
    decode_reminders,
    decode_stored_position,
    read_request,
)


_LOGGER = logging.getLogger(__name__)

REFRESH_TIMEOUT = 60
IO_TIMEOUT = 10
QUERY_TIMEOUT = 8
PAIR_TIMEOUT = 30


class DeskLinkLost(ConnectionError):
    """The current session disconnected during an operation."""


class DeskAuthenticationError(ConnectionError):
    """Bluetooth authentication was rejected or failed."""


class DeskPairingUnsupported(ConnectionError):
    """The selected backend cannot explicitly pair."""


class DeskPairingTimeout(TimeoutError):
    """Bluetooth authentication exceeded its deadline."""


@dataclass
class DeskState:
    position: PositionSample | None = None
    offset_raw: int | None = None
    capabilities: Capabilities | None = None
    memories: list[StoredPosition] = field(default_factory=list)
    reminders: ReminderSettings | None = None

    @property
    def height_cm(self) -> float | None:
        if self.position is None or self.offset_raw is None:
            return None
        return (self.offset_raw + self.position.position_raw) / 100


class DeskClient:
    """One serialized query channel, discarded after any ambiguous failure."""

    def __init__(
        self,
        device: BLEDevice,
        changed: Callable[[], None],
        device_callback: Callable[[], BLEDevice] | None = None,
    ) -> None:
        self.device = device
        self.device_callback = device_callback
        self.stage = "idle"
        self._stage_at = monotonic()
        self.changed = changed
        self.state = DeskState()
        self.client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._operation: asyncio.Task[Any] | None = None
        self._link_lost = False
        self._pending: asyncio.Future[bytes] | None = None
        self._response_type: int | None = None
        self._closing = False
        self._ready = False
        self._generation = 0

    def _set_stage(self, stage: str) -> None:
        now = monotonic()
        _LOGGER.debug(
            "BLE stage %s completed after %.3fs; entering %s",
            self.stage,
            now - self._stage_at,
            stage,
        )
        self.stage = stage
        self._stage_at = now

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected and self._ready

    def _disconnected(self, client: BleakClient) -> None:
        if client is not self.client:
            return
        self._ready = False
        if not self._closing:
            _LOGGER.debug(
                "BLE link lost during %s after %.3fs",
                self.stage,
                monotonic() - self._stage_at,
            )
        self._link_lost = True
        if self._operation is not None:
            self._operation.cancel()
        if not self._closing:
            self.changed()

    def _notification(self, generation: int, data: bytearray) -> None:
        if generation != self._generation:
            return
        pending = self._pending
        if pending is not None and not pending.done() and len(data) >= 2:
            if data[0] == 1 and data[1] == self._response_type:
                pending.set_result(bytes(data))

    def _position(self, generation: int, data: bytearray) -> None:
        if generation != self._generation:
            return
        try:
            self.state.position = decode_position(bytes(data))
        except ValueError:
            self._ready = False
        self.changed()

    async def _io[T](self, operation: Coroutine[Any, Any, T], timeout: float) -> T:
        """Own one operation; distinguish link loss from caller cancellation."""
        if self._link_lost or self.client is None or not self.client.is_connected:
            operation.close()
            raise DeskLinkLost("Desk disconnected")
        task = asyncio.create_task(operation)
        self._operation = task
        try:
            async with asyncio.timeout(timeout):
                result = await task
            if self._link_lost or not self.client.is_connected:
                raise DeskLinkLost("Desk disconnected")
            return result
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if self._link_lost and current is not None and not current.cancelling():
                raise DeskLinkLost("Desk disconnected") from None
            raise
        except BleakError:
            if self._link_lost:
                raise DeskLinkLost("Desk disconnected") from None
            raise
        finally:
            self._operation = None

    async def _pair(self) -> None:
        assert self.client is not None
        self._set_stage("pairing")
        if self.client.backend_id in (
            BleakBackend.CORE_BLUETOOTH,
            BleakBackend.PYTHONISTA_CB,
        ):
            _LOGGER.debug("BLE authentication is managed by CoreBluetooth")
            return
        try:
            await self._io(self.client.pair(), PAIR_TIMEOUT)
        except NotImplementedError:
            raise DeskPairingUnsupported("Backend does not support pairing") from None
        except TimeoutError:
            raise DeskPairingTimeout("Bluetooth pairing timed out") from None
        except BleakError:
            raise DeskAuthenticationError("Bluetooth authentication failed") from None

    async def _query(self, command: ReadCommand, response_type: int) -> bytes:
        assert self.client is not None
        self._pending = asyncio.get_running_loop().create_future()
        self._response_type = response_type
        try:
            return await self._io(self._exchange(command), QUERY_TIMEOUT)
        finally:
            if self._pending is not None:
                self._pending.cancel()
            self._pending = None
            self._response_type = None

    async def _exchange(self, command: ReadCommand) -> bytes:
        assert self.client is not None and self._pending is not None
        await self.client.write_gatt_char(
            DPG_UUID, read_request(command), response=True
        )
        return await self._pending

    async def refresh(self) -> DeskState:
        async with self._lock:
            try:
                async with asyncio.timeout(REFRESH_TIMEOUT):
                    return await self._refresh()
            except BaseException as error:
                # Cleanup owns the transport even if HA cancels the flow again.
                cancelled = isinstance(error, asyncio.CancelledError)
                settled = asyncio.gather(self.disconnect(), return_exceptions=True)
                while not settled.done():
                    try:
                        await asyncio.shield(settled)
                    except asyncio.CancelledError:
                        cancelled = True
                cleanup_error = settled.result()[0]
                if isinstance(cleanup_error, BaseException):
                    _LOGGER.debug(
                        "BLE cleanup failed: %s", type(cleanup_error).__name__
                    )
                if cancelled:
                    raise asyncio.CancelledError from None
                raise

    async def _refresh(self) -> DeskState:
        if self.client is None or not self.client.is_connected or not self._ready:
            await self.disconnect()
            self._closing = False
            self._link_lost = False
            self._generation += 1
            generation = self._generation
            self._set_stage("connection")
            self.client = await establish_connection(
                BleakClientWithServiceCache,
                self.device,
                "LINAK desk",
                disconnected_callback=self._disconnected,
                max_attempts=2,
                ble_device_callback=self.device_callback,
            )
            await self._pair()
            self._set_stage("notify_dpg")
            await self._io(
                self.client.start_notify(
                    DPG_UUID, lambda _, data: self._notification(generation, data)
                ),
                IO_TIMEOUT,
            )
            self._set_stage("notify_height")
            await self._io(
                self.client.start_notify(
                    HEIGHT_UUID, lambda _, data: self._position(generation, data)
                ),
                IO_TIMEOUT,
            )
        self._set_stage("extended_reads")
        state = DeskState()
        state.capabilities = decode_capabilities(
            await self._query(ReadCommand.CAPABILITIES, 2)
        )
        state.offset_raw = decode_offset(await self._query(ReadCommand.OFFSET, 3))
        if state.offset_raw is None:
            raise ValueError("Desk has no valid height offset")
        if state.capabilities.memory_slots > 4:
            raise ValueError("Unsupported number of memory slots")
        for command in list(ReadCommand)[3 : 3 + state.capabilities.memory_slots]:
            state.memories.append(decode_stored_position(await self._query(command, 7)))
        state.reminders = decode_reminders(await self._query(ReadCommand.REMINDERS, 11))
        self._set_stage("position_read")
        state.position = decode_position(
            bytes(await self._io(self.client.read_gatt_char(HEIGHT_UUID), IO_TIMEOUT))
        )
        self.state = state
        self._ready = True
        self._set_stage("ready")
        return state

    async def disconnect(self) -> None:
        self._closing = True
        self._link_lost = True
        if self._operation is not None:
            self._operation.cancel()
        self._ready = False
        self._generation += 1
        client, self.client = self.client, None
        if self._pending is not None and not self._pending.done():
            self._pending.cancel()
        if client is not None and client.is_connected:
            async with asyncio.timeout(IO_TIMEOUT):
                await client.disconnect()
