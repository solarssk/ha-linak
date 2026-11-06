"""Read-only desk heights and reminder profiles."""

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
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
from .entity import LinakEntity, track_memory_slots, whole_centimeters
from .operation import Phase


# HA requires this coroutine hook even when constructing entities needs no I/O.
async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        LinakSensor(coordinator, "height"),
        LinakSensor(coordinator, "offset"),
        LinakOperationSensor(coordinator, "operation"),
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
    track_memory_slots(
        hass,
        entry,
        coordinator,
        "memory_",
        lambda index: LinakSensor(coordinator, f"memory_{index + 1}"),
        async_add_entities,
    )


class LinakSensor(LinakEntity, SensorEntity):
    def __init__(self, coordinator: LinakCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self.key = key
        if key == "offset":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key in ("height", "offset") or key.startswith("memory_"):
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
            self._attr_suggested_display_precision = 0
        elif key == "reminder_profile":
            self._attr_icon = "mdi:bell-outline"
        else:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        if key == "height":
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self.key in ("height", "offset"):
            return True
        desk = self.coordinator.desk
        group = "memories" if self.key.startswith("memory_") else "reminders"
        return desk is not None and desk.settings_health[group].valid

    @property
    def native_value(self):
        state = self.coordinator.data
        if self.key == "height":
            return whole_centimeters(state.height_cm)
        if self.key == "offset":
            return (
                whole_centimeters(state.offset_raw / 100)
                if state.offset_raw is not None
                else None
            )
        if self.key.startswith("memory_"):
            index = int(self.key.split("_")[1]) - 1
            if index >= len(state.memories) or state.offset_raw is None:
                return None
            raw = state.memories[index].position_raw
            return (
                whole_centimeters((raw + state.offset_raw) / 100)
                if raw is not None
                else None
            )
        if state.reminders is None:
            return None
        if self.key == "reminder_profile":
            return state.reminders.selected_profile
        _, profile, kind = self.key.split("_")
        return state.reminders.profiles_raw[int(profile) - 1][0 if kind == "sit" else 1]


class LinakOperationSensor(LinakEntity, SensorEntity):
    """What the integration is doing with the desk, independent of the Bluetooth link.

    The status stays available when the link drops, so a failed operation keeps its
    reason visible. It describes software state and is not proof of physical arrival.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [phase.value for phase in Phase]

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return self.coordinator.operation.phase.value

    @property
    def extra_state_attributes(self) -> dict[str, float | str] | None:
        status = self.coordinator.operation
        attributes: dict[str, float | str] = {}
        if status.requested_height_cm is not None:
            attributes["requested_height_cm"] = status.requested_height_cm
        if status.reason is not None:
            attributes["reason"] = status.reason.value
        if status.phase is not Phase.IDLE:
            attributes["source"] = status.source.value
        if status.error_code is not None:
            attributes["error_code"] = status.error_code
        last = self.coordinator.last_operation
        if last is not None and not status.settled:
            # Between operations the result is kept here, so idle loses nothing.
            attributes["last_result"] = last.phase.value
            if last.requested_height_cm is not None:
                attributes["last_requested_height_cm"] = last.requested_height_cm
            if last.reason is not None:
                attributes["last_reason"] = last.reason.value
            attributes["last_source"] = last.source.value
            if last.error_code is not None:
                attributes["last_error_code"] = last.error_code
        return attributes or None


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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.key == "signal_strength":
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._refresh_signal, timedelta(seconds=60)
                )
            )

    @callback
    def _refresh_signal(self, _now: datetime) -> None:
        # Repeated coordinator failures can suppress listener notifications.
        # Re-evaluate HA's cached presence even while the desk remains offline.
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @property
    def native_value(self) -> str | int | None:
        if self.key == "signal_strength":
            return self.coordinator.signal_strength
        return self.coordinator.bluetooth_backend
