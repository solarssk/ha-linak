"""Native LINAK integration with explicitly configured movement controls."""

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform, CONF_NAME
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady

from .client import REFRESH_TIMEOUT
from .const import DOMAIN
from .coordinator import LinakCoordinator
from .naming import DEFAULT_NAME, desk_name
from .services import register_services

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
]
FIRST_REFRESH_TIMEOUT = REFRESH_TIMEOUT


# HA requires the async setup hook even when registration itself does not await.
async def async_setup(  # NOSONAR(S7503) HA coroutine contract
    hass: HomeAssistant, _config: ConfigType
) -> bool:
    """Register explicit diagnostic reads without starting Bluetooth work."""
    register_services(hass)
    return True


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
    if hass.state is not CoreState.running:
        # HA schedules ConfigEntryNotReady again on HOMEASSISTANT_STARTED.
        # Do not race adapter/proxy startup or block the bootstrap on radio I/O.
        raise ConfigEntryNotReady(
            "Waiting for Home Assistant startup before connecting to the desk",
            translation_domain=DOMAIN,
            translation_key="startup_waiting",
        )
    coordinator = LinakCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        if coordinator.connection_wanted:
            await _async_first_refresh(coordinator)
            _repair_title(hass, entry, coordinator)
        else:
            # A persisted release loads its entities without waiting for the desk.
            await coordinator.async_start_released()
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
