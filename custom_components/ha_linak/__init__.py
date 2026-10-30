"""Native read-only LINAK integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant

from .coordinator import LinakCoordinator
from .naming import desk_name

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = LinakCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
        _repair_title(hass, entry, coordinator)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.async_close()
        raise

    async def stop(_event):
        await coordinator.async_close()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_close()
        return True
    return False


def _repair_title(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: LinakCoordinator
) -> None:
    """Replace a title that was saved as the bare address."""
    address = coordinator.address
    if entry.title.upper() != address.upper() or coordinator.desk is None:
        return
    name = desk_name(address, coordinator.desk.device.name)
    hass.config_entries.async_update_entry(entry, title=name)
    coordinator.name = name
