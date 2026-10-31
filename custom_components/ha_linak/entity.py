"""Shared identity for LINAK entities, including local Bluetooth metadata."""

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
