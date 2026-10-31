"""Native centimeter target with explicit movement, without target restoration."""

from homeassistant.components.number import NumberEntity, NumberMode, NumberDeviceClass
from homeassistant.const import UnitOfLength

from .entity import LinakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    if coordinator.controls is not None:
        async_add_entities([LinakTargetHeight(coordinator)])


class LinakTargetHeight(LinakEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_native_step = 0.1
    _attr_device_class = NumberDeviceClass.DISTANCE

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "target_height")
        self._target: float | None = None
        self._attr_native_min_value = coordinator.controls.minimum_cm
        self._attr_native_max_value = coordinator.controls.maximum_cm

    @property
    def native_value(self) -> float | None:
        # Unknown until a request succeeds. Never substitute the measured height.
        return self._target

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_move_to_cm(value)
        self._target = value
        self.async_write_ha_state()
