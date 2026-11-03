"""Shared BLE state and recovery through Home Assistant."""

from datetime import timedelta
import logging

from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import BLUETOOTH_BACKENDS, DeskClient, DeskState, backend_category
from .const import DOMAIN
from .control_settings import ControlSettings
from .motion import MotionError, MotionFailure, MotionStopped
from .setup_session import take_session

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
        self.desk = take_session(hass, self.address)
        if self.desk is not None:
            self.desk.changed = self._changed
            self.desk.device_callback = self._device

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
            self.async_set_update_error(
                UpdateFailed("Desk disconnected or invalid position")
            )

    def _validate_control_reference(self, state: DeskState) -> None:
        """A changed calibration can invalidate previously configured bounds."""
        if self.controls is not None and state.offset_raw is not None:
            try:
                self.controls.limits(state.offset_raw)
            except ValueError:
                self.controls = None

    def _device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise ConnectionError("Desk is not reachable through Bluetooth")
        return device

    async def _async_update_data(self) -> DeskState:
        if self.desk is not None and self.desk.control_busy:
            if not self.desk.connected:
                raise UpdateFailed("Desk disconnected during control cleanup")
            return self.desk.state
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            if self.desk is not None:
                await self.desk.disconnect()
            raise UpdateFailed("Desk is not reachable through Bluetooth")
        if self.desk is None:
            self.desk = DeskClient(device, self._changed, self._device)
        else:
            self.desk.device = device
        try:
            state = await self.desk.refresh(
                allow_partial_settings=self.data is not None,
                settings_interval=SETTINGS_REFRESH_INTERVAL,
            )
            self._validate_control_reference(state)
            return state
        except (BleakError, ConnectionError, TimeoutError, ValueError) as err:
            raise UpdateFailed(
                f"Unable to read LINAK desk (stage={self.desk.stage}, "
                f"reason={_failure_reason(err)})"
            ) from err

    async def async_move_to_cm(self, height_cm: float) -> None:
        await self._async_control("target", height_cm)

    async def async_move_to_memory(self, index: int) -> None:
        await self._async_control("memory", index)

    async def async_stop(self) -> None:
        await self._async_control("stop")

    async def _async_control(self, action: str, value: float | int = 0) -> None:
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
            return HomeAssistantError(
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
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="stop_failed" if action == "stop" else "movement_failed",
        )

    async def async_close(self) -> None:
        await self.async_shutdown()
        if self.desk is not None:
            await self.desk.disconnect()
