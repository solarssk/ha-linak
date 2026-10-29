"""Read-only asynchronous DPG client; no movement or settings writes."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from bleak import BleakClient
from bleak.backends.device import BLEDevice
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

    def __init__(self, device: BLEDevice, changed: Callable[[], None]) -> None:
        self.device = device
        self.changed = changed
        self.state = DeskState()
        self.client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._pending: asyncio.Future[bytes] | None = None
        self._response_type: int | None = None
        self._closing = False
        self._ready = False
        self._generation = 0

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected and self._ready

    def _disconnected(self, client: BleakClient) -> None:
        if client is not self.client:
            return
        self._ready = False
        if self._pending is not None and not self._pending.done():
            self._pending.set_exception(ConnectionError("Desk disconnected"))
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

    async def _query(self, command: ReadCommand, response_type: int) -> bytes:
        assert self.client is not None
        self._pending = asyncio.get_running_loop().create_future()
        self._response_type = response_type
        try:
            async with asyncio.timeout(8):
                await self.client.write_gatt_char(
                    DPG_UUID, read_request(command), response=True
                )
                return await self._pending
        finally:
            if self._pending is not None:
                self._pending.cancel()
            self._pending = None
            self._response_type = None

    async def refresh(self) -> DeskState:
        async with self._lock:
            try:
                if (
                    self.client is None
                    or not self.client.is_connected
                    or not self._ready
                ):
                    await self.disconnect()
                    self._closing = False
                    self._generation += 1
                    generation = self._generation
                    self.client = await establish_connection(
                        BleakClientWithServiceCache,
                        self.device,
                        "LINAK desk",
                        disconnected_callback=self._disconnected,
                        max_attempts=2,
                    )
                    await self.client.start_notify(
                        DPG_UUID, lambda _, data: self._notification(generation, data)
                    )
                    await self.client.start_notify(
                        HEIGHT_UUID, lambda _, data: self._position(generation, data)
                    )
                state = DeskState()
                state.capabilities = decode_capabilities(
                    await self._query(ReadCommand.CAPABILITIES, 2)
                )
                state.offset_raw = decode_offset(
                    await self._query(ReadCommand.OFFSET, 3)
                )
                if state.offset_raw is None:
                    raise ValueError("Desk has no valid height offset")
                if state.capabilities.memory_slots > 4:
                    raise ValueError("Unsupported number of memory slots")
                for command in list(ReadCommand)[
                    3 : 3 + state.capabilities.memory_slots
                ]:
                    state.memories.append(
                        decode_stored_position(await self._query(command, 7))
                    )
                state.reminders = decode_reminders(
                    await self._query(ReadCommand.REMINDERS, 11)
                )
                state.position = decode_position(
                    bytes(await self.client.read_gatt_char(HEIGHT_UUID))
                )
                self.state = state
                self._ready = True
                return state
            except BaseException:
                await self.disconnect()
                raise

    async def disconnect(self) -> None:
        self._closing = True
        self._ready = False
        self._generation += 1
        client, self.client = self.client, None
        if self._pending is not None and not self._pending.done():
            self._pending.cancel()
        if client is not None and client.is_connected:
            async with asyncio.timeout(10):
                await client.disconnect()
