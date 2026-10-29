"""Real Home Assistant setup, entities and unload with a fake BLE transport."""

from types import SimpleNamespace
from unittest.mock import patch
from bleak.backends.device import BLEDevice
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.protocol import SERVICE_UUID
from test_client import FakeBleak

ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE = BLEDevice(ADDRESS, "Desk", {})


async def test_setup_reads_centimeters_and_unload_disconnects(hass):
    fake = FakeBleak()

    async def connect(*args, **kwargs):
        return fake

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test desk",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=connect,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.data.height_cm == 82.38
        states = hass.states.async_all("sensor")
        assert len(states) == 13
        assert any(
            s.state == "82.38" and s.attributes.get("unit_of_measurement") == "cm"
            for s in states
        )
        assert not hass.states.async_all("cover")
        fake.is_connected = False
        entry.runtime_data._changed()
        await hass.async_block_till_done()
        assert all(s.state == "unavailable" for s in hass.states.async_all("sensor"))
        fake.is_connected = True
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert entry.runtime_data.last_update_success
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert not fake.is_connected


async def test_config_flow_tests_connection_and_prevents_duplicates(hass):
    fake = FakeBleak()
    info = SimpleNamespace(
        address=ADDRESS, name="Desk", device=DEVICE, service_uuids=[SERVICE_UUID]
    )

    async def connect(*args, **kwargs):
        return fake

    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=connect,
        ),
        patch("custom_components.ha_linak.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == "form"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_ADDRESS: ADDRESS}
        assert not fake.is_connected
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=info
        )
        assert result["type"] == "abort"
        assert result["reason"] == "already_configured"


async def test_no_devices_has_clear_abort(hass):
    with patch(
        "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["reason"] == "no_devices_found"


async def test_failed_validation_returns_form_and_closes_link(hass):
    fake = FakeBleak()
    fake.fail_command = 0x80
    info = SimpleNamespace(
        address=ADDRESS, name="Desk", device=DEVICE, service_uuids=[SERVICE_UUID]
    )

    async def connect(*args, **kwargs):
        return fake

    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=connect,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
    assert not fake.is_connected


async def test_diagnostics_do_not_contain_device_identifiers(hass):
    from custom_components.ha_linak.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    from custom_components.ha_linak.client import DeskState
    import json

    entry = MockConfigEntry(
        domain=DOMAIN, title="Private location", data={CONF_ADDRESS: ADDRESS}
    )
    entry.runtime_data = SimpleNamespace(
        desk=None, last_update_success=False, data=DeskState()
    )
    result = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(result)
    assert ADDRESS not in serialized
    assert "Private location" not in serialized
