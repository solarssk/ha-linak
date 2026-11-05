"""Native Bluetooth names in discovery, validated entries and device metadata."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ha_linak.client import DEVICE_NAME_UUID
from custom_components.ha_linak.connection_intent import CONF_KEEP_CONNECTED
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.naming import desk_name, discovery_title
from custom_components.ha_linak.protocol import SERVICE_UUID
from test_client import FakeBleak
from test_integration import ADDRESS, finish_progress
from test_reminder_profile import setup_select


@pytest.mark.parametrize(
    "filename,position,stored",
    [
        ("strings.json", "Position", "Stored height"),
        ("translations/en.json", "Position", "Stored height"),
        ("translations/pl.json", "Pozycja", "Zapisana wysokość"),
    ],
)
def test_short_position_button_labels_keep_stored_height_sensors_distinct(
    filename, position, stored
):
    root = Path(__file__).parents[1] / "custom_components/ha_linak"
    entities = json.loads((root / filename).read_text())["entity"]
    for slot in range(1, 5):
        assert (
            entities["button"][f"go_to_memory_{slot}"]["name"] == f"{position} {slot}"
        )
        assert entities["sensor"][f"memory_{slot}"]["name"] == f"{stored} {slot}"


@pytest.mark.parametrize("disabled_by", [None, er.RegistryEntryDisabler.USER])
async def test_position_labels_preserve_existing_registry_identity_and_overrides(
    hass, disabled_by
):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Desk", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    buttons = []
    for slot in range(1, 5):
        item = registry.async_get_or_create(
            "button",
            DOMAIN,
            f"{ADDRESS}_go_to_memory_{slot}",
            config_entry=entry,
            suggested_object_id=f"desk_go_to_stored_position_{slot}",
        )
        buttons.append(
            registry.async_update_entity(
                item.entity_id, name=f"My favorite {slot}", disabled_by=disabled_by
            )
        )
    profile = registry.async_get_or_create(
        "sensor", DOMAIN, f"{ADDRESS}_reminder_profile", config_entry=entry
    )
    registry.async_update_entity(profile.entity_id, icon="mdi:alarm")
    await setup_select(hass, entry=entry)
    for slot, previous in enumerate(buttons, 1):
        actual = registry.async_get(previous.entity_id)
        assert actual.unique_id == previous.unique_id
        assert actual.entity_id == previous.entity_id
        assert actual.name == previous.name
        assert actual.original_name == f"Position {slot}"
        assert actual.original_icon == "mdi:table-chair"
        assert actual.disabled_by == disabled_by
    assert registry.async_get(profile.entity_id).icon == "mdi:alarm"
    assert registry.async_get(profile.entity_id).original_icon == "mdi:bell-outline"
    assert hass.states.get(profile.entity_id).attributes["icon"] == "mdi:alarm"
    await hass.config_entries.async_unload(entry.entry_id)


class NamedDesk(FakeBleak):
    def __init__(self, payload=b"Office desk"):
        super().__init__()
        self.payload = payload
        self.name_reads = 0
        get_characteristic = self.services.get_characteristic
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: (
                SimpleNamespace(properties=["read"])
                if uuid == DEVICE_NAME_UUID
                else get_characteristic(uuid)
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
    "advertised,device_name,current_name,latest_name,system_name,expected",
    [
        (ADDRESS, ADDRESS, None, "Office desk", None, "Office desk"),
        ("LINAK", "Office desk", None, None, None, "Office desk"),
        (ADDRESS, ADDRESS, "Office desk", None, None, "Office desk"),
        (ADDRESS, ADDRESS, None, None, None, "LINAK"),
        (ADDRESS, ADDRESS, None, None, "Panel name", "Panel name"),
        (ADDRESS, ADDRESS, None, "Fresh name", "Cached name", "Fresh name"),
    ],
)
async def test_discovery_uses_cached_native_name_without_connecting(
    hass, advertised, device_name, current_name, latest_name, system_name, expected
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
            "custom_components.ha_linak.config_flow.cached_bluez_names",
            new_callable=AsyncMock,
            return_value={ADDRESS: system_name} if system_name else {},
        ),
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
            AsyncMock(side_effect=fake.reconnect),
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
            AsyncMock(side_effect=fake.reconnect),
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
        AsyncMock(side_effect=fake.reconnect),
    ):
        await desk.refresh()
    assert desk.connected
    assert desk.device_name is None
    assert len(fake.writes) == 10
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
        AsyncMock(side_effect=fake.reconnect),
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
    assert json.dumps(result).count("Office desk") == 0
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
        AsyncMock(side_effect=fake.reconnect),
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
        AsyncMock(side_effect=fake.reconnect),
    ):
        await desk.refresh()
    assert desk.connected
    assert caplog.text.count("Private desk address") == 0
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
            AsyncMock(side_effect=fake.reconnect),
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
    connect = AsyncMock(side_effect=fake.reconnect)
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
        AsyncMock(side_effect=fake.reconnect),
    ):
        await desk.refresh()
    assert desk.connected
    assert desk.device_name is None
    await desk.disconnect()


def test_missing_runtime_desk_does_not_change_a_saved_title(hass):
    from custom_components.ha_linak import _repair_title

    entry = MockConfigEntry(domain=DOMAIN, title="LINAK", data={CONF_ADDRESS: ADDRESS})
    coordinator = SimpleNamespace(address=ADDRESS, desk=None)
    _repair_title(hass, entry, coordinator)
    assert entry.title == "LINAK"


@pytest.mark.parametrize(
    "platform,failed", [("linux", False), ("linux", True), ("darwin", False)]
)
async def test_optional_bluez_metadata_is_local_and_nonfatal(platform, failed):
    from custom_components.ha_linak.naming import cached_bluez_names

    adapter = SimpleNamespace(
        load=AsyncMock(side_effect=OSError("private details") if failed else None),
        history={
            ADDRESS.lower(): SimpleNamespace(
                advertisement_data=SimpleNamespace(local_name="Panel name")
            ),
            "11:22:33:44:55:66": SimpleNamespace(
                advertisement_data=SimpleNamespace(local_name="LINAK")
            ),
            "11:22:33:44:55:77": SimpleNamespace(
                advertisement_data=SimpleNamespace(local_name="bad\x01name")
            ),
        },
    )
    with (
        patch("custom_components.ha_linak.naming.sys.platform", platform),
        patch(
            "custom_components.ha_linak.naming.bluetooth_adapters.BlueZDBusObjects",
            return_value=adapter,
        ),
    ):
        result = await cached_bluez_names()
    assert result == (
        {ADDRESS: "Panel name"} if platform == "linux" and not failed else {}
    )
    if platform != "linux":
        adapter.load.assert_not_awaited()


async def test_bluez_metadata_preserves_external_cancellation():
    import asyncio
    from custom_components.ha_linak.naming import cached_bluez_names

    with (
        patch("custom_components.ha_linak.naming.sys.platform", "linux"),
        patch(
            "custom_components.ha_linak.naming.bluetooth_adapters.BlueZDBusObjects"
        ) as objects,
    ):
        objects.return_value.load = AsyncMock(side_effect=asyncio.CancelledError)
        with pytest.raises(asyncio.CancelledError):
            await cached_bluez_names()


def test_connector_wrapped_timeout_keeps_timeout_reason():
    from bleak_retry_connector import BleakNotFoundError
    from custom_components.ha_linak.config_flow import _validation_error

    timeout = TimeoutError()
    wrapped = BleakNotFoundError("private address and backend details")
    wrapped.__cause__ = timeout
    assert _validation_error(wrapped, "connection") == "timeout"
    assert (
        _validation_error(BleakNotFoundError("private details"), "connection")
        == "cannot_connect"
    )


def test_connector_timeout_unwrap_is_bounded_and_handles_nested_causes():
    from bleak_retry_connector import BleakNotFoundError
    from custom_components.ha_linak.config_flow import _validation_error

    middle = RuntimeError("private details")
    middle.__cause__ = TimeoutError()
    wrapped = BleakNotFoundError("private details")
    wrapped.__cause__ = middle
    assert _validation_error(wrapped, "connection") == "timeout"
    middle.__cause__ = middle
    assert _validation_error(wrapped, "connection") == "cannot_connect"


async def test_revisiting_discovery_reuses_system_name_cache(hass):
    from custom_components.ha_linak.config_flow import LinakConfigFlow

    device = BLEDevice(ADDRESS, ADDRESS, {})
    info = SimpleNamespace(
        address=ADDRESS,
        name=ADDRESS,
        device=device,
        service_uuids=[SERVICE_UUID],
        connectable=True,
    )
    flow = LinakConfigFlow()
    flow.hass = hass
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_last_service_info",
            return_value=info,
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=device,
        ),
        patch(
            "custom_components.ha_linak.config_flow.cached_bluez_names",
            new_callable=AsyncMock,
            return_value={ADDRESS: "Panel name"},
        ) as lookup,
    ):
        await flow.async_step_user()
        result = await flow.async_step_user()
    lookup.assert_awaited_once()
    options = result["data_schema"].schema[CONF_ADDRESS].config["options"]
    assert options[0]["label"] == f"Panel name ({ADDRESS})"


async def test_explicit_ha_name_survives_native_name_repair_on_reload(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LINAK",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, "name": "LINAK"},
    )
    entry.add_to_hass(hass)
    fake = NamedDesk(b"Office desk")
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=BLEDevice(ADDRESS, "Office desk", {}),
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.title == "LINAK"
        assert entry.runtime_data.name == "LINAK"
        device = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, ADDRESS), entry.entry_id
        )
        assert device.name == "LINAK"
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "title,entry_name,expected_title",
    [
        (ADDRESS, None, "LINAK"),
        ("Office desk", "Office desk", "Office desk"),
    ],
)
async def test_released_entry_registers_names_without_radio_and_preserves_registry(
    hass, title, entry_name, expected_title
):
    data = {CONF_ADDRESS: ADDRESS, CONF_KEEP_CONNECTED: False}
    if entry_name is not None:
        data[CONF_NAME] = entry_name
    entry = MockConfigEntry(domain=DOMAIN, title=title, unique_id=ADDRESS, data=data)
    entry.add_to_hass(hass)

    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ADDRESS)},
        name="Old device name",
    )
    devices.async_update_device(device.id, name_by_user="My workspace")

    registry = er.async_get(hass)
    old_sensor = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{ADDRESS}_offset",
        config_entry=entry,
        suggested_object_id="saved_offset",
    )
    old_sensor = registry.async_update_entity(old_sensor.entity_id, name="My offset")
    old_number = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{ADDRESS}_target_height",
        config_entry=entry,
        suggested_object_id="my_target",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    expected_registry = (
        old_sensor.entity_id,
        old_sensor.unique_id,
        old_sensor.name,
        old_number.entity_id,
        old_number.unique_id,
        old_number.disabled_by,
    )

    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address"
        ) as lookup,
        patch("homeassistant.components.bluetooth.async_request_active_scan") as scan,
        patch("custom_components.ha_linak.client.establish_connection") as connect,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.title == expected_title
        assert entry.runtime_data.name == expected_title
        lookup.assert_not_called()
        scan.assert_not_called()
        connect.assert_not_called()

        height_id = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_height")
        reminder_id = registry.async_get_entity_id(
            "number", DOMAIN, f"{ADDRESS}_reminder_1_sitting_time"
        )
        assert height_id == "sensor.my_workspace_height"
        assert reminder_id == "number.my_workspace_profile_1_sitting_time"
        assert hass.states.get(height_id).state == "unavailable"
        assert hass.states.get(reminder_id) is None
        assert (
            registry.async_get(reminder_id).disabled_by
            == er.RegistryEntryDisabler.INTEGRATION
        )

        old_sensor = registry.async_get(old_sensor.entity_id)
        old_number = registry.async_get(old_number.entity_id)
        actual_registry = (
            old_sensor.entity_id,
            old_sensor.unique_id,
            old_sensor.name,
            old_number.entity_id,
            old_number.unique_id,
            old_number.disabled_by,
        )
        assert actual_registry == expected_registry
        assert devices.async_get(device.id).name_by_user == "My workspace"
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("existing_device", [False, True], ids=["fresh", "existing"])
async def test_released_mac_title_uses_readable_default_entity_ids(
    hass, existing_device
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=ADDRESS,
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_KEEP_CONNECTED: False},
    )
    entry.add_to_hass(hass)

    devices = dr.async_get(hass)
    if existing_device:
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, ADDRESS)},
            name=ADDRESS,
        )
        assert device.name_by_user is None

    registry = er.async_get(hass)
    old_sensor = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{ADDRESS}_offset",
        config_entry=entry,
        suggested_object_id="legacy_offset",
    )
    old_sensor = registry.async_update_entity(
        old_sensor.entity_id, new_entity_id="sensor.saved_offset", name="My offset"
    )
    old_number = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{ADDRESS}_target_height",
        config_entry=entry,
        suggested_object_id="legacy_target",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    expected_registry = (
        old_sensor.entity_id,
        old_sensor.unique_id,
        old_sensor.name,
        old_number.entity_id,
        old_number.unique_id,
        old_number.disabled_by,
    )

    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address"
        ) as lookup,
        patch("homeassistant.components.bluetooth.async_request_active_scan") as scan,
        patch("custom_components.ha_linak.client.establish_connection") as connect,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        lookup.assert_not_called()
        scan.assert_not_called()
        connect.assert_not_called()
        assert (
            registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_height")
            == "sensor.linak_height"
        )
        assert (
            registry.async_get_entity_id(
                "number", DOMAIN, f"{ADDRESS}_reminder_1_sitting_time"
            )
            == "number.linak_profile_1_sitting_time"
        )
        assert entry.title == "LINAK"
        assert entry.runtime_data.name == "LINAK"
        assert hass.states.get("sensor.linak_height").state == "unavailable"
        assert hass.states.get("number.linak_profile_1_sitting_time") is None
        assert (
            registry.async_get("number.linak_profile_1_sitting_time").disabled_by
            == er.RegistryEntryDisabler.INTEGRATION
        )

        old_sensor = registry.async_get(old_sensor.entity_id)
        old_number = registry.async_get(old_number.entity_id)
        actual_registry = (
            old_sensor.entity_id,
            old_sensor.unique_id,
            old_sensor.name,
            old_number.entity_id,
            old_number.unique_id,
            old_number.disabled_by,
        )
        assert actual_registry == expected_registry
        device = devices.async_get_device_by_identifier(
            (DOMAIN, ADDRESS), entry.entry_id
        )
        assert device.name == "LINAK"
        assert device.name_by_user is None
        assert await hass.config_entries.async_unload(entry.entry_id)
