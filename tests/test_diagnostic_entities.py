"""Desk readings, opt-in Bluetooth details and connection failure semantics."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends import BleakBackend
from homeassistant.const import CONF_ADDRESS, EntityCategory
from homeassistant.helpers import entity_registry as er, device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.coordinator import LinakCoordinator
from custom_components.ha_linak.binary_sensor import LinakConnectionSensor
from custom_components.ha_linak.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_linak.sensor import LinakDiagnosticSensor
from test_client import FakeBleak
from test_integration import ADDRESS, DEVICE


async def test_categories_registry_identity_and_optional_diagnostics(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Desk", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    memory = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{ADDRESS}_memory_1",
        config_entry=entry,
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    registry.async_update_entity(memory.entity_id, name="My saved height")
    # Existing enabled entries override the default-disabled setting.
    signal = registry.async_get_or_create(
        "sensor", DOMAIN, f"{ADDRESS}_signal_strength", config_entry=entry
    )
    backend = registry.async_get_or_create(
        "sensor", DOMAIN, f"{ADDRESS}_bluetooth_backend", config_entry=entry
    )
    fake = FakeBleak()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_address_present",
            return_value=True,
        ),
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_last_service_info",
            return_value=SimpleNamespace(
                rssi=-65, name="Private desk", address=ADDRESS, source="Private proxy"
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(entries) == 16
        by_key = {item.unique_id.removeprefix(ADDRESS + "_"): item for item in entries}
        for key in [
            "height",
            "memory_1",
            "memory_2",
            "memory_3",
            "memory_4",
            "reminder_profile",
            "reminder_1_sit",
            "reminder_3_stand",
        ]:
            assert by_key[key].entity_category is None
        assert registry.async_get(memory.entity_id).name == "My saved height"
        for key in ["offset", "connection", "signal_strength", "bluetooth_backend"]:
            assert by_key[key].entity_category == EntityCategory.DIAGNOSTIC
        assert hass.states.get(signal.entity_id).state == "-65"
        assert (
            hass.states.get(signal.entity_id).attributes["unit_of_measurement"] == "dBm"
        )
        assert hass.states.get(backend.entity_id).state == "bleak_esphome"
        connected_id = by_key["connection"].entity_id
        assert hass.states.get(connected_id).state == "on"
        device = dr.async_get(hass).async_get(by_key["height"].device_id)
        assert (dr.CONNECTION_BLUETOOTH, dr.format_mac(ADDRESS)) in device.connections
        assert device.name == "Desk"
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["bluetooth"] == {
            "signal_strength": -65,
            "backend": "bleak_esphome",
        }
        serialized = json.dumps(result)
        assert ADDRESS not in serialized
        assert "Private" not in serialized
        # Connection goes off while RSSI remains valid from a present advertiser.
        fake.is_connected = False
        entry.runtime_data._changed()
        await hass.async_block_till_done()
        assert hass.states.get(connected_id).state == "off"
        assert hass.states.get(by_key["height"].entity_id).state == "unavailable"
        assert hass.states.get(signal.entity_id).state == "-65"
        assert hass.states.get(backend.entity_id).state == "unavailable"
        fake.is_connected = True
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(connected_id).state == "on"
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_optional_entities_start_disabled_but_connection_is_enabled(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Desk", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=FakeBleak()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entries = er.async_entries_for_config_entry(registry, entry.entry_id)
        for key in ("signal_strength", "bluetooth_backend"):
            entity = next(
                item for item in entries if item.unique_id == f"{ADDRESS}_{key}"
            )
            assert entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION
            assert hass.states.get(entity.entity_id) is None
        assert len(hass.states.async_all("binary_sensor")) == 1
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "present,info,expected",
    [
        (False, SimpleNamespace(rssi=-50), None),
        (True, None, None),
        (True, SimpleNamespace(rssi=127), None),
        (True, SimpleNamespace(rssi=-76), -76),
    ],
)
async def test_rssi_requires_present_connectable_advertisement(
    hass, present, info, expected
):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS})
    coordinator = LinakCoordinator(hass, entry)
    sensor = LinakDiagnosticSensor(coordinator, "signal_strength")
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_address_present",
            return_value=present,
        ) as presence,
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_last_service_info",
            return_value=info,
        ),
    ):
        assert sensor.native_value == expected
        assert sensor.available == (expected is not None)
        presence.assert_called_with(hass, ADDRESS, connectable=True)


@pytest.mark.parametrize(
    "backend,connected,expected",
    [
        (BleakBackend.BLUEZ_DBUS, True, "bluez_dbus"),
        ("bleak_esphome", True, "bleak_esphome"),
        ("Private proxy name", True, "other"),
        ("bluez_dbus", False, None),
    ],
)
async def test_backend_is_active_category_not_adapter_identity(
    hass, backend, connected, expected
):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS})
    coordinator = LinakCoordinator(hass, entry)
    coordinator.desk = SimpleNamespace(
        client=SimpleNamespace(backend_id=backend, is_connected=connected)
    )
    sensor = LinakDiagnosticSensor(coordinator, "bluetooth_backend")
    assert sensor.native_value == expected
    assert sensor.available == (expected is not None)


async def test_no_session_has_no_backend_and_connection_is_off(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS})
    coordinator = LinakCoordinator(hass, entry)
    assert coordinator.bluetooth_backend is None
    connection = LinakConnectionSensor(coordinator, "connection")
    assert connection.available
    assert not connection.is_on
    coordinator.desk = SimpleNamespace(client=None)
    assert coordinator.bluetooth_backend is None
