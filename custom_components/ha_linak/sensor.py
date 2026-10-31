"""Read-only desk heights and reminder profiles."""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfLength,
    UnitOfTime,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)

from .coordinator import LinakCoordinator
from .entity import LinakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        LinakSensor(coordinator, "height"),
        LinakSensor(coordinator, "offset"),
    ]
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
    entities += [
        LinakDiagnosticSensor(coordinator, key)
        for key in ("signal_strength", "bluetooth_backend")
    ]
    async_add_entities(entities)


class LinakSensor(LinakEntity, SensorEntity):
    def __init__(self, coordinator: LinakCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self.key = key
        if key == "offset":
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


class LinakDiagnosticSensor(LinakEntity, SensorEntity):
    """Optional transport details, independent of desk-reading availability."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LinakCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self.key = key
        if key == "signal_strength":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(coordinator.BACKENDS)

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @property
    def native_value(self) -> str | int | None:
        if self.key == "signal_strength":
            return self.coordinator.signal_strength
        return self.coordinator.bluetooth_backend
