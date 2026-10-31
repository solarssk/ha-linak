"""Configure a LINAK desk using Home Assistant Bluetooth discovery."""

import asyncio
import logging
from typing import Any

import probatio as vol
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import (
    DeskClient,
    DeskState,
    DeskLinkLost,
    DeskAuthenticationError,
    DeskPairingUnsupported,
    DeskPairingTimeout,
    DeskPairingAgentError,
)
from .control_settings import (
    ControlSettings,
    MINIMUM_HEIGHT,
    MAXIMUM_HEIGHT,
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LinakOptionsFlow()

    def __init__(self) -> None:
        self._devices: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}
        self._address: str | None = None
        self._discovery_address: str | None = None
        self._name = DEFAULT_NAME
        self._validation_task: asyncio.Task[str | None] | None = None
        self._error: str | None = None
        self._validated_state: DeskState | None = None
        self._pending_range: dict[str, Any] | None = None

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
        self._validated_state = None
        error = None
        try:
            desk = DeskClient(self._device(), lambda: None, self._device)
            self._validated_state = await desk.refresh()
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
        if self._pending_range is not None:
            next_step = "finish" if self._error else "save_range"
        else:
            next_step = "retry" if self._error else "finish"
        return self.async_show_progress_done(next_step_id=next_step)

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
        errors = {"base": self._error} if self._error else {}
        if user_input is not None:
            try:
                if ControlSettings.from_options(user_input) is None:
                    raise ValueError("A height range is required")
            except ValueError:
                errors["base"] = "invalid_limits"
            else:
                self._pending_range = dict(user_input)
                self._validation_task = None
                self._error = None
                # Reconnect/read under the same bounded progress UI as initial setup.
                return await self.async_step_connect()
        options = user_input or self._pending_range or {}
        return self.async_show_form(
            step_id="finish", data_schema=_range_schema(options), errors=errors
        )

    async def async_step_save_range(self, user_input=None) -> ConfigFlowResult:
        self._abort_if_unique_id_configured()
        try:
            _validate_range(self._pending_range or {}, self._validated_state)
        except ValueError:
            self._error = "invalid_limits"
            return await self.async_step_finish()
        return self.async_create_entry(
            title=self._name,
            data={CONF_ADDRESS: self._address},
            options=self._pending_range,
        )


class LinakOptionsFlow(OptionsFlowWithReload):
    """Change the desk height range without changing panel settings."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                coordinator = getattr(self.config_entry, "runtime_data", None)
                if coordinator is None or not coordinator.last_update_success:
                    raise ValueError("A current height reading is required")
                _validate_range(user_input, coordinator.data)
                return self.async_create_entry(title="", data=user_input)
            except ValueError:
                errors["base"] = "invalid_limits"
        options = user_input if user_input is not None else self.config_entry.options
        return self.async_show_form(
            step_id="init", data_schema=_range_schema(options), errors=errors
        )


def _validate_range(options: dict[str, Any], state: DeskState | None) -> None:
    settings = ControlSettings.from_options(options)
    if settings is None or state is None or state.offset_raw is None:
        raise ValueError("A height range and valid reading are required")
    limits = settings.limits(state.offset_raw)
    position = state.position
    if (
        position is None
        or not limits.minimum_raw <= position.position_raw <= limits.maximum_raw
    ):
        raise ValueError("Current height must be inside the measured bounds")


def _range_schema(options) -> vol.Schema:
    schema: dict[Any, Any] = {}
    for key in (MINIMUM_HEIGHT, MAXIMUM_HEIGHT):
        field = (
            vol.Required(key, default=options[key])
            if key in options
            else vol.Required(key)
        )
        schema[field] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX, step=0.1, unit_of_measurement="cm"
            )
        )
    return vol.Schema(schema)
