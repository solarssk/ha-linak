"""Redacted configuration diagnostics."""

from dataclasses import asdict


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    # Omit entry data, title and BLE objects entirely: these contain identifiers.
    return {
        "connected": coordinator.desk.connected if coordinator.desk else False,
        "stage": coordinator.desk.stage if coordinator.desk else "not_started",
        "last_update_success": coordinator.last_update_success,
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
