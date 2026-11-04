"""Optional monitoring-only setup path."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ha_linak.control_settings import ControlSettings
from test_calibration import DEVICE, CalibrationBleak, initial_form, writes
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


async def test_monitoring_only_setup_writes_nothing_and_stores_no_range(
    hass: HomeAssistant, desk_transport
):
    fake = desk_transport
    fake.activation = 0
    with patch("custom_components.ha_linak.async_setup_entry", return_value=True):
        result = await initial_form(hass, fake, guide=False)
        assert result["step_id"] == "name"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Office", "monitoring_only": True}
        )
        assert result["type"] == "create_entry"
    assert not writes(fake)
    assert result["options"] == {}
    assert ControlSettings.from_options(result["options"]) is None
    assert result["title"] == "Office"


async def test_controls_remain_the_default_path(hass: HomeAssistant, desk_transport):
    fake = desk_transport
    fake.activation = 0
    result = await initial_form(hass, fake, guide=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Office"}
    )
    result = await complete_progress(hass, result)
    assert result["step_id"] == "finish"
    assert len(writes(fake)) == 1
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_unchecked_monitoring_option_is_the_control_path(
    hass: HomeAssistant, desk_transport
):
    fake = desk_transport
    fake.activation = 0
    result = await initial_form(hass, fake, guide=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Office", "monitoring_only": False}
    )
    result = await complete_progress(hass, result)
    assert result["step_id"] == "finish"
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_invalid_name_blocks_monitoring_only_entry(
    hass: HomeAssistant, desk_transport
):
    fake = desk_transport
    result = await initial_form(hass, fake, guide=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "  ", "monitoring_only": True}
    )
    assert result["errors"] == {"name": "invalid_name"}
    assert not hass.config_entries.async_entries("ha_linak")
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_monitoring_entry_loads_and_can_be_upgraded_with_a_range(
    hass: HomeAssistant, desk_transport
):
    fake = desk_transport
    fake.activation = 0
    result = await initial_form(hass, fake, guide=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Office", "monitoring_only": True}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries("ha_linak")[0]
    assert entry.state is ConfigEntryState.LOADED
    assert not writes(fake)

    options = await hass.config_entries.options.async_init(entry.entry_id)
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {"next_step_id": "range"}
    )
    assert options["step_id"] == "range"
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {"minimum_height": 70, "maximum_height": 125}
    )
    assert options["type"] == "create_entry"
    assert ControlSettings.from_options(entry.options) is not None
