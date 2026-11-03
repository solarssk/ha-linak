"""Cross-integration ownership checks use synthetic registry entries only."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import (
    ConfigEntryDisabler,
    ConfigEntryState,
    SOURCE_IGNORE,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_linak.config_flow import LinakConfigFlow, LinakOptionsFlow
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.ownership import has_idasen_conflict
from test_native_controls import ADDRESS, DEVICE, OPTIONS, setup_entry


def ikea_entry(hass, **kwargs):
    values = dict(
        domain="idasen_desk", title="Synthetic IKEA desk", data={CONF_ADDRESS: ADDRESS}
    )
    values.update(kwargs)
    entry = MockConfigEntry(**values)
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize(
    "address",
    [ADDRESS, ADDRESS.lower(), "aa-bb-cc-dd-ee-ff", "aabb.ccdd.eeff", "AABBCCDDEEFF"],
)
def test_normalized_address_conflicts_without_touching_ikea(hass, address):
    other = ikea_entry(hass, data={CONF_ADDRESS: address})
    assert has_idasen_conflict(hass, ADDRESS)
    assert other.disabled_by is None
    assert other.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize("data", [{}, {CONF_ADDRESS: "invalid"}, {CONF_ADDRESS: None}])
def test_unique_id_is_fallback_for_missing_or_invalid_data(hass, data):
    ikea_entry(hass, data=data, unique_id=ADDRESS.lower())
    assert has_idasen_conflict(hass, ADDRESS)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"disabled_by": ConfigEntryDisabler.USER},
        {"source": SOURCE_IGNORE, "data": {}, "unique_id": ADDRESS},
        {"data": {CONF_ADDRESS: "11:22:33:44:55:66"}, "unique_id": ADDRESS},
        {"data": {CONF_ADDRESS: "invalid"}, "unique_id": "invalid"},
        {"domain": "other_desk"},
    ],
)
def test_disabled_ignored_different_and_invalid_entries_do_not_conflict(hass, kwargs):
    ikea_entry(hass, **kwargs)
    assert not has_idasen_conflict(hass, ADDRESS)


def test_invalid_linak_address_does_not_match_missing_ikea_address(hass):
    ikea_entry(hass, data={})
    assert not has_idasen_conflict(hass, "invalid")


async def test_initial_runtime_setup_reports_conflict_before_any_radio_work(hass):
    other = ikea_entry(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Desk", data={CONF_ADDRESS: ADDRESS})
    entry.add_to_hass(hass)
    with patch("custom_components.ha_linak.client.establish_connection") as connect:
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == "idasen_conflict"
    connect.assert_not_called()
    assert other.disabled_by is None
    assert other.state is ConfigEntryState.NOT_LOADED
    await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_flow_reports_conflict_without_looking_up_device(hass):
    ikea_entry(hass)
    flow = LinakConfigFlow()
    flow.hass = hass
    flow._address = ADDRESS
    with patch.object(flow, "_device") as device:
        assert await flow._validate() == "idasen_conflict"
    device.assert_not_called()
    assert flow._desk is None
    flow._error = "idasen_conflict"
    assert (await flow.async_step_retry())["errors"] == {"base": "idasen_conflict"}


async def test_wizard_rechecks_owner_before_preparation_and_final_handoff(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    flow = LinakConfigFlow()
    flow.hass = hass
    flow._address = ADDRESS
    flow._desk = entry.runtime_data.desk
    ikea_entry(hass)
    assert await flow._apply_calibration() == "idasen_conflict"
    assert not fake.is_connected
    # The final form must not create a LINAK entry if ownership changed meanwhile.
    flow._abort_if_unique_id_configured = Mock()
    assert (await flow.async_step_save_range())["reason"] == "idasen_conflict"
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("action", ["target", "memory"])
async def test_new_motion_rejected_but_stop_remains_available(hass, action):
    entry, fake = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    other = ikea_entry(hass)
    fake.writes.clear()
    with pytest.raises(HomeAssistantError) as error:
        if action == "target":
            await coordinator.async_move_to_cm(84)
        else:
            await coordinator.async_move_to_memory(0)
    assert error.value.translation_key == "idasen_conflict"
    assert not fake.writes
    await coordinator.async_stop()
    assert fake.writes
    assert other.disabled_by is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_runtime_refresh_releases_own_link_and_recovers_after_ikea_disabled(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    other = ikea_entry(hass)
    fake.writes.clear()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.last_exception.translation_key == "idasen_conflict"
    assert not fake.is_connected
    assert not fake.writes
    await hass.config_entries.async_set_disabled_by(
        other.entry_id, ConfigEntryDisabler.USER
    )
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=lambda *a, **k: fake.reconnect(),
        ),
    ):
        await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert fake.is_connected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_calibration_rechecks_owner_before_write(hass):
    entry, _ = await setup_entry(hass, OPTIONS)
    ikea_entry(hass)
    flow = LinakOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    flow._calibration = SimpleNamespace()
    with patch.object(
        entry.runtime_data.desk, "calibrate_height", new_callable=AsyncMock
    ) as calibrate:
        assert await flow._apply_calibration() == "idasen_conflict"
    calibrate.assert_not_awaited()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_conflict_during_motion_preserves_owned_cleanup_and_stop(hass):
    import asyncio

    entry, fake = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    fake.stall = True
    movement = asyncio.create_task(coordinator.async_move_to_cm(84))
    try:
        async with asyncio.timeout(1):
            await fake.target_written.wait()
        ikea_entry(hass)
        await coordinator.async_refresh()
        assert fake.is_connected
        assert coordinator.desk.control_busy
        await coordinator.async_stop()
        await movement
        assert fake.is_connected
        assert not coordinator.desk.control_busy
    finally:
        if not movement.done():
            movement.cancel()
        await asyncio.gather(movement, return_exceptions=True)
        await hass.config_entries.async_unload(entry.entry_id)
