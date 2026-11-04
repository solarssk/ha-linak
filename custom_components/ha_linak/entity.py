"""Shared identity for LINAK entities, including local Bluetooth metadata."""

from collections.abc import Callable
import math

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LinakCoordinator


class LinakEntity(CoordinatorEntity[LinakCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LinakCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, format_mac(coordinator.address))},
            name=coordinator.name,
            manufacturer="LINAK",
            model="DPG",
        )


def whole_centimeters(value: float | None) -> int | None:
    """Round only HA-facing heights; protocol and movement retain exact values."""
    return math.floor(value + 0.5) if value is not None else None


def track_memory_slots(
    hass: HomeAssistant,
    entry,
    coordinator: LinakCoordinator,
    unique_prefix: str,
    factory: Callable[[int], LinakEntity],
    async_add_entities,
) -> None:
    """Create one entity per stored position, also when the desk is not readable.

    A persisted release starts without capabilities. Slots registered earlier are
    restored, and any slot the first connection reveals is added afterwards.
    """
    known = coordinator.data.capabilities is not None
    if known:
        created = len(coordinator.data.memories)
    else:
        registry = er.async_get(hass)
        prefix = f"{coordinator.address}_{unique_prefix}"
        created = sum(
            1
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
            if item.unique_id.startswith(prefix)
        )
    async_add_entities([factory(index) for index in range(created)])

    def add_revealed_slots() -> None:
        nonlocal created
        count = len(coordinator.data.memories)
        if count > created:
            async_add_entities([factory(index) for index in range(created, count)])
            created = count

    entry.async_on_unload(coordinator.async_add_listener(add_revealed_slots))
