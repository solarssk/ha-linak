"""Guided setup through HA forms and whole-centimeter entity states."""

from unittest.mock import AsyncMock, patch

from homeassistant.helpers import device_registry as dr, entity_registry as er

import pytest

from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.entity import whole_centimeters
from custom_components.ha_linak.number import LinakTargetHeight
from custom_components.ha_linak.protocol import PositionSample
from test_calibration import (
    BOUNDS,
    DEVICE,
    CalibrationBleak,
    initial_form,
    setup_calibration_entry,
    writes,
)


@pytest.fixture
def desk_transport():
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        yield fake


async def complete_progress(hass, result, options=False):
    await hass.async_block_till_done()
    manager = hass.config_entries.options if options else hass.config_entries.flow
    return await manager.async_configure(result["flow_id"])


async def test_guided_setup_activates_after_name_and_measures_after_range(
    hass, desk_transport
):
    fake = desk_transport
    fake.activation = 0
    identity = fake.identity
    with patch("custom_components.ha_linak.async_setup_entry", return_value=True):
        result = await initial_form(hass, fake, guide=False)
        assert result["step_id"] == "name"
        assert not writes(fake)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Office workspace"}
        )
        result = await complete_progress(hass, result)
        assert result["step_id"] == "finish"
        assert writes(fake) == [b"\x7f\x86\x80\x01" + identity]
        # The owner may use the panel while checking travel bounds. The next
        # measurement must use the new current position, not the old preview.
        fake.position = 1500
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], BOUNDS
        )
        result = await complete_progress(hass, result)
        assert result["step_id"] == "height"
        assert result["description_placeholders"]["height"] == "83"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"height_correct": False}
        )
        assert result["step_id"] == "measure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"measured_height": 75.5}
        )
        assert result["step_id"] == "calibration_confirm"
        assert len(writes(fake)) == 1
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await complete_progress(hass, result)
        assert result["type"] == "create_entry"
        assert result["title"] == "Office workspace"
        assert result["options"] == BOUNDS
        assert fake.offset == 6050
        assert len(writes(fake)) == 2
        assert fake.identity == identity
        await hass.async_block_till_done()


async def test_invalid_name_and_aborted_name_page_never_activate(hass, desk_transport):
    fake = desk_transport
    fake.activation = 0
    result = await initial_form(hass, fake, guide=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "   "}
    )
    assert result["errors"] == {"name": "invalid_name"}
    hass.config_entries.flow.async_abort(result["flow_id"])
    assert not writes(fake)


async def test_failed_preparation_cannot_skip_to_range(hass, desk_transport):
    fake = desk_transport
    fake.activation = 0
    fake.reject_setting = True
    result = await initial_form(hass, fake, guide=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Office"}
    )
    result = await complete_progress(hass, result)
    assert result["step_id"] == "name"
    assert result["errors"] == {"base": "client_preparation_failed"}
    assert len(writes(fake)) == 1
    assert fake.offset == 6800
    assert not hass.config_entries.async_entries("ha_linak")
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_options_can_rename_only_in_home_assistant(hass, desk_transport):
    fake = desk_transport
    entry = await setup_calibration_entry(hass, fake)
    before = list(fake.writes)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ) as reload_entry:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == "menu"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "name"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"name": "Study desk"}
        )
        assert result["type"] == "create_entry"
        assert entry.title == "Study desk"
        device = dr.async_get(hass).async_get_device_by_identifier(
            ("ha_linak", entry.data["address"]), entry.entry_id
        )
        assert device.name_by_user == "Study desk"
        assert entry.runtime_data.name == "Study desk"
        await hass.async_block_till_done()
        reload_entry.assert_not_awaited()
        assert fake.writes == before
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_can_prepare_client_without_changing_height(hass, desk_transport):
    fake = desk_transport
    entry = await setup_calibration_entry(hass, fake)
    fake.activation = 0
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "connect"}
        )
        assert not writes(fake)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        result = await complete_progress(hass, result, options=True)
        assert result["type"] == "create_entry"
        assert fake.activation == 1
        assert fake.offset == 6800
        assert len(writes(fake)) == 1
        await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_ha_records_whole_centimeters_but_keeps_exact_protocol_values(
    hass, desk_transport
):
    entry = await setup_calibration_entry(hass, desk_transport)
    coordinator = entry.runtime_data
    coordinator.desk.state.position = PositionSample(1450, 0)
    coordinator._changed()
    await hass.async_block_till_done()
    assert coordinator.data.height_cm == 82.5
    height_id = er.async_get(hass).async_get_entity_id(
        "sensor", "ha_linak", f"{entry.data['address']}_height"
    )
    assert height_id is not None
    assert hass.states.get(height_id).state == "83"
    for state in hass.states.async_all("sensor"):
        if state.attributes.get("unit_of_measurement") == "cm":
            assert float(state.state).is_integer()
    coordinator.controls = ControlSettings(61.2, 126.2)
    target = LinakTargetHeight(coordinator)
    assert target.native_min_value == 62
    assert target.native_max_value == 126
    assert target.native_step == 1
    assert target.native_value == 83
    assert coordinator.data.offset_raw == 6800
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "value,expected", [(None, None), (75.49, 75), (75.5, 76), (0.43, 0)]
)
def test_presentation_rounding(value, expected):
    assert whole_centimeters(value) == expected


async def test_measurement_page_reports_connection_loss_instead_of_bad_measurement(
    hass, desk_transport
):
    entry = await setup_calibration_entry(hass, desk_transport)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "height"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"height_correct": False}
    )
    entry.runtime_data.last_update_success = False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"measured_height": 75.5}
    )
    assert result["errors"] == {"base": "connection_unavailable"}
    assert result["description_placeholders"]["height"] == "?"
    assert not writes(desk_transport)
    hass.config_entries.options.async_abort(result["flow_id"])
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_offline_entry_can_be_renamed_without_bluetooth(hass, desk_transport):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain="ha_linak", title="Old name", data={"address": "AA:BB:CC:DD:EE:FF"}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "name"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Office"}
    )
    assert result["type"] == "create_entry"
    assert entry.title == "Office"
    assert entry.data["name"] == "Office"
    assert not desk_transport.writes
    await hass.async_block_till_done()


async def test_options_correct_height_does_not_write_panel_settings(
    hass, desk_transport
):
    entry = await setup_calibration_entry(hass, desk_transport)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "height"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"height_correct": True}
    )
    assert result["type"] == "create_entry"
    assert not writes(desk_transport)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_preparation_while_moving_stays_on_form_and_can_retry(
    hass, desk_transport
):
    entry = await setup_calibration_entry(hass, desk_transport)
    coordinator = entry.runtime_data
    coordinator.desk.state.position = PositionSample(1438, 1)
    coordinator._changed()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "connect"}
    )
    before = list(desk_transport.writes)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["step_id"] == "connect"
    assert result["errors"] == {"base": "desk_not_stationary"}
    assert desk_transport.writes == before
    coordinator.desk.state.position = PositionSample(1438, 0)
    coordinator._changed()
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    result = await complete_progress(hass, result, options=True)
    assert result["type"] == "create_entry"
    assert not writes(desk_transport)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_height_correction_is_not_offered_without_bounds(hass, desk_transport):
    entry = await setup_calibration_entry(hass, desk_transport)
    hass.config_entries.async_update_entry(entry, options={})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "height" not in result["menu_options"]
    assert "range" in result["menu_options"]
    assert not writes(desk_transport)
    hass.config_entries.options.async_abort(result["flow_id"])
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_final_height_confirmation_rechecks_bounds_after_movement(
    hass, desk_transport
):
    result = await initial_form(hass, desk_transport)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"minimum_height": 70, "maximum_height": 125}
    )
    result = await complete_progress(hass, result)
    assert result["step_id"] == "height"
    desk_transport.position = 6000
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"height_correct": True}
    )
    assert result["type"] == "progress"
    result = await complete_progress(hass, result)
    assert result["step_id"] == "finish"
    assert result["errors"] == {"base": "invalid_limits"}
    assert not hass.config_entries.async_entries("ha_linak")
    assert not writes(desk_transport)
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_rejected_setting_logs_status_without_identifier(
    hass, desk_transport, caplog
):
    entry = await setup_calibration_entry(hass, desk_transport)
    desk_transport.activation = 0
    desk_transport.reject_setting = True
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "connect"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    result = await complete_progress(hass, result, options=True)
    assert result["errors"] == {"base": "setting_rejected"}
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "custom_components.ha_linak.config_flow"
    ]
    assert any("status=0b" in message for message in messages)
    assert all(desk_transport.identity.hex() not in message for message in messages)
    hass.config_entries.options.async_abort(result["flow_id"])
    assert await hass.config_entries.async_unload(entry.entry_id)
