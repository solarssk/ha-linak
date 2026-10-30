"""Configure a LINAK desk using Home Assistant Bluetooth discovery."""

import asyncio
import logging
from typing import Any

import probatio as vol
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector

from .client import DeskClient
from .const import DOMAIN
from .protocol import SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


class LinakConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._devices: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}
        self._address: str | None = None
        self._name = "LINAK"
        self._validation_task: asyncio.Task[str | None] | None = None
        self._error: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not discovery_info.connectable:
            return self.async_abort(reason="not_connectable")
        self.context["title_placeholders"] = {"name": discovery_info.name or "LINAK"}
        self._devices[discovery_info.address] = discovery_info
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address not in self._devices:
                return self.async_abort(reason="no_devices_found")
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._address = address
            self._name = self._devices[address].name or "LINAK"
            return await self.async_step_connect()
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
        )

    def _device(self) -> BLEDevice:
        assert self._address is not None
        device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if device is None:
            raise ConnectionError("Desk is not reachable through Bluetooth")
        return device

    async def _validate(self) -> str | None:
        desk: DeskClient | None = None
        error = None
        try:
            desk = DeskClient(self._device(), lambda: None, self._device)
            await desk.refresh()
        except TimeoutError:
            error = "timeout"
        except ValueError:
            error = "unsupported_device"
        except BleakError, ConnectionError:
            error = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected LINAK configuration failure")
            error = "unknown"
        finally:
            stage = desk.stage if desk else "device_lookup"
            if desk is not None:
                try:
                    await desk.disconnect()
                except BleakError, ConnectionError, TimeoutError:
                    if error is None:
                        stage = "disconnect"
                        error = "cannot_connect"
        if error:
            _LOGGER.warning(
                "LINAK setup failed during %s: %s",
                stage,
                error,
            )
        return error

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._validation_task is None:
            self._validation_task = self.hass.async_create_task(
                self._validate(), eager_start=False
            )
        if not self._validation_task.done():
            return self.async_show_progress(
                step_id="connect",
                progress_action="connect",
                progress_task=self._validation_task,
            )
        self._error = self._validation_task.result()
        return self.async_show_progress_done(
            next_step_id="retry" if self._error else "finish"
        )

    async def async_step_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._validation_task = None
            return await self.async_step_connect()
        return self.async_show_form(
            step_id="retry",
            data_schema=vol.Schema({}),
            errors={"base": self._error or "cannot_connect"},
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._name, data={CONF_ADDRESS: self._address}
        )
