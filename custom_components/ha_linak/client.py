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

from .calibration import (
    HeightCalibration,
    SettingRejected,
    CalibrationSnapshotChanged,
    PREVIEW_TOLERANCE_RAW,
)
from .protocol import activation_request
from .device_profile import DeviceIdentity, MODEL_UUID, FIRMWARE_UUID
from .control_settings import ControlSettings
from .motion import (
    BleakMotionTransport,
    CONTROL_UUID,
    TARGET_UUID,
    STOP,
    IO_TIMEOUT as MOTION_IO_TIMEOUT,
    MotionController,
    MotionError,
    MotionFailure,
    MotionStopped,
    _drain_cleanup,
)
from .naming import DEFAULT_NAME, desk_name
from .operation import OPERATION_RESET_DELAY, OperationTracker, Phase, Reason
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
SETTINGS_RETRY_INTERVAL = 300
PAIR_TIMEOUT = 30
DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"
BLUETOOTH_BACKENDS = tuple(
    sorted(
        {backend.value for backend in BleakBackend}
        | {"bleak_esphome", "bluez_mgmt", "other"}
    )
)


def backend_category(client: BleakClient) -> str:
    """Expose a backend category without device names or adapter identifiers."""
    backend = getattr(client, "backend_id", None)
    if isinstance(backend, BleakBackend):
        backend = backend.value
    if backend in BLUETOOTH_BACKENDS:
        return backend
    # Some HA wrappers expose the backend class's metaclass name ("type").
    # Fall back only to known implementation modules, never an adapter identity.
    module = type(getattr(client, "_backend", None)).__module__
    return {
        "bleak_esphome.backend.client": "bleak_esphome",
        "bleak.backends.bluezdbus.client": "bluez_dbus",
    }.get(module, "other")


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


class OptionalReadTimeout(TimeoutError):
    """An optional query expired; its session must be discarded."""

    def __init__(self, group: str) -> None:
        super().__init__(f"Optional {group} read timed out")
        self.group = group


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


@dataclass
class SettingsHealth:
    """Read validity for one optional group; ages use a monotonic clock."""

    valid: bool = False
    last_success: float | None = None
    error: str | None = None
    retry_after: float = 0


class DeskClient:
    """One serialized query channel, discarded after any ambiguous failure."""

    def __init__(
        self,
        device: BLEDevice,
        changed: Callable[[], None],
        device_callback: Callable[[], BLEDevice] | None = None,
    ) -> None:
        self.identity = DeviceIdentity()
        self.protocol_validated = False
        self.device_name: str | None = None
        self.device = device
        self.device_callback = device_callback
        self.stage = "idle"
        self._stage_at = monotonic()
        self.changed = changed
        self.state = DeskState()
        self.settings_health = {
            "memories": SettingsHealth(),
            "reminders": SettingsHealth(),
        }
        self.client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._operation: asyncio.Task[Any] | None = None
        self._link_lost = False
        self._pending: asyncio.Future[bytes] | None = None
        self._response_type: int | None = None
        self._closing = False
        self._ready = False
        self._generation = 0
        self._calibration_task: asyncio.Task[Any] | None = None
        self._motion_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self.last_control_result = "not_requested"
        self._motion_stop_sent = False
        self._stop_requested = False
        self._released = False
        self._operation_reset: asyncio.TimerHandle | None = None
        self._operation_resets_closed = False
        self.operation = OperationTracker(self._operation_changed)

    @property
    def released(self) -> bool:
        """The owner deliberately released the desk; nothing may reconnect it."""
        return self._released

    async def release(self) -> None:
        """Stop any movement, drop the link and refuse to reconnect until resumed."""
        self._released = True
        await self.disconnect()

    def resume(self) -> None:
        self._released = False

    def _require_unreleased(self) -> None:
        if self._released:
            raise ConnectionError("The connection was released by the owner")

    def _operation_changed(self) -> None:
        self._schedule_operation_reset()
        self.changed()

    def _schedule_operation_reset(self) -> None:
        """Return a settled result to idle after a pause; a new request cancels it."""
        self.cancel_operation_reset()
        if self._operation_resets_closed or not self.operation.status.settled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._operation_reset = loop.call_later(
            OPERATION_RESET_DELAY, self.operation.reset
        )

    def cancel_operation_reset(self) -> None:
        if self._operation_reset is not None:
            self._operation_reset.cancel()
            self._operation_reset = None

    def close_operation_resets(self) -> None:
        """No timer may outlive this client, even one a closing movement settles."""
        self._operation_resets_closed = True
        self.cancel_operation_reset()

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
        for health in self.settings_health.values():
            health.valid = False
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
            self.operation.link_lost()
            self.changed()

    def _notification(self, generation: int, data: bytearray) -> None:
        if generation != self._generation:
            return
        pending = self._pending
        if pending is not None and not pending.done() and len(data) >= 2:
            if self._response_type == 0 and len(data) == 2 and data[0] != 1:
                pending.set_exception(SettingRejected(data[0]))
            elif data[0] == 1 and data[1] == self._response_type:
                pending.set_result(bytes(data))

    def _position(self, generation: int, data: bytearray) -> None:
        if generation != self._generation:
            return
        was_ready = self._ready
        previous = self.state.position
        try:
            self.state.position = decode_position(bytes(data))
        except ValueError:
            self._ready = False
        if (
            was_ready
            and self._calibration_task is None
            and (not self._ready or self.state.position != previous)
        ):
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

    async def _read_identity(self) -> None:
        """Read advertised DIS fields once per session, never during polling."""
        assert self.client is not None
        self.identity = DeviceIdentity()
        self.protocol_validated = False
        fields: list[bytes] = []
        self._set_stage("device_identity")
        for uuid in (MODEL_UUID, FIRMWARE_UUID):
            raw = b""
            try:
                characteristic = self.client.services.get_characteristic(uuid)
                if characteristic is not None and "read" in characteristic.properties:
                    raw = bytes(
                        await self._io(self.client.read_gatt_char(uuid), IO_TIMEOUT)
                    )
            except BleakError:
                # Absent/ambiguous/denied metadata is optional. Timeout and link
                # loss still discard this session through _io and refresh.
                _LOGGER.debug("Optional device information could not be read")
            fields.append(raw)
            if uuid == MODEL_UUID:
                self.identity = DeviceIdentity.from_metadata(raw, b"")
                self.identity.require_driver()
        self.identity = DeviceIdentity.from_metadata(*fields)

    async def _query(self, command: ReadCommand, response_type: int) -> bytes:
        assert self.client is not None
        self._pending = asyncio.get_running_loop().create_future()
        self._response_type = response_type
        try:
            return await self._io(self._exchange(command), QUERY_TIMEOUT)
        except TimeoutError:
            _LOGGER.debug("DPG read timed out: command=%s", command.name)
            raise
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

    async def refresh(
        self, *, allow_partial_settings: bool = False, settings_interval: float = 0
    ) -> DeskState:
        self._require_unreleased()
        if self.control_busy:
            return self.state
        async with self._lock:
            try:
                async with asyncio.timeout(REFRESH_TIMEOUT):
                    return await self._refresh_with_recovery(
                        allow_partial_settings, settings_interval
                    )
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

    async def _refresh_with_recovery(
        self, allow_partial_settings: bool, settings_interval: float
    ) -> DeskState:
        excluded: set[str] = set()
        while True:
            try:
                return await self._refresh(
                    allow_partial_settings=allow_partial_settings,
                    settings_interval=settings_interval,
                    excluded=excluded,
                )
            except OptionalReadTimeout as error:
                if not allow_partial_settings or error.group in excluded:
                    raise
                excluded.add(error.group)
                await self._disconnect_link()
                health = self.settings_health[error.group]
                health.error = "timeout"
                health.retry_after = monotonic() + SETTINGS_RETRY_INTERVAL
                _LOGGER.warning(
                    "LINAK %s read timed out; reconnecting with group unavailable",
                    error.group,
                )

    async def _connect(self) -> None:
        """Establish and subscribe a fresh session before any DPG reads."""
        await self.disconnect()
        self._closing = False
        self._link_lost = False
        self._generation += 1
        self.protocol_validated = False
        generation = self._generation
        self._set_stage("connection")
        self.client = await establish_connection(
            BleakClientWithServiceCache,
            self.device,
            "LINAK desk",
            disconnected_callback=self._disconnected,
            # HA reevaluates the adapter on each connector retry. A local
            # two-attempt cap can end setup before a healthy path is chosen.
            # Keep the connector policy inside refresh's overall deadline.
            ble_device_callback=self.device_callback,
        )
        _LOGGER.debug(
            "BLE session connected: backend=%s", backend_category(self.client)
        )
        await self._pair()
        await self._read_device_name()
        await self._read_identity()
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

    async def _refresh(
        self,
        *,
        allow_partial_settings: bool = False,
        settings_interval: float = 0,
        required_only: bool = False,
        excluded: set[str] | None = None,
    ) -> DeskState:
        if self.client is None or not self.client.is_connected or not self._ready:
            await self._connect()
        assert self.client is not None
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
        reference_changed = (
            state.capabilities != self.state.capabilities
            or state.offset_raw != self.state.offset_raw
        )
        force_settings = not allow_partial_settings or reference_changed
        excluded = excluded or set()
        memories_due = self._optional_due(
            "memories",
            settings_interval,
            force_settings,
            allow_partial_settings,
            required_only,
            excluded,
        )
        reminders_due = self._optional_due(
            "reminders",
            settings_interval,
            force_settings,
            allow_partial_settings,
            required_only,
            excluded,
        )
        if required_only and reference_changed:
            self._invalidate_settings()
        memories_valid, reminders_valid = await self._refresh_optional(
            state, memories_due, reminders_due, allow_partial_settings
        )
        self._set_stage("position_read")
        state.position = decode_position(
            bytes(await self._io(self.client.read_gatt_char(HEIGHT_UUID), IO_TIMEOUT))
        )
        if memories_due:
            self._record_settings("memories", memories_valid)
        if reminders_due:
            self._record_settings("reminders", reminders_valid)
        self.state = state
        self.protocol_validated = True
        self._ready = True
        self._set_stage("ready")
        return state

    async def _refresh_optional(
        self,
        state: DeskState,
        memories_due: bool,
        reminders_due: bool,
        allow_partial_settings: bool,
    ) -> tuple[bool, bool]:
        """Build optional values without publishing group health prematurely."""
        assert state.capabilities is not None
        memories = None
        reminders = None
        state.memories = list(self.state.memories[: state.capabilities.memory_slots])
        state.reminders = self.state.reminders
        if memories_due:
            memories = await self._read_memories(
                state.capabilities, allow_partial_settings
            )
            if memories is not None:
                state.memories = memories
        if reminders_due:
            reminders = self._decode_optional(
                decode_reminders,
                await self._optional_query(ReadCommand.REMINDERS, 11, "reminders"),
                allow_partial_settings,
            )
            if reminders is not None:
                state.reminders = reminders
        return memories is not None, reminders is not None

    @staticmethod
    def _decode_optional[T](
        decoder: Callable[[bytes], T], payload: bytes, allow_partial: bool
    ) -> T | None:
        # Only a completed, matching reply reaches this parser. Never catch a
        # timeout, cancellation or transport error as an optional-field failure.
        try:
            return decoder(payload)
        except ValueError:
            if not allow_partial:
                raise
            return None

    async def _read_memories(
        self, capabilities: Capabilities, allow_partial: bool
    ) -> list[StoredPosition] | None:
        memories = []
        valid = True
        for index in range(capabilities.memory_slots):
            if index:
                # Memory replies have no slot ID. A different reply type is an
                # ordered barrier against the observed duplicate signal burst.
                barrier = decode_capabilities(
                    await self._query(ReadCommand.CAPABILITIES, 2)
                )
                if barrier != capabilities:
                    raise ValueError("Desk capabilities changed during memory reads")
            payload = await self._optional_query(
                ReadCommand(0x89 + index), 7, "memories"
            )
            memory = self._decode_optional(
                decode_stored_position, payload, allow_partial
            )
            if memory is None:
                valid = False
            else:
                memories.append(memory)
        return memories if valid else None

    async def _optional_query(
        self, command: ReadCommand, response_type: int, group: str
    ) -> bytes:
        try:
            return await self._query(command, response_type)
        except TimeoutError as error:
            raise OptionalReadTimeout(group) from error

    def _optional_due(
        self,
        group: str,
        interval: float,
        force: bool,
        allow_partial: bool,
        required_only: bool,
        excluded: set[str],
    ) -> bool:
        if required_only or group in excluded:
            return False
        if allow_partial and monotonic() < self.settings_health[group].retry_after:
            return False
        return force or self._settings_due(group, interval)

    def _settings_due(self, group: str, interval: float) -> bool:
        health = self.settings_health[group]
        return (
            not health.valid
            or health.last_success is None
            or monotonic() - health.last_success >= interval
        )

    def _record_settings(self, group: str, valid: bool) -> None:
        health = self.settings_health[group]
        if valid:
            health.last_success = monotonic()
            health.retry_after = 0
        elif health.error is None:
            _LOGGER.warning("LINAK %s response invalid; group unavailable", group)
        health.valid = valid
        health.error = None if valid else "invalid_response"

    def settings_diagnostics(self) -> dict[str, dict[str, object]]:
        now = monotonic()
        return {
            group: {
                "valid": health.valid,
                "age_seconds": round(max(0.0, now - health.last_success), 1)
                if health.last_success is not None
                else None,
                "error": health.error,
            }
            for group, health in self.settings_health.items()
        }

    @property
    def control_busy(self) -> bool:
        return (
            self._calibration_task is not None
            or self._motion_task is not None
            or (self._stop_task is not None and not self._stop_task.done())
        )

    def _check_control_properties(self, target: bool = False) -> BleakClient:
        client = self.client
        if client is None or not self.connected:
            raise MotionError("An existing ready connection is required")
        required = [(CONTROL_UUID, "write-without-response")]
        if target:
            required += [(TARGET_UUID, "write-without-response"), (HEIGHT_UUID, "read")]
        for uuid, operation in required:
            characteristic = client.services.get_characteristic(uuid)
            if characteristic is None or operation not in characteristic.properties:
                raise MotionError("The required Bluetooth operation is unavailable")
        return client

    async def _write_setting(self, payload: bytes) -> None:
        """Send one allowlisted setting and require the application ACK, no retry."""
        if not (
            (payload[:4] == b"\x7f\x81\x80\x01" and len(payload) == 6)
            or (payload[:4] == b"\x7f\x86\x80\x01" and len(payload) == 20)
        ):
            raise ValueError("Unsupported setting request")
        await self._query(ReadCommand.CAPABILITIES, 2)
        self._pending = asyncio.get_running_loop().create_future()
        self._response_type = 0
        try:
            await self._io(self._exchange_setting(payload), QUERY_TIMEOUT)
        finally:
            self._pending.cancel()
            self._pending = None
            self._response_type = None

    async def _exchange_setting(self, payload: bytes) -> bytes:
        assert self.client is not None and self._pending is not None
        await self.client.write_gatt_char(DPG_UUID, payload, response=True)
        return await self._pending

    async def _activate_client(self, phase: str) -> None:
        """Prepare the existing identity only for explicit foreground control."""
        self._set_stage(f"{phase}_activation_check")
        identity = await self._query(ReadCommand.USER_ID, 17)
        payload = activation_request(identity)
        if payload is None:
            return
        self._set_stage(f"{phase}_activation_write")
        await self._write_setting(payload)
        verified = await self._query(ReadCommand.USER_ID, 17)
        if verified != identity[:2] + b"\x01" + identity[3:]:
            raise ValueError("Client activation was not verified")

    def _calibration_transport(self) -> BleakClient:
        """Require the read/write operations used by confirmed preparation."""
        client = self.client
        if client is None:
            raise MotionError("Calibration requires a connection")
        for uuid, operation in ((DPG_UUID, "write"), (HEIGHT_UUID, "read")):
            characteristic = client.services.get_characteristic(uuid)
            if characteristic is None or operation not in characteristic.properties:
                raise MotionError("Calibration Bluetooth operation is unavailable")
        return client

    async def calibrate_height(
        self, proposal: HeightCalibration, *, activate_client: bool = False
    ) -> DeskState:
        """Apply one explicitly confirmed offset, verify it, never move or retry."""
        if self.control_busy or self._lock.locked() or not self.connected:
            raise MotionError("Calibration requires an idle ready connection")
        self._calibration_task = asyncio.current_task()
        try:
            async with self._lock, asyncio.timeout(REFRESH_TIMEOUT):
                self._set_stage("calibration_check")
                client = self._calibration_transport()
                first = decode_position(
                    bytes(
                        await self._io(client.read_gatt_char(HEIGHT_UUID), IO_TIMEOUT)
                    )
                )
                offset = decode_offset(await self._query(ReadCommand.OFFSET, 3))
                second = decode_position(
                    bytes(
                        await self._io(client.read_gatt_char(HEIGHT_UUID), IO_TIMEOUT)
                    )
                )
                if (
                    first != second
                    or first.speed_raw != 0
                    or abs(first.position_raw - proposal.position_raw)
                    > PREVIEW_TOLERANCE_RAW
                    or offset != proposal.old_offset_raw
                ):
                    raise CalibrationSnapshotChanged(
                        "Desk position or reference changed; measure again"
                    )
                if proposal.changed or activate_client:
                    await self._activate_client("calibration")
                    fresh_offset = decode_offset(
                        await self._query(ReadCommand.OFFSET, 3)
                    )
                    fresh_position = decode_position(
                        bytes(
                            await self._io(
                                client.read_gatt_char(HEIGHT_UUID), IO_TIMEOUT
                            )
                        )
                    )
                    if (
                        fresh_position != first
                        or fresh_offset != proposal.old_offset_raw
                    ):
                        raise CalibrationSnapshotChanged(
                            "Position or reference changed during activation"
                        )
                if proposal.changed:
                    self._set_stage("calibration_write")
                    await self._write_setting(proposal.write_request())
                # Required readback cannot be blocked by unavailable settings.
                # A capabilities reply separates the setter from offset verification.
                state = await self._refresh(required_only=True)
                if (
                    state.offset_raw != proposal.new_offset_raw
                    or state.position != first
                ):
                    raise ValueError(
                        "Calibration readback did not match; do not retry automatically"
                    )
                self.changed()
                return state
        except BaseException:
            settled = asyncio.gather(self._disconnect_link(), return_exceptions=True)
            await _drain_cleanup(settled)
            raise
        finally:
            self._calibration_task = None
            self.changed()

    async def move_to_cm(self, height_cm: float, settings: ControlSettings) -> None:
        await self._start_move(height_cm, settings)

    async def move_to_memory(self, index: int, settings: ControlSettings) -> None:
        if (
            not self.settings_health["memories"].valid
            or type(index) is not int
            or not 0 <= index < len(self.state.memories)
        ):
            raise MotionError("Stored position is unavailable")
        await self._start_move(None, settings, index)

    async def _start_move(
        self,
        height_cm: float | None,
        settings: ControlSettings,
        memory_index: int | None = None,
    ) -> None:
        if self.control_busy or self._lock.locked():
            raise MotionError(
                "The desk is busy; commands are not queued", MotionFailure.BUSY
            )
        self._check_control_properties(target=True)
        # Reserve before the first await; a competing action cannot queue a move.
        task = self._motion_task = asyncio.create_task(
            self._move(height_cm, settings, memory_index)
        )
        self.last_control_result = "moving"
        self._motion_stop_sent = False
        self._stop_requested = False
        self.operation.begin(height_cm)
        failure: BaseException | None = None
        stop_error: BaseException | None = None
        try:
            await task
            self.last_control_result = "completed"
        except asyncio.CancelledError as cancelled:
            self.last_control_result = "interrupted"
            failure = cancelled
            # A Stop that cancelled a move before it started writes its own Stop;
            # its delivery decides whether this was an interruption.
            stop_error = await self._stop_outcome()
            try:
                self._raise_if_child_interrupted()
            except MotionError as translated:
                failure = translated
                raise
            raise
        except Exception as error:
            self.last_control_result = "failed"
            failure = error
            raise
        finally:
            settled = asyncio.gather(task, return_exceptions=True)
            try:
                await _drain_cleanup(settled)
            finally:
                if stop_error is None:
                    stop_error = await self._stop_outcome()
                self._motion_task = None
                self._settle_operation(failure, stop_error)
                self.changed()

    async def _stop_outcome(self) -> BaseException | None:
        """Wait for a Stop requested during this operation; return its failure."""
        stop = self._stop_task
        if not self._stop_requested or stop is None:
            return None
        settled = asyncio.gather(stop, return_exceptions=True)
        await _drain_cleanup(settled)
        result = settled.result()[0]
        return result if isinstance(result, BaseException) else None

    def _raise_if_child_interrupted(self) -> None:
        """Translate only worker cancellation; preserve HA caller cancellation."""
        current = asyncio.current_task()
        if current is not None and not current.cancelling():
            if self._stop_requested and self._motion_stop_sent:
                raise MotionStopped("Movement was stopped") from None
            raise MotionError(
                "Movement was interrupted without confirmed Stop"
            ) from None

    def _settle_operation(
        self, error: BaseException | None, stop_error: BaseException | None = None
    ) -> None:
        """Publish the final outcome once the movement's own cleanup has settled."""
        if stop_error is not None:
            self.operation.fail(Reason.STOP_FAILED)
        elif error is None:
            self.operation.complete()
        elif isinstance(error, MotionStopped):
            self.operation.interrupt()
        elif isinstance(error, asyncio.CancelledError):
            # The caller went away. Cancellation before any target was sent has
            # nothing to stop; otherwise only a delivered final Stop is clean.
            if self._motion_stop_sent or self.operation.origin is Phase.PREPARING:
                self.operation.interrupt()
            else:
                self.operation.fail(Reason.STOP_FAILED)
        else:
            self.operation.fail(self._failure_reason(error))

    def _failure_reason(self, error: BaseException) -> Reason:
        """Name what the software detected; never expose a raw exception message."""
        if isinstance(error, DeskLinkLost):
            return Reason.LINK_LOST
        if self._stop_requested and not self._motion_stop_sent:
            return Reason.STOP_FAILED
        if isinstance(error, TimeoutError):
            return Reason.TIMEOUT
        if isinstance(error, MotionError) and error.reason is not MotionFailure.UNKNOWN:
            try:
                return Reason(error.reason.value)
            except ValueError:
                return Reason.UNKNOWN
        if self.operation.origin is Phase.PREPARING:
            return Reason.PREPARATION_FAILED
        return Reason.UNKNOWN

    async def _move(
        self,
        height_cm: float | None,
        settings: ControlSettings,
        memory_index: int | None,
    ) -> None:
        controller: MotionController | None = None
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
                    self.operation.request(height_cm)
                assert height_cm is not None
                limits.target(height_cm, offset)
                self.state.offset_raw = offset
                await self._activate_client("movement")
                assert self.client is not None
                transport = _LiveMotionTransport(self)
                controller = MotionController(
                    transport,
                    limits,
                    offset,
                    on_start=self.operation.moving,
                    on_cleanup=self.operation.stopping,
                )
                self._set_stage("movement")
                await controller.move_to_cm(height_cm)
                self._set_stage("ready")
            except BaseException as error:
                if self._can_retain_after_stop(error, controller):
                    # Explicit Stop completed both channel writes. Its cancelled
                    # movement can release ownership without dropping a sound link.
                    self._set_stage("ready")
                    raise
                # A controller settles its own Stop. Preparation has no controller,
                # so an explicit Stop still needs one bounded write before release.
                cleanup = asyncio.gather(
                    self._finish_failed_move(controller is None), return_exceptions=True
                )
                await _drain_cleanup(cleanup)
                result = cleanup.result()[0]
                if isinstance(result, BaseException):
                    raise result
                raise

    def _can_retain_after_stop(
        self, error: BaseException, controller: MotionController | None
    ) -> bool:
        if not isinstance(error, asyncio.CancelledError) or controller is None:
            return False
        stop_pending = self._stop_task is not None and not self._stop_task.done()
        return stop_pending and self._motion_stop_sent and self.connected

    async def _finish_failed_move(self, before_motion: bool) -> None:
        try:
            if (
                before_motion
                and not self._motion_stop_sent
                and self._stop_task is not None
                and not self._stop_task.done()
            ):
                client = self._check_control_properties()
                self._set_stage("stop")
                async with asyncio.timeout(MOTION_IO_TIMEOUT):
                    await BleakMotionTransport(client).write_control(STOP)
                self._motion_stop_sent = True
        finally:
            await self._disconnect_link()

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
        # The request owns its operation until it settles, even after its task ends.
        during_operation = task is not None
        if task is not None:
            self._stop_requested = True
        if task is not None and not task.done():
            self.operation.stopping()
            task.cancel()
            settled = asyncio.gather(task, return_exceptions=True)
            await _drain_cleanup(settled)
            # Await the movement's final two-channel Stop before releasing ownership.
            # Cleanup failures must remain visible to this Stop caller too.
            result = settled.result()[0]
            if isinstance(result, Exception):
                self.last_control_result = "stop_failed"
                raise MotionError(
                    "Movement cleanup failed; check physical Stop"
                ) from result
            if self._motion_stop_sent:
                self.last_control_result = "stop_sent"
                return
            if not self.connected:
                self.last_control_result = "stop_failed"
                raise MotionError("Stop was not delivered; check physical Stop")
        try:
            client = self._check_control_properties()
            self._set_stage("stop")
            async with asyncio.timeout(MOTION_IO_TIMEOUT):
                await BleakMotionTransport(client).write_control(STOP)
            self.last_control_result = "stop_sent"
            self._motion_stop_sent = True
            self._set_stage("ready")
        except Exception as err:
            self.last_control_result = "stop_failed"
            if not during_operation:
                # A running request settles its own operation; a lone Stop records itself.
                self.operation.stop_failed_while_idle()
            await self._disconnect_link()
            raise MotionError("Stop failed; check physical Stop") from err
        finally:
            self.changed()

    async def disconnect(self) -> None:
        calibration = self._calibration_task
        if calibration is not None and calibration is not asyncio.current_task():
            calibration.cancel()
            await _drain_cleanup(asyncio.gather(calibration, return_exceptions=True))
        try:
            if self.control_busy:
                await self.stop()
        finally:
            await self._disconnect_link()

    def _invalidate_settings(self) -> None:
        for health in self.settings_health.values():
            health.valid = False

    async def _disconnect_link(self) -> None:
        self._closing = True
        self._link_lost = True
        if self._operation is not None:
            self._operation.cancel()
        self._ready = False
        self._invalidate_settings()
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
        previous = self.desk.state.position
        self.desk.state.position = sample
        if sample != previous:
            self.desk.changed()
        return sample

    async def write_control(self, payload: bytes) -> None:
        self.desk._motion_stop_sent = False
        await super().write_control(payload)
        self.desk._motion_stop_sent = payload == STOP

    async def disconnect(self) -> None:
        await self.desk._disconnect_link()
