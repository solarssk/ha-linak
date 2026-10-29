"""Read-only desk heights and reminder profiles."""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LinakCoordinator


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = [LinakSensor(coordinator, "height"), LinakSensor(coordinator, "offset")]
    entities += [
        LinakSensor(coordinator, f"memory_{i + 1}")
        for i in range(len(coordinator.data.memories))
    ]
    entities += [LinakSensor(coordinator, "reminder_profile")]
    entities += [
        LinakSensor(coordinator, f"reminder_{i + 1}_{kind}")
        for i in range(3)
        for kind in ("sit", "stand")
    ]
    async_add_entities(entities)


class LinakSensor(CoordinatorEntity[LinakCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LinakCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=coordinator.name,
            manufacturer="LINAK",
            model="DPG",
        )
        if key != "height":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key in ("height", "offset") or key.startswith("memory_"):
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
            self._attr_suggested_display_precision = 1
        elif key != "reminder_profile":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        if key == "height":
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        state = self.coordinator.data
        if self.key == "height":
            return state.height_cm
        if self.key == "offset":
            return state.offset_raw / 100 if state.offset_raw is not None else None
        if self.key.startswith("memory_"):
            index = int(self.key.split("_")[1]) - 1
            if index >= len(state.memories) or state.offset_raw is None:
                return None
            raw = state.memories[index].position_raw
            return (raw + state.offset_raw) / 100 if raw is not None else None
        if state.reminders is None:
            return None
        if self.key == "reminder_profile":
            return state.reminders.selected_profile
        _, profile, kind = self.key.split("_")
        return state.reminders.profiles_raw[int(profile) - 1][0 if kind == "sit" else 1]
