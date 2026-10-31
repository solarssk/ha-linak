"""Shared BLE state and recovery through Home Assistant."""

from datetime import timedelta
import logging

from bleak.backends import BleakBackend
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import DeskClient, DeskState

_LOGGER = logging.getLogger(__name__)


class LinakCoordinator(DataUpdateCoordinator[DeskState]):
    BACKENDS = tuple(
        sorted(
            {backend.value for backend in BleakBackend}
            | {"bleak_esphome", "bluez_mgmt"}
        )
    )

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(seconds=60),
        )
        self.address = entry.data[CONF_ADDRESS]
        self.desk: DeskClient | None = None

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
        backend = self.desk.client.backend_id
        if backend not in self.BACKENDS:
            return None
        if isinstance(backend, BleakBackend):
            return backend.value
        return backend

    @callback
    def _changed(self) -> None:
        if self.desk is not None and self.desk.connected:
            self.async_set_updated_data(self.desk.state)
        else:
            self.async_set_update_error(
                UpdateFailed("Desk disconnected or invalid position")
            )

    def _device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise ConnectionError("Desk is not reachable through Bluetooth")
        return device

    async def _async_update_data(self) -> DeskState:
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
            return await self.desk.refresh()
        except (BleakError, ConnectionError, TimeoutError, ValueError) as err:
            raise UpdateFailed("Unable to read LINAK desk") from err

    async def async_close(self) -> None:
        await self.async_shutdown()
        if self.desk is not None:
            await self.desk.disconnect()
