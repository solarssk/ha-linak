"""Explicit administrator-only protocol research on an existing native session."""

import logging

from bleak.exc import BleakError
import probatio as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .coordinator import LinakCoordinator
from .motion import MotionError, MotionFailure
from .ownership import has_idasen_conflict
from .protocol import ResearchSection

_LOGGER = logging.getLogger(__name__)
SERVICE_READ_PROTOCOL_INVENTORY = "read_protocol_inventory"


def register_services(hass: HomeAssistant) -> None:
    """Register fixed read sections, not a byte/opcode or settings-write API."""

    async def read_inventory(call: ServiceCall) -> ServiceResponse:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or not isinstance(entry.runtime_data, LinakCoordinator)
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="research_not_ready"
            )
        coordinator = entry.runtime_data
        if (
            not coordinator.connection_wanted
            or coordinator.desk is None
            or not coordinator.desk.connected
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="research_not_ready"
            )
        if has_idasen_conflict(hass, coordinator.address):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="idasen_conflict"
            )
        try:
            return await coordinator.desk.read_protocol_inventory(
                ResearchSection(call.data["section"])
            )
        except MotionError as error:
            if error.reason is MotionFailure.BUSY:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="control_busy"
                ) from error
            _LOGGER.warning("Protocol research read failed: %s", type(error).__name__)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="research_failed"
            ) from error
        except (BleakError, ConnectionError, TimeoutError, ValueError) as error:
            _LOGGER.warning("Protocol research read failed: %s", type(error).__name__)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="research_failed"
            ) from error

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_READ_PROTOCOL_INVENTORY,
        read_inventory,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): str,
                vol.Required("section"): vol.In(
                    [section.value for section in ResearchSection]
                ),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
