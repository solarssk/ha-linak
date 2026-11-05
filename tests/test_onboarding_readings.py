"""Onboarding readings never supply or infer measured command bounds."""

from dataclasses import replace
from unittest.mock import patch

import probatio as vol
import pytest
from homeassistant.helpers import config_validation as cv
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ha_linak.config_flow import (
    _range_schema,
    _reading_placeholders,
)
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.protocol import StoredPosition
from test_calibration import (
    BOUNDS,
    DEVICE,
    CalibrationBleak,
    initial_form,
    ready,
    setup_calibration_entry,
    writes,
)
from test_guided_setup import complete_progress


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


def serialized_bounds(options):
    return vol.to_field_list(
        _range_schema(options), custom_serializer=cv.custom_serializer
    )


def test_unmeasured_bounds_are_required_but_serialize_as_null_not_zero():
    fields = serialized_bounds({})
    assert {field["name"] for field in fields} == set(BOUNDS)
    for field in fields:
        assert field["required"]
        assert "default" in field
        assert field["default"] is None
        assert field["selector"]["number"] == {
            "mode": "box",
            "step": 0.1,
            "unit_of_measurement": "cm",
        }
    schema = _range_schema({})
    with pytest.raises(vol.Invalid):
        schema({})
    assert _range_schema({})(BOUNDS) == BOUNDS


@pytest.mark.parametrize(
    "values",
    [BOUNDS, {"minimum_height": 61.2}, {"minimum_height": 0, "maximum_height": 0}],
)
def test_existing_or_submitted_bounds_are_preserved_exactly(values):
    assert {field["name"]: field["default"] for field in serialized_bounds(values)} == {
        key: values.get(key) for key in BOUNDS
    }


async def test_first_form_shows_existing_memories_before_preparation(
    hass, desk_transport
):
    desk_transport.activation = 0
    result = await initial_form(hass, desk_transport, guide=False)
    assert result["step_id"] == "name"
    assert result["description_placeholders"] == {
        "height": "82",
        "memory_1": "80.04 cm",
        "memory_2": "82.38 cm",
        "memory_3": "119.52 cm",
        "memory_4": "124.96 cm",
    }
    assert [data[1] for _, data in desk_transport.writes] == [
        0x80,
        0x81,
        0x89,
        0x80,
        0x8A,
        0x80,
        0x8B,
        0x80,
        0x8C,
        0x88,
    ]
    assert not writes(desk_transport)
    assert not hass.config_entries.async_entries("ha_linak")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await complete_progress(hass, result)
    assert result["step_id"] == "finish"
    assert result["description_placeholders"]["memory_1"] == "80.04 cm"
    assert all(field["default"] is None for field in serialized_bounds({}))
    # Even though favorites exist, missing bounds cannot finish control setup.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"minimum_height": 0, "maximum_height": 0}
    )
    assert result["step_id"] == "finish"
    assert result["errors"] == {"base": "invalid_limits"}
    assert not hass.config_entries.async_entries("ha_linak")
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.parametrize("slots", [0, 1, 2, 4])
async def test_readings_keep_slot_identity_empty_equal_and_unsupported(slots):
    desk, _ = await ready()
    state = desk.state
    state.capabilities = replace(state.capabilities, memory_slots=slots)
    state.memories = [
        StoredPosition(position, 0) for position in (None, 0, 1000, 1000)[:slots]
    ]
    placeholders = _reading_placeholders(state, desk)
    expected = ["-", "68.00 cm", "78.00 cm", "78.00 cm"]
    assert [placeholders[f"memory_{index + 1}"] for index in range(4)] == (
        expected[:slots] + ["n/a"] * (4 - slots)
    )
    await desk.disconnect()


@pytest.mark.parametrize("failure", ["invalid_group", "incomplete", "disconnected"])
async def test_unavailable_group_never_shows_retained_values(failure):
    desk, fake = await ready()
    if failure == "invalid_group":
        desk.settings_health["memories"].valid = False
    elif failure == "incomplete":
        desk.state.memories.pop()
    else:
        fake.is_connected = False
    placeholders = _reading_placeholders(desk.state, desk)
    assert [placeholders[f"memory_{index}"] for index in range(1, 5)] == ["?"] * 4
    assert placeholders["height"] == ("?" if failure == "disconnected" else "82")
    await desk.disconnect()


async def test_calibration_invalidates_saved_height_preview_until_reread():
    from custom_components.ha_linak.calibration import HeightCalibration

    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    state = await desk.calibrate_height(proposal)
    assert _reading_placeholders(state, desk)["memory_1"] == "?"
    await desk.refresh(allow_partial_settings=True)
    assert _reading_placeholders(desk.state, desk)["memory_1"] == "73.16 cm"
    assert fake.offset == 6112
    await desk.disconnect()


@pytest.mark.parametrize("has_bounds", [False, True])
async def test_configure_range_shows_memories_without_new_reads_or_guessed_bounds(
    hass, desk_transport, has_bounds
):
    entry = await setup_calibration_entry(hass, desk_transport)
    hass.config_entries.async_update_entry(entry, options=BOUNDS if has_bounds else {})
    before = list(desk_transport.writes)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "range"}
    )
    assert result["description_placeholders"]["memory_4"] == "124.96 cm"
    fields = vol.to_field_list(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    assert {field["name"]: field["default"] for field in fields} == (
        BOUNDS if has_bounds else dict.fromkeys(BOUNDS)
    )
    assert ControlSettings.from_options(entry.options) == (
        ControlSettings.from_options(BOUNDS) if has_bounds else None
    )
    assert desk_transport.writes == before
    hass.config_entries.options.async_abort(result["flow_id"])
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("failure", ["update_failed", "memories_invalid", "link_lost"])
async def test_configure_range_hides_unavailable_memories(
    hass, desk_transport, failure
):
    entry = await setup_calibration_entry(hass, desk_transport)
    if failure == "update_failed":
        entry.runtime_data.last_update_success = False
    elif failure == "memories_invalid":
        entry.runtime_data.desk.settings_health["memories"].valid = False
    else:
        desk_transport.is_connected = False
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "range"}
    )
    assert all(
        result["description_placeholders"][f"memory_{index}"] == "?"
        for index in range(1, 5)
    )
    hass.config_entries.options.async_abort(result["flow_id"])
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_offline_unloaded_entry_can_open_range_without_cached_readings(hass):
    entry = MockConfigEntry(domain="ha_linak", title="Desk", data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "range"}
    )
    assert set(result["description_placeholders"].values()) == {"?"}
    hass.config_entries.options.async_abort(result["flow_id"])
