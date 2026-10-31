"""Serialized DPG readings and explicitly requested, bounded movement."""

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

from .control_settings import ControlSettings
from .motion import (
    BleakMotionTransport,
    CONTROL_UUID,
    TARGET_UUID,
    STOP,
    IO_TIMEOUT as MOTION_IO_TIMEOUT,
    MotionController,
    MotionError,
    _drain_cleanup,
)
from .naming import DEFAULT_NAME, desk_name
from .pairing import BlueZAgentUnavailable, pair_bluez
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
DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"


class DeskLinkLost(ConnectionError):
    """The current session disconnected during an operation."""

    def __init__(self) -> None:
        super().__init__("Desk disconnected")


class DeskAuthenticationError(ConnectionError):
    """Bluetooth authentication was rejected or failed."""


class DeskPairingAgentError(ConnectionError):
    """The local host cannot provide a scoped BlueZ pairing agent."""


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
        self.device_name: str | None = None
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
        self._motion_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self.last_control_result = "not_requested"
        self._motion_stop_sent = False

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
        was_ready = self._ready
        try:
            self.state.position = decode_position(bytes(data))
        except ValueError:
            self._ready = False
        if was_ready:
            self.changed()

    async def _io[T](self, operation: Coroutine[Any, Any, T], budget: float) -> T:
        """Own one operation; distinguish link loss from caller cancellation."""
        if self._link_lost or self.client is None or not self.client.is_connected:
            operation.close()
            raise DeskLinkLost()
        task = asyncio.create_task(operation)
        self._operation = task
        try:
            async with asyncio.timeout(budget):
                result = await task
            if self._link_lost or not self.client.is_connected:
                raise DeskLinkLost()
            return result
        except asyncio.CancelledError:
            self._raise_if_transport_cancelled()
            raise
        except BleakError:
            if self._link_lost:
                raise DeskLinkLost() from None
            raise
        finally:
            self._operation = None

    def _raise_if_transport_cancelled(self) -> None:
        """Translate child I/O cancellation only; caller cancellation must propagate."""
        current = asyncio.current_task()
        if self._link_lost and current is not None and not current.cancelling():
            raise DeskLinkLost() from None

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
            operation = (
                pair_bluez(self.device.address)
                if self.client.backend_id == BleakBackend.BLUEZ_DBUS
                else self.client.pair()
            )
            await self._io(operation, PAIR_TIMEOUT)
        except BlueZAgentUnavailable:
            raise DeskPairingAgentError(
                "Local Bluetooth pairing agent unavailable"
            ) from None
        except NotImplementedError:
            raise DeskPairingUnsupported("Backend does not support pairing") from None
        except TimeoutError:
            raise DeskPairingTimeout("Bluetooth pairing timed out") from None
        except BleakError:
            raise DeskAuthenticationError("Bluetooth authentication failed") from None

    async def _read_device_name(self) -> None:
        """Read optional GAP metadata only when cached naming is a fallback."""
        assert self.client is not None
        cached = desk_name(self.device.address, self.device.name)
        self.device_name = cached if cached != DEFAULT_NAME else None
        if self.device_name is not None:
            return
        try:
            characteristic = self.client.services.get_characteristic(DEVICE_NAME_UUID)
            if characteristic is None or "read" not in characteristic.properties:
                return
            self._set_stage("device_name")
            raw = await self._io(
                self.client.read_gatt_char(DEVICE_NAME_UUID), IO_TIMEOUT
            )
        except BleakError:
            # Missing/denied metadata is optional. Link loss and timeout still
            # invalidate the session through _io/refresh, rather than being hidden.
            _LOGGER.debug("Optional Bluetooth device name could not be read")
            return
        try:
            name = bytes(raw).decode("utf-8").strip("\x00 \t\r\n")
        except UnicodeDecodeError:
            return
        if name and name.isprintable():
            resolved = desk_name(self.device.address, name)
            self.device_name = resolved if resolved != DEFAULT_NAME else None

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
        if self.control_busy:
            return self.state
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
                        if settled.done():
                            raise
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
            await self._read_device_name()
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

    @property
    def control_busy(self) -> bool:
        return self._motion_task is not None or (
            self._stop_task is not None and not self._stop_task.done()
        )

    def _check_control_properties(self, target: bool = False) -> None:
        if not self.connected:
            raise MotionError("An existing ready connection is required")
        assert self.client is not None
        required = [(CONTROL_UUID, "write-without-response")]
        if target:
            required += [(TARGET_UUID, "write-without-response"), (HEIGHT_UUID, "read")]
        for uuid, operation in required:
            characteristic = self.client.services.get_characteristic(uuid)
            if characteristic is None or operation not in characteristic.properties:
                raise MotionError("The required Bluetooth operation is unavailable")

    async def move_to_cm(self, height_cm: float, settings: ControlSettings) -> None:
        await self._start_move(height_cm, settings)

    async def move_to_memory(self, index: int, settings: ControlSettings) -> None:
        if type(index) is not int or not 0 <= index < len(self.state.memories):
            raise MotionError("Stored position is unavailable")
        await self._start_move(None, settings, index)

    async def _start_move(
        self,
        height_cm: float | None,
        settings: ControlSettings,
        memory_index: int | None = None,
    ) -> None:
        if self.control_busy or self._lock.locked():
            raise MotionError("The desk is busy; commands are not queued")
        self._check_control_properties(target=True)
        # Reserve before the first await; a competing action cannot queue a move.
        task = self._motion_task = asyncio.create_task(
            self._move(height_cm, settings, memory_index)
        )
        self.last_control_result = "moving"
        self._motion_stop_sent = False
        try:
            await task
            self.last_control_result = "completed"
        except asyncio.CancelledError:
            self.last_control_result = "interrupted"
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            raise MotionError("Movement was interrupted by Stop") from None
        except Exception:
            self.last_control_result = "failed"
            raise
        finally:
            settled = asyncio.gather(task, return_exceptions=True)
            try:
                await _drain_cleanup(settled)
            finally:
                self._motion_task = None
                self.changed()

    async def _move(
        self,
        height_cm: float | None,
        settings: ControlSettings,
        memory_index: int | None,
    ) -> None:
        async with self._lock:
            try:
                self._set_stage("movement_prepare")
                # Re-read the conversion reference under exclusive session ownership.
                offset = decode_offset(await self._query(ReadCommand.OFFSET, 3))
                if offset is None:
                    raise ValueError("No valid height reference")
                limits = settings.limits(offset)
                if memory_index is not None:
                    command = ReadCommand(0x89 + memory_index)
                    memory = decode_stored_position(await self._query(command, 7))
                    self.state.memories[memory_index] = memory
                    if memory.position_raw is None:
                        raise MotionError("Stored position is empty")
                    height_cm = (memory.position_raw + offset) / 100
                assert height_cm is not None
                limits.target(height_cm, offset)
                self.state.offset_raw = offset
                assert self.client is not None
                transport = _LiveMotionTransport(self)
                controller = MotionController(transport, limits, offset)
                self._set_stage("movement")
                await controller.move_to_cm(height_cm)
                self._set_stage("ready")
            except BaseException:
                # Stop cleanup in the controller settles before this discards the link.
                cleanup = asyncio.gather(
                    self._disconnect_link(), return_exceptions=True
                )
                await _drain_cleanup(cleanup)
                raise

    async def stop(self) -> None:
        if self._stop_task is None or self._stop_task.done():
            self._stop_task = asyncio.create_task(self._stop_control())
        settled = asyncio.gather(self._stop_task, return_exceptions=True)
        try:
            await asyncio.shield(settled)
        except asyncio.CancelledError:
            await _drain_cleanup(settled)
            raise
        result = settled.result()[0]
        if isinstance(result, BaseException):
            raise result

    async def _stop_control(self) -> None:
        task = self._motion_task
        if task is not None and not task.done():
            task.cancel()
            settled = asyncio.gather(task, return_exceptions=True)
            await _drain_cleanup(settled)
            # Cancellation discards the movement session after its final Stop.
            # Its cleanup failure must remain visible to this Stop caller too.
            result = settled.result()[0]
            if isinstance(result, Exception):
                self.last_control_result = "stop_failed"
                raise MotionError(
                    "Movement cleanup failed; check physical Stop"
                ) from result
            if not self.connected:
                if not self._motion_stop_sent:
                    self.last_control_result = "stop_failed"
                    raise MotionError("Stop was not delivered; check physical Stop")
                self.last_control_result = "stop_sent"
                return
        try:
            self._check_control_properties()
            assert self.client is not None
            self._set_stage("stop")
            async with asyncio.timeout(MOTION_IO_TIMEOUT):
                await self.client.write_gatt_char(CONTROL_UUID, STOP, response=False)
            self.last_control_result = "stop_sent"
            self._set_stage("ready")
        except Exception as err:
            self.last_control_result = "stop_failed"
            await self._disconnect_link()
            raise MotionError("Stop failed; check physical Stop") from err
        finally:
            self.changed()

    async def disconnect(self) -> None:
        try:
            if self.control_busy:
                await self.stop()
        finally:
            await self._disconnect_link()

    async def _disconnect_link(self) -> None:
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


class _LiveMotionTransport(BleakMotionTransport):
    """Reuse the connected HA client and publish only measured position values."""

    def __init__(self, desk: DeskClient) -> None:
        assert desk.client is not None
        super().__init__(desk.client)
        self.desk = desk

    async def read_position(self) -> PositionSample:
        sample = await super().read_position()
        self.desk.state.position = sample
        self.desk.changed()
        return sample

    async def write_control(self, payload: bytes) -> None:
        await super().write_control(payload)
        if payload == STOP:
            self.desk._motion_stop_sent = True

    async def disconnect(self) -> None:
        await self.desk._disconnect_link()
