"""Native centimeter target with explicit movement, without target restoration."""

from homeassistant.components.number import NumberEntity, NumberMode, NumberDeviceClass
from homeassistant.const import UnitOfLength

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import LinakEntity


# HA requires this coroutine hook even when constructing entities needs no I/O.
async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([LinakTargetHeight(coordinator)])


class LinakTargetHeight(LinakEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_native_step = 0.1
    _attr_device_class = NumberDeviceClass.DISTANCE

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "target_height")
        settings = coordinator.controls
        self._attr_native_min_value = settings.minimum_cm if settings else 0
        self._attr_native_max_value = settings.maximum_cm if settings else 0

    @property
    def available(self) -> bool:
        return self.coordinator.controls is not None and super().available

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.height_cm

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_move_to_cm(value)
        self.async_write_ha_state()
