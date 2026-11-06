"""Shared BLE state and recovery through Home Assistant."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging

from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import device_registry as dr

from .client import BLUETOOTH_BACKENDS, DeskClient, DeskState, backend_category
from .connection_intent import remember_connection, wants_connection
from .const import DOMAIN
from .control_settings import ControlSettings
from .motion import MotionError, MotionFailure, MotionStopped
from .protocol import ReminderClientInactive
from .reminder_settings import InvalidReminderInterval, ReminderProfileActive
from .operation import OperationStatus
from .setup_session import take_session
from .ownership import has_idasen_conflict

_LOGGER = logging.getLogger(__name__)
SETTINGS_REFRESH_INTERVAL = 300


def _failure_reason(error: Exception) -> str:
    if isinstance(error, MotionError):
        return error.reason.value
    return type(error).__name__


class LinakCoordinator(DataUpdateCoordinator[DeskState]):
    BACKENDS = BLUETOOTH_BACKENDS

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(seconds=60),
        )
        self.controls = ControlSettings.from_options(dict(entry.options))
        self.address = entry.data[CONF_ADDRESS]
        self._ownership = asyncio.Lock()
        self._unreachable_warned = False
        self.desk = take_session(hass, self.address)
        if self.desk is not None:
            self.desk.changed = self._changed
            self.desk.device_callback = self._device

    @property
    def connection_wanted(self) -> bool:
        """The owner's intent, not the observed link; it survives a restart."""
        assert self.config_entry is not None
        return wants_connection(self.config_entry)

    @callback
    def _show_released(self) -> None:
        """Present a deliberate release without logging it as a fault."""
        self.last_exception = UpdateFailed(
            translation_domain=DOMAIN, translation_key="connection_released"
        )
        self.last_update_success = False
        self.async_update_listeners()

    async def async_start_released(self) -> None:
        """Load the entities of a persisted release without touching the radio."""
        self.data = DeskState()
        if self.desk is not None:
            # A setup wizard may still hold a link; the owner asked for none.
            await self.desk.release()
        self._show_released()

    async def async_set_connection_wanted(self, wanted: bool) -> None:
        """Release the desk or take it back; the newest request wins.

        The intent is saved at once, so a restart or an in-flight refresh sees the
        latest choice. The actions themselves are serialized, and a request that a
        later one superseded does nothing.
        """
        assert self.config_entry is not None
        remember_connection(self.hass, self.config_entry, wanted)
        async with self._ownership:
            if self.connection_wanted != wanted:
                return
            try:
                if not wanted:
                    await self._release()
                    return
                if self.desk is not None:
                    self.desk.resume()
                if self.desk is not None and self.desk.connected:
                    return
                await self.async_refresh()
                if not self.last_update_success and self.connection_wanted:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="connection_failed"
                    )
            finally:
                # The owner's intent changed even when reconnecting did not work.
                self.async_update_listeners()

    async def _release(self) -> None:
        try:
            if self.desk is not None:
                await self.desk.release()
        except MotionError as err:
            # The link is down either way; the owner must still hear about a Stop
            # that could not be confirmed.
            raise self._control_error("stop", "released", err) from err
        finally:
            # Cached readings must stop looking live even if the disconnect failed.
            self._show_released()

    @property
    def signal_strength(self) -> int | None:
        """Latest connectable advertisement, not the active GATT link's RSSI."""
        if not bluetooth.async_address_present(
            self.hass, self.address, connectable=True
        ):
            return None
        info = bluetooth.async_last_service_info(
            self.hass, self.address, connectable=True
        )
        if info is None or info.rssi == 127:
            return None
        return info.rssi

    @property
    def bluetooth_backend(self) -> str | None:
        """Return only a known backend category, never its name or details."""
        if (
            self.desk is None
            or self.desk.client is None
            or not self.desk.client.is_connected
        ):
            return None
        return backend_category(self.desk.client)

    @property
    def operation(self) -> OperationStatus:
        """The latest explicit operation, kept apart from the Bluetooth link."""
        if self.desk is None:
            return OperationStatus()
        return self.desk.operation.status

    @property
    def last_operation(self) -> OperationStatus | None:
        """The latest settled result, which outlives the return to idle."""
        return None if self.desk is None else self.desk.operation.last

    @callback
    def _changed(self) -> None:
        if self.desk is not None and self.desk.connected:
            self._validate_control_reference(self.desk.state)
            if self.last_update_success and self.data is not None:
                # Notification ticks must not postpone the scheduled reference read.
                self.data = self.desk.state
                self.async_update_listeners()
            else:
                self.async_set_updated_data(self.desk.state)
        else:
            already_failed = not self.last_update_success
            self.async_set_update_error(
                UpdateFailed("Desk disconnected or invalid position")
            )
            if already_failed:
                # HA notifies listeners only on the first error; the always
                # available Operation sensor must still follow later changes.
                self.async_update_listeners()

    def _validate_control_reference(self, state: DeskState) -> None:
        """A changed calibration can invalidate previously configured bounds."""
        if self.controls is not None and state.offset_raw is not None:
            try:
                self.controls.limits(state.offset_raw)
            except ValueError:
                self.controls = None

    def reachability_hint(self) -> str:
        """Home Assistant's own explanation of why no connection path to the desk exists.

        Never raises: it only decorates a failure that is already being reported.
        """
        try:
            if bluetooth.async_scanner_count(self.hass, connectable=True) == 0:
                return "No connectable Bluetooth adapter or proxy is available"
            return bluetooth.async_address_reachability_diagnostics(
                self.hass,
                self.address,
                bluetooth.BluetoothReachabilityIntent.CONNECTION,
            )
        except Exception:  # noqa: BLE001
            return "Reachability diagnostics are unavailable"

    def _warn_unreachable_once(self) -> None:
        """Explain an outage once; Home Assistant itself logs the failure only once."""
        if self._unreachable_warned:
            return
        self._unreachable_warned = True
        _LOGGER.warning(
            "LINAK desk cannot be reached for a connection: %s",
            self.reachability_hint(),
        )

    def _device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise ConnectionError("Desk is not reachable through Bluetooth")
        return device

    def _require_connection_wanted(self) -> None:
        if not self.connection_wanted:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="connection_released"
            )

    async def _discard_if_released(self, desk: DeskClient) -> None:
        """A release that raced a refresh must not be revived by its result."""
        if self.connection_wanted:
            return
        try:
            await desk.release()
        except Exception as err:
            # Only the class is logged: raw backend messages stay out of the log.
            _LOGGER.warning(
                "Release after a raced refresh failed: %s", type(err).__name__
            )
        self._require_connection_wanted()

    async def _async_update_data(self) -> DeskState:
        self._require_connection_wanted()
        if self.desk is not None and self.desk.control_busy:
            if not self.desk.connected:
                raise UpdateFailed("Desk disconnected during control cleanup")
            return self.desk.state
        if has_idasen_conflict(self.hass, self.address):
            if self.desk is not None:
                await self.desk.disconnect()
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="idasen_conflict"
            )
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            if self.desk is not None:
                await self.desk.disconnect()
            self._warn_unreachable_once()
            raise UpdateFailed("Desk is not reachable through Bluetooth")
        if self.desk is None:
            self.desk = DeskClient(device, self._changed, self._device)
        else:
            self.desk.device = device
        try:
            state = await self.desk.refresh(
                allow_partial_settings=True,
                settings_interval=SETTINGS_REFRESH_INTERVAL,
            )
            await self._discard_if_released(self.desk)
            self._validate_control_reference(state)
            self._update_device_identity()
            self._unreachable_warned = False
            return state
        except (BleakError, ConnectionError, TimeoutError, ValueError) as err:
            if self.desk.stage == "connection":
                self._warn_unreachable_once()
            raise UpdateFailed(
                f"Unable to read LINAK desk (stage={self.desk.stage}, "
                f"reason={_failure_reason(err)})"
            ) from err

    @callback
    def _update_device_identity(self) -> None:
        """Refresh an existing registry entry after reconnect or a released boot."""
        if self.desk is None or self.config_entry is None:
            return
        registry = dr.async_get(self.hass)
        identity = self.desk.identity
        for device in dr.async_entries_for_config_entry(
            registry, self.config_entry.entry_id
        ):
            if (DOMAIN, self.address) not in device.identifiers:
                continue
            if device.model != identity.model or device.sw_version != identity.firmware:
                registry.async_update_device(
                    device.id, model=identity.model, sw_version=identity.firmware
                )

    async def async_set_reminder_profile(self, profile: int) -> None:
        """Configure reminders without travel limits, activation or a new client."""
        await self._async_reminder_change(
            lambda desk: desk.set_reminder_profile(profile)
        )

    async def async_set_reminder_sitting_minutes(self, minutes: float) -> None:
        """Keep the original profile 1 sitting control and standard button."""
        await self.async_set_reminder_interval_minutes(1, False, minutes)

    async def async_set_reminder_interval_minutes(
        self, profile: int, standing: bool, minutes: float
    ) -> None:
        """Set one duration through the shared reminder transaction."""
        await self._async_reminder_change(
            lambda desk: desk.set_reminder_interval_minutes(profile, standing, minutes)
        )

    async def async_set_panel_unit_preference(self, inch: bool) -> None:
        """Change the panel preference independently of HA presentation units."""
        await self._async_reminder_change(
            lambda desk: desk.set_panel_unit_preference(inch)
        )

    async def _async_reminder_change(
        self, change: Callable[[DeskClient], Awaitable[DeskState]]
    ) -> None:
        self._require_connection_wanted()
        if has_idasen_conflict(self.hass, self.address):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="idasen_conflict"
            )
        if self.desk is None or not self.desk.connected:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="control_unavailable"
            )
        try:
            await change(self.desk)
        except InvalidReminderInterval as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="reminder_interval_invalid"
            ) from err
        except ReminderProfileActive as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="reminder_profile_active"
            ) from err
        except ReminderClientInactive as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="reminder_client_inactive"
            ) from err
        except MotionError as err:
            key = "control_unavailable"
            if err.reason == MotionFailure.BUSY:
                key = "control_busy"
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key=key
            ) from err
        except (BleakError, ConnectionError, TimeoutError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="reminder_failed"
            ) from err
        finally:
            self._changed()

    async def async_move_to_cm(self, height_cm: float) -> None:
        await self._async_control("target", height_cm)

    async def async_move_to_memory(self, index: int) -> None:
        await self._async_control("memory", index)

    async def async_stop(self) -> None:
        await self._async_control("stop")

    async def _async_control(self, action: str, value: float | int = 0) -> None:
        if action != "stop" and has_idasen_conflict(self.hass, self.address):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="idasen_conflict"
            )
        if self.desk is None or (action != "stop" and not self.desk.connected):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="control_unavailable"
            )
        if action != "stop" and self.controls is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="range_not_configured"
            )
        settings = self.controls
        backend = self.bluetooth_backend or "not_connected"
        try:
            if action == "stop":
                await self.desk.stop()
            elif settings is not None:
                if action == "memory":
                    await self.desk.move_to_memory(int(value), settings)
                else:
                    await self.desk.move_to_cm(value, settings)
        except MotionStopped:
            # Intentional interruption is a normal control outcome. Failed Stop
            # cleanup raises an ordinary MotionError and remains visible.
            return
        except (
            MotionError,
            BleakError,
            ConnectionError,
            TimeoutError,
            ValueError,
        ) as err:
            raise self._control_error(action, backend, err) from err
        finally:
            self._changed()

    def _control_error(
        self, action: str, backend: str, error: Exception
    ) -> HomeAssistantError:
        if isinstance(error, MotionError) and error.reason == MotionFailure.BUSY:
            return ServiceValidationError(
                translation_domain=DOMAIN, translation_key="control_busy"
            )
        assert self.desk is not None
        _LOGGER.warning(
            "LINAK %s failed during %s: reason=%s backend=%s",
            action,
            self.desk.stage,
            _failure_reason(error),
            backend,
        )
        if (
            action != "stop"
            and isinstance(error, MotionError)
            and error.reason == MotionFailure.REVERSE
        ):
            # The desk turned back by itself, which its anti-collision can do. The
            # cause is inferred from position, not read from a panel error code.
            key = "movement_reversed"
        else:
            key = "stop_failed" if action == "stop" else "movement_failed"
        return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)

    async def async_close(self) -> None:
        await self.async_shutdown()
        if self.desk is not None:
            self.desk.close_operation_resets()
            await self.desk.disconnect()
