"""Real Home Assistant setup, entities and unload with a fake BLE transport."""

import pytest
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


@pytest.fixture(autouse=True)
def available_bluetooth_device():
    with patch(
        "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
        return_value=DEVICE,
    ):
        yield


async def finish_progress(hass, result):
    assert result["type"] == "progress"
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(result["flow_id"])


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
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=True,
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
        result = await finish_progress(hass, result)
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
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=True,
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
        result = await finish_progress(hass, result)
    assert result["type"] == "form"
    assert result["step_id"] == "retry"
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


@pytest.mark.parametrize(
    "failure,error",
    [
        (TimeoutError, "timeout"),
        (ValueError, "unsupported_device"),
        (RuntimeError, "unknown"),
    ],
)
async def test_validation_errors_show_retry_and_allow_a_new_attempt(
    hass, failure, error
):
    from unittest.mock import AsyncMock

    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )
    fake = FakeBleak()
    connect = AsyncMock(return_value=fake)
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch("custom_components.ha_linak.client.establish_connection", connect),
        patch(
            "custom_components.ha_linak.config_flow.DeskClient.refresh",
            side_effect=failure,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        result = await finish_progress(hass, result)
        assert result["step_id"] == "retry"
        assert result["errors"] == {"base": error}
    with (
        patch("custom_components.ha_linak.client.establish_connection", connect),
        patch("custom_components.ha_linak.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await finish_progress(hass, result)
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()


async def test_progress_revisit_does_not_start_second_connection_and_abort_cleans_up(
    hass,
):
    import asyncio
    from unittest.mock import AsyncMock

    started = asyncio.Event()
    fake = FakeBleak()
    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )

    async def subscribe(*args):
        started.set()
        await asyncio.Future()

    fake.start_notify = subscribe
    connect = AsyncMock(return_value=fake)
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch("custom_components.ha_linak.client.establish_connection", connect),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        assert result["type"] == "progress"
        await started.wait()
        again = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert again["type"] == "progress"
        connect.assert_awaited_once()
        hass.config_entries.flow.async_abort(result["flow_id"])
        await hass.async_block_till_done()
        assert not fake.is_connected
        assert not hass.config_entries.async_entries(DOMAIN)


async def test_passive_discovery_is_rejected_without_connecting(hass):
    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=False,
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "bluetooth"}, data=info
    )
    assert result["type"] == "abort"
    assert result["reason"] == "not_connectable"


async def test_discovery_requires_confirmation_before_connection(hass):
    from unittest.mock import AsyncMock

    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=BLEDevice(ADDRESS, "Stale", {}),
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )
    connect = AsyncMock(return_value=FakeBleak())
    with (
        patch("custom_components.ha_linak.client.establish_connection", connect),
        patch("custom_components.ha_linak.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=info
        )
        assert result["type"] == "form"
        assert hass.config_entries.flow.async_get(result["flow_id"])["context"][
            "title_placeholders"
        ] == {"name": "Desk"}
        connect.assert_not_awaited()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        result = await finish_progress(hass, result)
        assert result["type"] == "create_entry"
        assert connect.call_args.args[1] is DEVICE
        assert connect.call_args.kwargs["ble_device_callback"]() is DEVICE
        await hass.async_block_till_done()


async def test_device_disappearing_before_validation_gets_retry(hass):
    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        result = await finish_progress(hass, result)
        assert result["step_id"] == "retry"
        assert result["errors"] == {"base": "cannot_connect"}


async def test_hanging_initial_entry_setup_becomes_ha_setup_retry(hass):
    import asyncio
    from unittest.mock import AsyncMock
    from homeassistant.config_entries import ConfigEntryState

    fake = FakeBleak()

    async def subscribe(*args):
        await asyncio.Future()

    fake.start_notify = subscribe
    entry = MockConfigEntry(
        domain=DOMAIN, title="Desk", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert not fake.is_connected
        assert not hass.states.async_all("sensor")


async def test_failed_disconnect_after_validation_never_creates_entry(hass):
    from unittest.mock import AsyncMock

    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch("custom_components.ha_linak.config_flow.DeskClient.refresh", AsyncMock()),
        patch(
            "custom_components.ha_linak.config_flow.DeskClient.disconnect",
            AsyncMock(side_effect=ConnectionError),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        result = await finish_progress(hass, result)
        assert result["step_id"] == "retry"
        assert result["errors"] == {"base": "cannot_connect"}
        assert not hass.config_entries.async_entries(DOMAIN)
