"""Configure a LINAK desk using Home Assistant Bluetooth discovery."""

from typing import Any
import probatio as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector

from .client import DeskClient
from .const import DOMAIN
from .protocol import SERVICE_UUID


class LinakConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._devices: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._devices[discovery_info.address] = discovery_info
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            info = self._devices.get(address)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                desk = DeskClient(info.device, lambda: None)
                try:
                    await desk.refresh()
                except BleakError, ConnectionError, TimeoutError, ValueError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=info.name or "LINAK", data={CONF_ADDRESS: address}
                    )
                finally:
                    await desk.disconnect()
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            if (
                SERVICE_UUID in info.service_uuids
                and info.address not in self._async_current_ids()
            ):
                self._devices[info.address] = info
        if not self._devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=address,
                                    label=f"{info.name or 'LINAK'} ({address})",
                                )
                                for address, info in self._devices.items()
                            ]
                        )
                    )
                }
            ),
            errors=errors,
        )
