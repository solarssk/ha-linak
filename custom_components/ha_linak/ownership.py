"""Detect configured IKEA ownership without changing another integration."""

import re

from homeassistant.config_entries import SOURCE_IGNORE
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac


class DeskOwnershipConflict(ConnectionError):
    """An enabled IKEA entry already claims this desk."""


def _address(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = format_mac(value.strip())
    return (
        normalized
        if re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", normalized)
        else None
    )


@callback
def has_idasen_conflict(hass: HomeAssistant, address: str) -> bool:
    """Match the official entry's address, falling back to its unique ID."""
    target = _address(address)
    if target is None:
        return False
    for entry in hass.config_entries.async_entries("idasen_desk"):
        if entry.disabled_by is not None or entry.source == SOURCE_IGNORE:
            continue
        other = _address(entry.data.get(CONF_ADDRESS)) or _address(entry.unique_id)
        if other == target:
            return True
    return False
