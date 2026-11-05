"""Explicit reminder configuration through the existing desk owner."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import LinakReminderEntity

OPTIONS = ["off", "profile_1", "profile_2", "profile_3"]


async def async_setup_entry(  # NOSONAR(S7503) HA coroutine contract
    _hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [LinakReminderProfileSelect(entry.runtime_data, "reminder_profile")]
    )


class LinakReminderProfileSelect(LinakReminderEntity, SelectEntity):
    """Assign a profile; the existing profile sensor retains its identity."""

    _attr_options = OPTIONS
    _attr_icon = "mdi:bell-cog"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def current_option(self) -> str | None:
        reminders = self.coordinator.data.reminders
        return (
            OPTIONS[reminders.selected_profile]
            if self.available and reminders
            else None
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_reminder_profile(OPTIONS.index(option))
