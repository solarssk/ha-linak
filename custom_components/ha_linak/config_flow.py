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

from .client import (
    DeskClient,
    DeskLinkLost,
    DeskAuthenticationError,
    DeskPairingUnsupported,
    DeskPairingTimeout,
    DeskPairingAgentError,
)
from .const import DOMAIN
from .naming import DEFAULT_NAME, desk_name, discovery_title
from .protocol import SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


def _validation_error(error: Exception, stage: str) -> str:
    if isinstance(error, TimeoutError) and stage == "pairing":
        return "pairing_timeout"
    for exception_type, code in (
        (DeskPairingTimeout, "pairing_timeout"),
        (DeskPairingAgentError, "pairing_agent_unavailable"),
        (DeskAuthenticationError, "authentication_failed"),
        (DeskPairingUnsupported, "pairing_unsupported"),
        (DeskLinkLost, "connection_lost"),
        (TimeoutError, "timeout"),
        (ValueError, "unsupported_device"),
    ):
        if isinstance(error, exception_type):
            return code
    return "cannot_connect"


class LinakConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._devices: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}
        self._address: str | None = None
        self._discovery_address: str | None = None
        self._name = DEFAULT_NAME
        self._validation_task: asyncio.Task[str | None] | None = None
        self._error: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not discovery_info.connectable:
            return self.async_abort(reason="not_connectable")
        self._discovery_address = discovery_info.address
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
            self._name = self._desk_name(self._devices[address])
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
        if self._discovery_address is not None:
            info = self._devices[self._discovery_address]
            self.context["title_placeholders"] = {
                "name": discovery_title(info.address, self._desk_name(info))
            }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=address,
                                    label=f"{self._desk_name(info)} ({address})",
                                )
                                for address, info in self._devices.items()
                            ]
                        )
                    )
                }
            ),
        )

    def _desk_name(self, info: bluetooth.BluetoothServiceInfoBleak) -> str:
        """Resolve cached metadata without connecting or requesting a scan."""
        latest = bluetooth.async_last_service_info(
            self.hass, info.address, connectable=True
        )
        device = bluetooth.async_ble_device_from_address(
            self.hass, info.address, connectable=True
        )
        return desk_name(
            info.address,
            latest.name if latest is not None else None,
            info.name,
            device.name if device is not None else None,
            info.device.name,
            latest.device.name if latest is not None else None,
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
            self._name = desk_name(desk.device.address, self._name, desk.device_name)
        except (TimeoutError, ValueError, BleakError, ConnectionError) as err:
            error = _validation_error(err, desk.stage if desk else "device_lookup")
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
