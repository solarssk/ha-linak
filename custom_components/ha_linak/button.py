"""Stop and drive-to-memory controls on the coordinator's existing connection."""

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import LinakEntity


# HA requires this coroutine hook even when constructing entities needs no I/O.
async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.controls is not None:
        async_add_entities(
            [LinakStop(coordinator)]
            + [
                LinakMemory(coordinator, index)
                for index in range(len(coordinator.data.memories))
            ]
        )


class LinakStop(LinakEntity, ButtonEntity):
    _attr_icon = "mdi:stop"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "stop")

    @property
    def available(self) -> bool:
        desk = self.coordinator.desk
        return desk is not None and (desk.connected or desk.control_busy)

    async def async_press(self) -> None:
        await self.coordinator.async_stop()


class LinakMemory(LinakEntity, ButtonEntity):
    _attr_icon = "mdi:table-chair"

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, f"go_to_memory_{index + 1}")
        self.index = index

    @property
    def available(self) -> bool:
        memories = self.coordinator.data.memories
        return (
            super().available
            and self.index < len(memories)
            and memories[self.index].position_raw is not None
        )

    async def async_press(self) -> None:
        state = self.coordinator.data
        if self.index >= len(state.memories) or state.offset_raw is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="memory_unavailable"
            )
        raw = state.memories[self.index].position_raw
        if raw is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="memory_unavailable"
            )
        await self.coordinator.async_move_to_memory(self.index)
