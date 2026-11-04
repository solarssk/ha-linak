"""Native centimeter target with explicit movement, without target restoration."""

import math
from collections.abc import Callable

from homeassistant.components.number import NumberEntity, NumberMode, NumberDeviceClass
from homeassistant.const import UnitOfLength

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import LinakEntity, whole_centimeters


# HA requires this coroutine hook even when constructing entities needs no I/O.
async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([LinakTargetHeight(coordinator)])


class LinakTargetHeight(LinakEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_native_step = 1
    _attr_device_class = NumberDeviceClass.DISTANCE

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "target_height")
        settings = coordinator.controls
        self._attr_native_min_value = math.ceil(settings.minimum_cm) if settings else 0
        self._attr_native_max_value = math.floor(settings.maximum_cm) if settings else 0
        self._settled_value = self._measured_value()
        self._candidate: tuple[int, int | None] | None = None
        self._cancel_settle: Callable[[], None] | None = None

    def _measured_value(self) -> float | None:
        value = whole_centimeters(self.coordinator.data.height_cm)
        if value is None:
            return None
        return max(self.native_min_value, min(value, self.native_max_value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._cancel_pending_settle)

    @callback
    def _cancel_pending_settle(self) -> None:
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None
        self._candidate = None

    @callback
    def _stationary(self) -> bool:
        """The desk stands still, or this integration just finished moving it."""
        desk = self.coordinator.desk
        position = self.coordinator.data.position
        if desk is None or desk.control_busy or position is None:
            return False
        # The last sample of our own move can carry residual speed, and no later
        # one may arrive; the move's Stop has already been sent.
        return position.speed_raw == 0 or desk.operation.status.settled

    @callback
    def _handle_coordinator_update(self) -> None:
        position = self.coordinator.data.position
        if not self.available or position is None or not self._stationary():
            self._cancel_pending_settle()
        else:
            candidate = (position.position_raw, self.coordinator.data.offset_raw)
            if self._measured_value() == self._settled_value:
                self._cancel_pending_settle()
            elif candidate != self._candidate:
                self._cancel_pending_settle()
                self._candidate = candidate
                self._cancel_settle = async_call_later(self.hass, 0.5, self._settle)
        super()._handle_coordinator_update()

    @callback
    def _settle(self, _now) -> None:
        self._cancel_settle = None
        position = self.coordinator.data.position
        if (
            self.available
            and position is not None
            and self._stationary()
            and self._candidate
            == (position.position_raw, self.coordinator.data.offset_raw)
        ):
            self._settled_value = self._measured_value()
            self.async_write_ha_state()
        self._candidate = None

    @property
    def available(self) -> bool:
        return (
            self.coordinator.controls is not None
            and self.native_min_value <= self.native_max_value
            and super().available
        )

    @property
    def native_value(self) -> float | None:
        return self._settled_value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_move_to_cm(value)
        self._cancel_pending_settle()
        self._settled_value = self._measured_value()
        self.async_write_ha_state()
