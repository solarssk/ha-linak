"""Redacted configuration diagnostics."""

from dataclasses import asdict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


# HA requires this coroutine hook even though diagnostics read only cached data.
async def async_get_config_entry_diagnostics(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    coordinator = entry.runtime_data
    # Omit entry data, title and BLE objects entirely: these contain identifiers.
    return {
        "device_profile": coordinator.desk.identity.diagnostics(
            coordinator.desk.protocol_validated
        )
        if coordinator.desk
        else None,
        "connected": coordinator.desk.connected if coordinator.desk else False,
        "connection_wanted": coordinator.connection_wanted,
        "stage": coordinator.desk.stage if coordinator.desk else "not_started",
        "last_update_success": coordinator.last_update_success,
        "bluetooth": {
            "signal_strength": coordinator.signal_strength,
            "signal_strength_source": "advertisement",
            "backend": coordinator.bluetooth_backend,
        },
        "settings": coordinator.desk.settings_diagnostics()
        if coordinator.desk
        else None,
        "controls": {
            "range_configured": getattr(coordinator, "controls", None) is not None,
            "busy": coordinator.desk.control_busy if coordinator.desk else False,
            "last_result": coordinator.desk.last_control_result
            if coordinator.desk
            else "not_requested",
            "operation": {
                "phase": coordinator.operation.phase.value,
                "reason": coordinator.operation.reason.value
                if coordinator.operation.reason
                else None,
                "requested_height_cm": coordinator.operation.requested_height_cm,
                "last_result": coordinator.last_operation.phase.value
                if coordinator.last_operation
                else None,
            },
        },
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
