"""Native LINAK integration with explicitly configured movement controls."""

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import LinakCoordinator
from .naming import DEFAULT_NAME, desk_name

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER, Platform.BUTTON]
FIRST_REFRESH_TIMEOUT = 20


async def _async_first_refresh(coordinator: LinakCoordinator) -> None:
    """Bound initial radio work; HA owns later setup retries."""
    try:
        async with asyncio.timeout(FIRST_REFRESH_TIMEOUT):
            await coordinator.async_config_entry_first_refresh()
    except TimeoutError as error:
        raise ConfigEntryNotReady(
            "Initial Bluetooth connection/read timed out; setup will retry",
            translation_domain=DOMAIN,
            translation_key="startup_timeout",
        ) from error


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = LinakCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        await _async_first_refresh(coordinator)
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
    """Improve generated device metadata without guessing ownership of LINAK titles."""
    if CONF_NAME in entry.data:
        coordinator.name = entry.title
        return
    if coordinator.desk is None:
        return
    address = coordinator.address
    name = desk_name(
        address, coordinator.desk.device_name, coordinator.desk.device.name
    )
    if entry.title.upper() == address.upper():
        hass.config_entries.async_update_entry(entry, title=name)
        coordinator.name = name
    elif entry.title == DEFAULT_NAME and name != DEFAULT_NAME:
        # Older LINAK titles might have been explicitly chosen. Preserve the
        # config-entry title, but improve the device's integration-supplied name.
        # HA's device name_by_user always takes precedence over this metadata.
        coordinator.name = name
