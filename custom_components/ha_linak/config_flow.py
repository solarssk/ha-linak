"""Configure a LINAK desk using Home Assistant Bluetooth discovery."""

import asyncio
import logging
from typing import Any

import probatio as vol
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector, device_registry as dr

from .client import (
    DeskClient,
    DeskState,
    DeskLinkLost,
    DeskAuthenticationError,
    DeskPairingUnsupported,
    DeskPairingTimeout,
    DeskPairingAgentError,
)
from .calibration import (
    HeightCalibration,
    InvalidMeasurement,
    SettingRejected,
    MEASURED_HEIGHT,
    CalibrationSnapshotChanged,
)
from .motion import MotionError, _drain_cleanup
from .control_settings import (
    ControlSettings,
    MINIMUM_HEIGHT,
    MAXIMUM_HEIGHT,
)
from .const import DOMAIN
from .entity import whole_centimeters
from .naming import DEFAULT_NAME, cached_bluez_names, desk_name, discovery_title
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
    # The connector wraps exhausted connection timeouts in BleakNotFoundError.
    # Preserve that reason without parsing private backend error messages.
    cause = error.__cause__
    for _ in range(8):
        if isinstance(cause, TimeoutError):
            return "timeout"
        if cause is None:
            break
        cause = cause.__cause__
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
        self._user_named = False
        self._system_names: dict[str, str] | None = None
        self._validation_task: asyncio.Task[str | None] | None = None
        self._error: str | None = None
        self._validated_state: DeskState | None = None
        self._pending_range: dict[str, Any] | None = None
        self._calibration: HeightCalibration | None = None
        self._calibration_task: asyncio.Task[str | None] | None = None
        self._preparing = False
        self._final_height_check = False

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
        if self._system_names is None:
            self._system_names = {}
            if any(
                self._desk_name(info) == DEFAULT_NAME for info in self._devices.values()
            ):
                self._system_names = await cached_bluez_names()
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
            (self._system_names or {}).get(info.address.upper()),
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
            if not self._user_named:
                self._name = desk_name(
                    desk.device.address, self._name, desk.device_name
                )
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
        if self._pending_range is None:
            next_step = "retry" if self._error else "name"
        elif self._error:
            next_step = "finish"
        elif self._final_height_check:
            next_step = "save_range"
        else:
            next_step = "height"
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

    async def async_step_name(self, user_input=None) -> ConfigFlowResult:
        errors = {"base": self._error} if self._error else {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME, self._name)).strip()
            if name and len(name) <= 80 and name.isprintable():
                self._name = name
                self._user_named = True
                self._error = None
                self._preparing = True
                self._calibration_task = self.hass.async_create_task(
                    self._apply_calibration(), eager_start=False
                )
                return await self.async_step_calibration_apply()
            errors["name"] = "invalid_name"
        return self.async_show_form(
            step_id="name", data_schema=_name_schema(self._name), errors=errors
        )

    async def async_step_height(self, user_input=None) -> ConfigFlowResult:
        return await _guide_height(
            self, user_input, self._validated_state, "refresh_range"
        )

    async def async_step_measure(self, user_input=None) -> ConfigFlowResult:
        return await _guide_measure(
            self, user_input, self._validated_state, "confirm_height"
        )

    async def async_step_confirm_height(self, user_input=None) -> ConfigFlowResult:
        if self._calibration is not None and self._calibration.changed:
            return await self.async_step_calibration_confirm()
        return await self.async_step_refresh_range()

    async def async_step_refresh_range(self, user_input=None) -> ConfigFlowResult:
        """Re-read position after the owner confirms the displayed height."""
        self._final_height_check = True
        self._validation_task = None
        self._error = None
        return await self.async_step_connect()

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._abort_if_unique_id_configured()
        errors = {"base": self._error} if self._error else {}
        if user_input is not None:
            error = self._prepare_finish(user_input)
            errors = {"base": error} if error else {}
            if not errors:
                self._final_height_check = False
                self._validation_task = None
                self._error = None
                return await self.async_step_connect()
        options = user_input or self._pending_range or {}
        return self.async_show_form(
            step_id="finish",
            data_schema=_range_schema(options),
            errors=errors,
            description_placeholders=_height_placeholders(self._validated_state),
        )

    def _prepare_finish(self, user_input: dict[str, Any]) -> str | None:
        self._calibration = None
        try:
            if ControlSettings.from_options(user_input) is None:
                raise ValueError("A height range is required")
        except ValueError:
            return "invalid_limits"
        self._pending_range = _range_options(user_input)
        return None

    async def async_step_calibration_confirm(self, user_input=None) -> ConfigFlowResult:
        assert self._calibration is not None
        if user_input is not None:
            self._calibration_task = self.hass.async_create_task(
                self._apply_calibration(), eager_start=False
            )
            return await self.async_step_calibration_apply()
        return self.async_show_form(
            step_id="calibration_confirm",
            data_schema=vol.Schema({}),
            description_placeholders=_calibration_placeholders(
                self._calibration, self._pending_range, self._name
            ),
        )

    async def _apply_calibration(self) -> str | None:
        desk: DeskClient | None = None
        error = None
        try:
            desk = DeskClient(self._device(), lambda: None, self._device)
            await desk.refresh()
            if self._preparing:
                assert desk.state.height_cm is not None
                self._calibration = _prepare_calibration(
                    desk.state, desk.state.height_cm
                )
            assert self._calibration is not None
            self._validated_state = await desk.calibrate_height(
                self._calibration, activate_client=self._preparing
            )
        except SettingRejected as err:
            _log_setting_rejection(err, desk)
            error = "setting_rejected"
        except CalibrationSnapshotChanged:
            error = "calibration_snapshot_changed"
        except (
            BleakError,
            ConnectionError,
            TimeoutError,
            ValueError,
            MotionError,
        ) as err:
            error = "calibration_failed"
            _LOGGER.warning(
                "LINAK calibration failed during %s: %s",
                desk.stage if desk else "device_lookup",
                type(err).__name__,
            )
        finally:
            self._calibration = None
            if desk is not None:
                settled = asyncio.gather(desk.disconnect(), return_exceptions=True)
                await _drain_cleanup(settled)
                if isinstance(settled.result()[0], Exception):
                    error = "calibration_failed"
        if error:
            # Read-only recovery cannot replay the uncertain setting write.
            self._validated_state = None
            await self._validate()
        return error

    async def async_step_calibration_apply(self, user_input=None) -> ConfigFlowResult:
        assert self._calibration_task is not None
        if not self._calibration_task.done():
            return self.async_show_progress(
                step_id="calibration_apply",
                progress_action="calibrate",
                progress_task=self._calibration_task,
            )
        self._error = self._calibration_task.result()
        self._calibration_task = None
        if self._preparing:
            next_step = "name" if self._error else "finish"
            if self._error:
                self._error = "client_preparation_failed"
        else:
            next_step = "height" if self._error else "save_range"
        self._preparing = False
        return self.async_show_progress_done(next_step_id=next_step)

    async def async_step_save_range(self, user_input=None) -> ConfigFlowResult:
        self._abort_if_unique_id_configured()
        try:
            _validate_range(self._pending_range or {}, self._validated_state)
        except ValueError:
            self._error = "invalid_limits"
            return await self.async_step_finish()
        return self.async_create_entry(
            title=self._name,
            data={CONF_ADDRESS: self._address, CONF_NAME: self._name},
            options=self._pending_range,
        )


class LinakOptionsFlow(OptionsFlowWithReload):
    """Configure measured height calibration and the desk travel range."""

    def __init__(self) -> None:
        self._calibration: HeightCalibration | None = None
        self._calibration_task: asyncio.Task[str | None] | None = None
        self._pending_range: dict[str, Any] = {}
        self._calibration_error: str | None = None

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_range(user_input)
        options = ["name", "connect"]
        if self._has_bounds():
            options.append("height")
        options.append("range")
        return self.async_show_menu(step_id="init", menu_options=options)

    # Named HA flow steps must be coroutines; renaming only updates HA registries.
    async def async_step_name(
        self, user_input=None
    ) -> ConfigFlowResult:  # NOSONAR(S7503) HA flow contract
        errors = {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME, self.config_entry.title)).strip()
            if name and len(name) <= 80 and name.isprintable():
                _rename_ha_device(self.hass, self.config_entry, name)
                return self.async_create_entry(
                    title="", data=dict(self.config_entry.options)
                )
            errors["name"] = "invalid_name"
        return self.async_show_form(
            step_id="name",
            data_schema=_name_schema(self.config_entry.title),
            errors=errors,
        )

    async def async_step_connect(self, user_input=None) -> ConfigFlowResult:
        state = self._current_state()
        errors = {}
        if user_input is not None:
            if state is None or state.height_cm is None:
                errors["base"] = "connection_unavailable"
            else:
                try:
                    self._calibration = _prepare_calibration(state, state.height_cm)
                except InvalidMeasurement:
                    errors["base"] = "desk_not_stationary"
                else:
                    self._pending_range = dict(self.config_entry.options)
                    self._calibration_task = self.hass.async_create_task(
                        self._apply_calibration(), eager_start=False
                    )
                    return await self.async_step_calibration_apply()
        return self.async_show_form(
            step_id="connect", data_schema=vol.Schema({}), errors=errors
        )

    def _has_bounds(self) -> bool:
        return all(
            key in self.config_entry.options for key in (MINIMUM_HEIGHT, MAXIMUM_HEIGHT)
        )

    async def async_step_height(self, user_input=None) -> ConfigFlowResult:
        if not self._has_bounds():
            self._calibration_error = "range_required"
            return await self.async_step_range()
        return await _guide_height(
            self, user_input, self._current_state(), "confirm_height"
        )

    async def async_step_measure(self, user_input=None) -> ConfigFlowResult:
        if not self._has_bounds():
            self._calibration_error = "range_required"
            return await self.async_step_range()
        return await _guide_measure(
            self, user_input, self._current_state(), "confirm_height"
        )

    async def async_step_confirm_height(self, user_input=None) -> ConfigFlowResult:
        self._pending_range = dict(self.config_entry.options)
        if self._calibration is not None and self._calibration.changed:
            return await self.async_step_calibration_confirm()
        return await self.async_step_calibration_finish()

    async def async_step_range(self, user_input=None) -> ConfigFlowResult:
        errors = {"base": self._calibration_error} if self._calibration_error else {}
        self._calibration_error = None
        if user_input is not None:
            try:
                self._prepare_options(user_input)
                return self.async_create_entry(title="", data=self._pending_range)
            except ConnectionError:
                errors["base"] = "connection_unavailable"
            except ValueError:
                errors["base"] = "invalid_limits"
        options = (
            user_input
            if user_input is not None
            else (self._pending_range or self.config_entry.options)
        )
        return self.async_show_form(
            step_id="range",
            data_schema=_range_schema(options),
            errors=errors,
            description_placeholders=_height_placeholders(self._current_state()),
        )

    def _current_state(self) -> DeskState | None:
        """Hide cached height when the latest connection update failed."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.last_update_success:
            return None
        return coordinator.data

    def _prepare_options(self, user_input: dict[str, Any]) -> None:
        state = self._current_state()
        if state is None:
            raise ConnectionError("A current height reading is required")
        self._calibration = None
        self._pending_range = _range_options(user_input)
        _validate_range(user_input, state)

    async def async_step_calibration_confirm(self, user_input=None) -> ConfigFlowResult:
        assert self._calibration is not None
        if user_input is not None:
            self._calibration_task = self.hass.async_create_task(
                self._apply_calibration(), eager_start=False
            )
            return await self.async_step_calibration_apply()
        return self.async_show_form(
            step_id="calibration_confirm",
            data_schema=vol.Schema({}),
            description_placeholders=_calibration_placeholders(
                self._calibration, self._pending_range, self.config_entry.title
            ),
        )

    async def _apply_calibration(self) -> str | None:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        try:
            if (
                coordinator is None
                or coordinator.desk is None
                or self._calibration is None
            ):
                raise ValueError("A current connection is required")
            await coordinator.desk.calibrate_height(
                self._calibration, activate_client=True
            )
            return None
        except SettingRejected as err:
            _log_setting_rejection(err, coordinator.desk if coordinator else None)
            return "setting_rejected"
        except CalibrationSnapshotChanged:
            return "calibration_snapshot_changed"
        except BleakError, ConnectionError, TimeoutError, ValueError, MotionError:
            return "calibration_failed"
        finally:
            self._calibration = None
            if coordinator is not None:
                coordinator._changed()

    async def async_step_calibration_apply(self, user_input=None) -> ConfigFlowResult:
        assert self._calibration_task is not None
        if not self._calibration_task.done():
            return self.async_show_progress(
                step_id="calibration_apply",
                progress_action="calibrate",
                progress_task=self._calibration_task,
            )
        self._calibration_error = self._calibration_task.result()
        self._calibration_task = None
        return self.async_show_progress_done(next_step_id="calibration_finish")

    async def async_step_calibration_finish(self, user_input=None) -> ConfigFlowResult:
        if not self._calibration_error:
            try:
                _validate_range(
                    self._pending_range, self.config_entry.runtime_data.data
                )
            except ValueError:
                self._calibration_error = "invalid_limits"
            else:
                return self.async_create_entry(title="", data=self._pending_range)
        if self._calibration_error != "invalid_limits":
            return await self.async_step_height()
        return await self.async_step_range()


def _range_options(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: values[key] for key in (MINIMUM_HEIGHT, MAXIMUM_HEIGHT) if key in values
    }


def _prepare_calibration(
    state: DeskState | None, measured_cm: float
) -> HeightCalibration:
    if state is None:
        raise ValueError("A current reading is required")
    return HeightCalibration.prepare(state.position, state.offset_raw, measured_cm)


def _height_placeholders(state: DeskState | None) -> dict[str, str]:
    height = state.height_cm if state is not None else None
    return {"height": str(whole_centimeters(height)) if height is not None else "?"}


def _calibration_placeholders(
    proposal: HeightCalibration,
    bounds: dict[str, Any] | None = None,
    name: str = DEFAULT_NAME,
) -> dict[str, str]:
    return {
        "desk_name": name,
        "minimum_height": str((bounds or {}).get(MINIMUM_HEIGHT, "?")),
        "maximum_height": str((bounds or {}).get(MAXIMUM_HEIGHT, "?")),
        "old_height": f"{(proposal.position_raw + proposal.old_offset_raw) / 100:.1f}",
        "measured_height": f"{proposal.measured_cm:.1f}",
        "old_offset": f"{proposal.old_offset_raw / 100:.2f}",
        "new_offset": f"{proposal.new_offset_raw / 100:.2f}",
    }


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


def _name_schema(name: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_NAME, default=name): selector.TextSelector()})


async def _guide_height(flow, user_input, state, next_step) -> ConfigFlowResult:
    if user_input is not None and state is not None:
        flow._calibration = None
        if user_input.get("height_correct", True):
            return await getattr(flow, f"async_step_{next_step}")()
        return await flow.async_step_measure()
    error = getattr(flow, "_error", None) or getattr(flow, "_calibration_error", None)
    flow._error = None
    flow._calibration_error = None
    if state is None and not error:
        error = "connection_unavailable"
    return flow.async_show_form(
        step_id="height",
        data_schema=vol.Schema(
            {vol.Required("height_correct", default=True): selector.BooleanSelector()}
        ),
        description_placeholders=_height_placeholders(state),
        errors={"base": error} if error else {},
    )


async def _guide_measure(flow, user_input, state, next_step) -> ConfigFlowResult:
    errors = {"base": "connection_unavailable"} if state is None else {}
    if user_input is not None and state is not None:
        try:
            proposal = _prepare_calibration(state, user_input.get(MEASURED_HEIGHT))
        except ValueError:
            errors["base"] = "invalid_measurement"
        else:
            flow._calibration = proposal
            return await getattr(flow, f"async_step_{next_step}")()
    return flow.async_show_form(
        step_id="measure",
        data_schema=vol.Schema(
            {
                vol.Required(MEASURED_HEIGHT): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        mode=selector.NumberSelectorMode.BOX,
                        step=0.1,
                        unit_of_measurement="cm",
                    )
                )
            }
        ),
        errors=errors,
        description_placeholders=_height_placeholders(state),
    )


def _rename_ha_device(hass: HomeAssistant, entry: ConfigEntry, name: str) -> None:
    """Apply an explicit HA name without reconnecting or changing Bluetooth."""
    hass.config_entries.async_update_entry(
        entry, title=name, data={**entry.data, CONF_NAME: name}
    )
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        coordinator.name = name
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, entry.data[CONF_ADDRESS]), entry.entry_id
    )
    if device is not None:
        registry.async_update_device(device.id, name_by_user=name)


def _log_setting_rejection(error: SettingRejected, desk: DeskClient | None) -> None:
    """Log only the protocol status and phase, never identifiers or payloads."""
    _LOGGER.warning(
        "LINAK setting rejected during %s: status=%02x",
        desk.stage if desk else "not_connected",
        error.status,
    )
