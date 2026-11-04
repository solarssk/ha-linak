"""Whether the owner wants this integration to hold the desk's Bluetooth link.

The intent is stored on the config entry so a deliberate disconnect survives a Home
Assistant restart. It is separate from the observed connection state, and existing
entries without the key keep the default, connected behavior.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

CONF_KEEP_CONNECTED = "keep_connected"


def wants_connection(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_KEEP_CONNECTED, True) is not False


def remember_connection(hass: HomeAssistant, entry: ConfigEntry, wanted: bool) -> None:
    """Persist the intent without reloading the entry."""
    if wants_connection(entry) != wanted:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_KEEP_CONNECTED: wanted}
        )
