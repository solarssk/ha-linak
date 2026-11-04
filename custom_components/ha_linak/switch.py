"""Owner control over whether the integration holds the desk's Bluetooth link."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import LinakEntity


# HA requires this coroutine hook even when constructing entities needs no I/O.
async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([LinakKeepConnectedSwitch(entry.runtime_data, "keep_connected")])


class LinakKeepConnectedSwitch(LinakEntity, SwitchEntity):
    """The owner's intent. The Connection sensor still reports the actual link."""

    _attr_icon = "mdi:bluetooth-connect"

    @property
    def available(self) -> bool:
        # A released or unreachable desk is exactly when the owner needs this.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.connection_wanted

    async def async_turn_on(self, **_kwargs: Any) -> None:
        await self.coordinator.async_set_connection_wanted(True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        await self.coordinator.async_set_connection_wanted(False)
