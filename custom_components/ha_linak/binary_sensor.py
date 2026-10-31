"""Whether the desk has a validated, ready Bluetooth session."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import LinakEntity


# HA requires this async platform hook even when entity creation needs no await.
async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([LinakConnectionSensor(entry.runtime_data, "connection")])


class LinakConnectionSensor(LinakEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def available(self) -> bool:
        # A failed desk refresh is the useful "disconnected" state, not an
        # unavailable connectivity entity. HA still owns entity unload/shutdown.
        return True

    @property
    def is_on(self) -> bool:
        desk = self.coordinator.desk
        return desk is not None and desk.connected
