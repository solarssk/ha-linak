"""Whether the desk has a validated, ready Bluetooth session."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .entity import LinakEntity


async def async_setup_entry(hass, entry, async_add_entities):
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
