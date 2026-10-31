"""Native Bluetooth names in discovery, validated entries and device metadata."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_linak.client import DEVICE_NAME_UUID
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.naming import desk_name, discovery_title
from custom_components.ha_linak.protocol import SERVICE_UUID
from test_client import FakeBleak
from test_integration import ADDRESS, finish_progress


class NamedDesk(FakeBleak):
    def __init__(self, payload=b"Office desk"):
        super().__init__()
        self.payload = payload
        self.name_reads = 0
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: (
                SimpleNamespace(properties=["read"])
                if uuid == DEVICE_NAME_UUID
                else None
            )
        )

    async def read_gatt_char(self, uuid):
        if uuid == DEVICE_NAME_UUID:
            assert self.paired
            self.name_reads += 1
            return bytearray(self.payload)
        return await super().read_gatt_char(uuid)


def test_generic_and_address_names_do_not_hide_native_names():
    assert desk_name(ADDRESS, "LINAK", ADDRESS, " Office desk ") == "Office desk"
    assert desk_name(ADDRESS, "linak", None, "  ") == "LINAK"
    assert discovery_title(ADDRESS, "Office desk") == "Office desk (EEFF)"
    assert discovery_title(ADDRESS, ADDRESS) == "LINAK (EEFF)"


@pytest.mark.parametrize(
    "advertised,device_name,current_name,latest_name,expected",
    [
        (ADDRESS, ADDRESS, None, "Office desk", "Office desk"),
        ("LINAK", "Office desk", None, None, "Office desk"),
        (ADDRESS, ADDRESS, "Office desk", None, "Office desk"),
        (ADDRESS, ADDRESS, None, None, "LINAK"),
    ],
)
async def test_discovery_uses_cached_native_name_without_connecting(
    hass, advertised, device_name, current_name, latest_name, expected
):
    info = SimpleNamespace(
        address=ADDRESS,
        name=advertised,
        device=BLEDevice(ADDRESS, device_name, {}),
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )
    latest = (
        SimpleNamespace(name=latest_name, device=BLEDevice(ADDRESS, latest_name, {}))
        if latest_name
        else None
    )
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_last_service_info",
            return_value=latest,
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=BLEDevice(ADDRESS, current_name, {}) if current_name else None,
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            new_callable=AsyncMock,
        ) as connect,
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_request_active_scan",
            new_callable=AsyncMock,
        ) as scan,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=info
        )
        assert result["type"] == "form"
        context = hass.config_entries.flow.async_get(result["flow_id"])["context"]
        assert context["title_placeholders"] == {"name": expected + " (EEFF)"}
        options = result["data_schema"].schema[CONF_ADDRESS].config["options"]
        assert options[0]["label"] == f"{expected} ({ADDRESS})"
        connect.assert_not_awaited()
        scan.assert_not_awaited()


async def test_validated_entry_uses_gap_name_when_discovery_has_only_fallback(hass):
    fake = NamedDesk()
    device = BLEDevice(ADDRESS, ADDRESS, {})
    info = SimpleNamespace(
        address=ADDRESS,
        name=ADDRESS,
        device=device,
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
            return_value=device,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch("custom_components.ha_linak.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        result = await finish_progress(hass, result)
        assert result["title"] == "Office desk"
        assert fake.name_reads == 1


@pytest.mark.parametrize(
    "title,user_name,payload,expected",
    [
        ("LINAK", None, b"Office desk", "Office desk"),
        ("My desk", None, b"Office desk", "My desk"),
        ("LINAK", "My workspace", b"Office desk", "Office desk"),
        ("LINAK", None, b"", "LINAK"),
    ],
)
async def test_existing_fallback_device_name_is_improved_without_overwriting_user_titles(
    hass, title, user_name, payload, expected
):
    entry = MockConfigEntry(
        domain=DOMAIN, title=title, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}, name="LINAK"
    )
    if user_name:
        devices.async_update_device(device.id, name_by_user=user_name)
    fake = NamedDesk(payload)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=BLEDevice(ADDRESS, ADDRESS, {}),
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.title == title
        assert devices.async_get(device.id).name == expected
        assert devices.async_get(device.id).name_by_user == user_name
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "payload", [b"", b"\xff", b"Hidden\x01name", ADDRESS.encode(), b"LINAK"]
)
async def test_invalid_optional_gap_names_do_not_block_readings(payload):
    from custom_components.ha_linak.client import DeskClient

    fake = NamedDesk(payload)
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    assert desk.connected
    assert desk.device_name is None
    assert len(fake.writes) == 7
    await desk.disconnect()


async def test_gap_name_is_read_once_per_session_and_not_exported(hass):
    import json
    from custom_components.ha_linak.client import DeskClient
    from custom_components.ha_linak.coordinator import LinakCoordinator
    from custom_components.ha_linak.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    fake = NamedDesk()
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
        state = await desk.refresh()
    assert fake.name_reads == 1
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS})
    coordinator = LinakCoordinator(hass, entry)
    coordinator.desk = desk
    coordinator.async_set_updated_data(state)
    entry.runtime_data = coordinator
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert "Office desk" not in json.dumps(result)
    await coordinator.async_close()


@pytest.mark.parametrize("properties", [None, ["notify"]])
async def test_missing_or_nonreadable_name_characteristic_is_optional(properties):
    from custom_components.ha_linak.client import DeskClient

    fake = NamedDesk()
    characteristic = (
        None if properties is None else SimpleNamespace(properties=properties)
    )
    fake.services = SimpleNamespace(get_characteristic=lambda _: characteristic)
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    assert desk.connected
    assert fake.name_reads == 0
    await desk.disconnect()


async def test_denied_gap_name_is_optional_and_its_error_is_private(caplog):
    import logging
    from bleak.exc import BleakError
    from custom_components.ha_linak.client import DeskClient

    caplog.set_level(logging.DEBUG, logger="custom_components.ha_linak.client")
    fake = NamedDesk()
    original = fake.read_gatt_char

    async def read(uuid):
        if uuid == DEVICE_NAME_UUID:
            raise BleakError("Private desk address")
        return await original(uuid)

    fake.read_gatt_char = read
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    assert desk.connected
    assert "Private desk address" not in caplog.text
    await desk.disconnect()


async def test_name_read_timeout_invalidates_session_before_queries():
    import asyncio
    from custom_components.ha_linak.client import DeskClient

    fake = NamedDesk()

    async def hang(_uuid):
        await asyncio.Future()

    fake.read_gatt_char = hang
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await desk.refresh()
    assert not fake.is_connected
    assert desk.client is None
    assert desk.stage == "device_name"
    assert fake.writes == []


async def test_link_loss_during_name_read_is_not_hidden_as_optional_metadata():
    import asyncio
    from custom_components.ha_linak.client import DeskClient, DeskLinkLost

    started = asyncio.Event()
    fake = NamedDesk()

    async def hang(_uuid):
        started.set()
        await asyncio.Future()

    fake.read_gatt_char = hang
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    connect = AsyncMock(return_value=fake)
    with patch("custom_components.ha_linak.client.establish_connection", connect):
        task = asyncio.create_task(desk.refresh())
        await asyncio.wait_for(started.wait(), 1)
        fake.is_connected = False
        connect.call_args.kwargs["disconnected_callback"](fake)
        with pytest.raises(DeskLinkLost):
            await task
    assert desk.client is None
    assert desk.stage == "device_name"
    assert fake.writes == []


async def test_ambiguous_optional_name_characteristic_does_not_block_readings():
    from bleak.exc import BleakError
    from custom_components.ha_linak.client import DeskClient
    from unittest.mock import Mock

    fake = NamedDesk()
    fake.services = SimpleNamespace(
        get_characteristic=Mock(side_effect=BleakError("Ambiguous name"))
    )
    desk = DeskClient(BLEDevice(ADDRESS, ADDRESS, {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    assert desk.connected
    assert desk.device_name is None
    await desk.disconnect()


def test_missing_runtime_desk_does_not_change_a_saved_title(hass):
    from custom_components.ha_linak import _repair_title

    entry = MockConfigEntry(domain=DOMAIN, title="LINAK", data={CONF_ADDRESS: ADDRESS})
    coordinator = SimpleNamespace(desk=None)
    _repair_title(hass, entry, coordinator)
    assert entry.title == "LINAK"
