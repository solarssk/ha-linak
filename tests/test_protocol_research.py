"""Explicit research reads use the native lock and never write settings or move."""

import asyncio
import gc
import weakref
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bleak.backends.device import BLEDevice
from bleak.exc import BleakDBusError, BleakError, BleakGATTProtocolError
import pytest

from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
import probatio as vol
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Context
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_linak.client import DeskClient, DeskLinkLost
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.motion import MotionError, MotionFailure
from custom_components.ha_linak.protocol import (
    DPG_UUID,
    HEIGHT_UUID,
    REFERENCE_INVENTORY_UUIDS,
    ResearchSection,
    research_product_reply,
)
from custom_components.ha_linak.services import SERVICE_READ_PROTOCOL_INVENTORY
from test_client import FakeBleak

DEVICE = BLEDevice("AA:BB:CC:DD:EE:FF", "Synthetic desk", {})
EXPECTED_REFERENCE_UUIDS = [
    "99fa0021-338a-1024-8a49-009c0215f78a",
    "99fa0029-338a-1024-8a49-009c0215f78a",
    "99fa002a-338a-1024-8a49-009c0215f78a",
    "99fa0022-338a-1024-8a49-009c0215f78a",
    "99fa0023-338a-1024-8a49-009c0215f78a",
    "99fa0024-338a-1024-8a49-009c0215f78a",
    "99fa0025-338a-1024-8a49-009c0215f78a",
    "99fa0026-338a-1024-8a49-009c0215f78a",
    "99fa0027-338a-1024-8a49-009c0215f78a",
    "99fa0028-338a-1024-8a49-009c0215f78a",
]


class ResearchBleak(FakeBleak):
    def __init__(self):
        super().__init__()
        self.services = SimpleNamespace(
            get_characteristic=self.characteristic,
        )
        self.missing = set()
        self.unreadable = set()
        self.reads = []
        self.read_errors = {}
        self.read_responses = {}
        self.product_reply = b"\x01\x05\x10\x20\x30"
        self.product_started = asyncio.Event()
        self.product_gate = None
        self.read_gate = None
        self.disconnect_gate = None
        self.disconnect_started = asyncio.Event()
        self.nonstationary = False
        self.emit_product_ack = True
        self.product_written = asyncio.Event()

    def characteristic(self, uuid):
        if uuid in self.missing or uuid not in {*EXPECTED_REFERENCE_UUIDS, DPG_UUID}:
            return None
        return SimpleNamespace(
            properties=[]
            if uuid in self.unreadable
            else ["read", "write", "notify"]
            if uuid == DPG_UUID
            else ["read"]
        )

    async def write_gatt_char(self, uuid, payload, response):
        if bytes(payload) != b"\x7f\x08\x00":
            await super().write_gatt_char(uuid, payload, response)
            return
        self.writes.append((uuid, bytes(payload)))
        self.product_started.set()
        if self.product_gate is not None:
            await self.product_gate.wait()
        if self.emit_product_ack:
            self.callbacks[DPG_UUID](None, bytearray(b"\x01\x00"))
        if self.product_reply is not None:
            self.callbacks[DPG_UUID](None, bytearray(self.product_reply))
        self.product_written.set()

    async def read_gatt_char(self, uuid):
        self.reads.append(uuid)
        if self.read_gate is not None:
            await self.read_gate.wait()
        if uuid in self.read_errors:
            raise self.read_errors[uuid]
        if uuid in self.read_responses:
            return self.read_responses[uuid]
        if uuid == HEIGHT_UUID:
            return b"\x00\x04\x01\x00" if self.nonstationary else b"\x00\x04\x00\x00"
        return b"\x00\x00\x04\x00"

    async def disconnect(self):
        self.disconnect_started.set()
        if self.disconnect_gate is not None:
            await self.disconnect_gate.wait()
        await super().disconnect()


async def connected_desk():
    fake = ResearchBleak()
    desk = DeskClient(DEVICE, lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    fake.writes.clear()
    fake.reads.clear()
    return desk, fake


async def setup_entry(hass):
    fake = ResearchBleak()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic desk",
        unique_id=DEVICE.address,
        data={CONF_ADDRESS: DEVICE.address},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection", return_value=fake
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    fake.writes.clear()
    fake.reads.clear()
    return entry, fake


async def test_fixed_reference_reads_on_existing_proxy():
    desk, fake = await connected_desk()
    previous = desk.state
    result = await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == EXPECTED_REFERENCE_UUIDS
    assert fake.writes == []
    assert result["backend"] == "bleak_esphome"
    assert result["semantics_verified"] is False
    assert len(result["observations"]) == 10
    assert desk.state is previous
    assert desk.connected
    await desk.disconnect()


async def test_one_product_query_after_barrier_without_activation():
    desk, fake = await connected_desk()
    result = await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert fake.writes == [(DPG_UUID, b"\x7f\x80\x00"), (DPG_UUID, b"\x7f\x08\x00")]
    assert result["response_hex"] == fake.product_reply.hex()
    assert result["semantics_verified"] is False
    assert fake.reads == [HEIGHT_UUID]
    assert desk.connected
    assert desk._product_pending is None
    await desk.disconnect()


@pytest.mark.parametrize("section", list(ResearchSection))
async def test_no_reconnect_on_unready_session(section):
    desk, fake = await connected_desk()
    await desk.disconnect()
    with (
        patch("custom_components.ha_linak.client.establish_connection") as connect,
        pytest.raises(ConnectionError),
    ):
        await desk.read_protocol_inventory(section)
    connect.assert_not_called()
    assert fake.writes == []


async def test_released_session_does_not_read():
    desk, fake = await connected_desk()
    await desk.release()
    with pytest.raises(ConnectionError):
        await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert fake.writes == []


@pytest.mark.parametrize("section", list(ResearchSection))
async def test_busy_read_is_refused_without_queue(section):
    desk, fake = await connected_desk()
    async with desk._lock:
        with pytest.raises(MotionError) as error:
            await desk.read_protocol_inventory(section)
    assert error.value.reason is MotionFailure.BUSY
    assert fake.writes == fake.reads == []
    await desk.disconnect()


async def test_control_cannot_start_during_research_and_polling_is_serialized():
    desk, fake = await connected_desk()
    fake.product_gate = asyncio.Event()
    read = asyncio.create_task(
        desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    )
    await fake.product_started.wait()
    settings = ControlSettings(70, 125)
    with pytest.raises(MotionError):
        await desk.move_to_cm(83, settings)
    refresh = asyncio.create_task(desk.refresh())
    await asyncio.sleep(0)
    assert fake.writes == [(DPG_UUID, b"\x7f\x80\x00"), (DPG_UUID, b"\x7f\x08\x00")]
    fake.product_gate.set()
    await read
    await refresh
    await desk.disconnect()


@pytest.mark.parametrize("section", list(ResearchSection))
async def test_timeout_discards_session_and_does_not_retry(section):
    desk, fake = await connected_desk()
    if section is ResearchSection.PRODUCT_INFO:
        fake.product_gate = asyncio.Event()
    else:
        fake.read_gate = asyncio.Event()
    with (
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
        patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await desk.read_protocol_inventory(section)
    assert not desk.connected
    assert not fake.is_connected
    assert sum(payload == b"\x7f\x08\x00" for _, payload in fake.writes) <= 1
    assert desk._product_pending is None


async def test_disconnect_during_pending_raw_reply_invalidates_generation():
    desk, fake = await connected_desk()
    fake.product_gate = asyncio.Event()
    generation = desk._generation
    task = asyncio.create_task(
        desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    )
    await fake.product_started.wait()
    desk._notification(generation - 1, bytearray(fake.product_reply))
    assert not task.done()
    fake.is_connected = False
    desk._disconnected(fake)
    with pytest.raises(DeskLinkLost):
        await task
    assert desk._product_pending is None
    assert desk._generation > generation


async def test_cancelled_research_waits_for_bounded_cleanup():
    desk, fake = await connected_desk()
    fake.product_gate = asyncio.Event()
    fake.disconnect_gate = asyncio.Event()
    task = asyncio.create_task(
        desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    )
    await fake.product_started.wait()
    task.cancel()
    await fake.disconnect_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    fake.disconnect_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not desk.connected


async def test_nonstationary_position_refuses_reference_inventory():
    desk, fake = await connected_desk()
    fake.nonstationary = True
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == [HEIGHT_UUID]
    assert fake.writes == []
    assert not desk.connected


async def test_nonstationary_position_prevents_product_query():
    desk, fake = await connected_desk()
    fake.nonstationary = True
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert fake.reads == [HEIGHT_UUID]
    assert fake.writes == []
    assert not desk.connected


async def test_unidentified_late_frame_is_raw_not_verified_product_metadata():
    desk, fake = await connected_desk()
    fake.product_reply = b"\x01\x02\x44\x01"
    result = await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert result["response_hex"] == fake.product_reply.hex()
    assert result["semantics_verified"] is False
    assert result["correlation"] == "serialized_raw_reply_without_request_identity"
    await desk.disconnect()


async def test_complete_research_budget_still_discards_the_session():
    desk, fake = await connected_desk()
    fake.read_gate = asyncio.Event()
    with (
        patch("custom_components.ha_linak.client.REFRESH_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert not desk.connected
    assert not fake.is_connected


async def test_changed_capabilities_prevent_product_query():
    desk, fake = await connected_desk()

    async def changed_capabilities(uuid, payload, response):
        fake.writes.append((uuid, bytes(payload)))
        fake.callbacks[DPG_UUID](None, bytearray(b"\x01\x02\x00\x01"))

    fake.write_gatt_char = changed_capabilities
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert fake.writes == [(DPG_UUID, b"\x7f\x80\x00")]
    assert not desk.connected


async def test_absent_optional_output_is_not_zero():
    desk, fake = await connected_desk()
    fake.services.get_characteristic = lambda uuid: (
        SimpleNamespace(properties=["read"]) if uuid == HEIGHT_UUID else None
    )
    result = await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == [HEIGHT_UUID]
    assert result["observations"][1] == {
        "uuid": REFERENCE_INVENTORY_UUIDS[1],
        "status": "not_readable",
    }
    await desk.disconnect()


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x01",
        b"\x0b\x00",
        b"\x01\x03",
        b"\x01\x11" + bytes(17),
        b"\x01\x05" + bytes(511),
    ],
)
async def test_malformed_or_identity_replies_are_not_published(payload):
    desk, fake = await connected_desk()
    fake.product_reply = payload
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert not desk.connected
    assert desk._product_pending is None


def test_product_research_parser_does_not_invent_semantics():
    assert research_product_reply(b"\x01\x00") is None
    assert research_product_reply(b"\x01\x05\x10\x20") == b"\x01\x05\x10\x20"


async def test_response_service_uses_existing_native_transport(hass):
    entry, fake = await setup_entry(hass)
    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_READ_PROTOCOL_INVENTORY,
        {"config_entry_id": entry.entry_id, "section": "product_info"},
        blocking=True,
        return_response=True,
    )
    assert result["response_hex"] == fake.product_reply.hex()
    assert fake.writes == [(DPG_UUID, b"\x7f\x80\x00"), (DPG_UUID, b"\x7f\x08\x00")]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_nonadministrator_service_call_is_rejected_without_io(hass):
    entry, fake = await setup_entry(hass)
    await hass.auth.async_create_user("Synthetic owner", group_ids=[GROUP_ID_ADMIN])
    user = await hass.auth.async_create_user(
        "Synthetic user", group_ids=[GROUP_ID_USER]
    )
    assert not user.is_admin
    context = Context(user_id=user.id)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_READ_PROTOCOL_INVENTORY,
            {"config_entry_id": entry.entry_id, "section": "product_info"},
            blocking=True,
            return_response=True,
            context=context,
        )
    assert fake.writes == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("section", ["unknown", "7f8880", "save_memory"])
async def test_service_rejects_nonallowlisted_sections(hass, section):
    entry, fake = await setup_entry(hass)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_READ_PROTOCOL_INVENTORY,
            {"config_entry_id": entry.entry_id, "section": section},
            blocking=True,
            return_response=True,
        )
    assert fake.writes == []
    await hass.config_entries.async_unload(entry.entry_id)


async def test_service_refuses_unloaded_entry_without_reconnecting(hass):
    entry, fake = await setup_entry(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_READ_PROTOCOL_INVENTORY,
            {"config_entry_id": entry.entry_id, "section": "product_info"},
            blocking=True,
            return_response=True,
        )
    assert error.value.translation_key == "research_not_ready"
    assert fake.writes == []


async def test_service_failure_is_visible_and_clears_availability(hass):
    entry, fake = await setup_entry(hass)
    fake.product_reply = b"bad"
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_READ_PROTOCOL_INVENTORY,
            {"config_entry_id": entry.entry_id, "section": "product_info"},
            blocking=True,
            return_response=True,
        )
    assert error.value.translation_key == "research_failed"
    assert not entry.runtime_data.last_update_success
    await hass.config_entries.async_unload(entry.entry_id)


async def test_service_busy_error_does_not_change_operation(hass):
    entry, fake = await setup_entry(hass)
    original = entry.runtime_data.operation
    async with entry.runtime_data.desk._lock:
        with pytest.raises(ServiceValidationError) as error:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_READ_PROTOCOL_INVENTORY,
                {"config_entry_id": entry.entry_id, "section": "product_info"},
                blocking=True,
                return_response=True,
            )
    assert error.value.translation_key == "control_busy"
    assert entry.runtime_data.operation == original
    assert fake.writes == fake.reads == []
    await hass.config_entries.async_unload(entry.entry_id)


async def test_service_refuses_released_intent_and_arbitrary_fields(hass):
    entry, fake = await setup_entry(hass)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_READ_PROTOCOL_INVENTORY,
            {
                "config_entry_id": entry.entry_id,
                "section": "product_info",
                "payload": "7f8880",
            },
            blocking=True,
            return_response=True,
        )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "keep_connected": False}
    )
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_READ_PROTOCOL_INVENTORY,
            {"config_entry_id": entry.entry_id, "section": "product_info"},
            blocking=True,
            return_response=True,
        )
    assert error.value.translation_key == "research_not_ready"
    assert fake.writes == fake.reads == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("section", ["unknown", None, 8])
async def test_invalid_direct_section_does_not_touch_the_ready_session(section):
    desk, fake = await connected_desk()
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(section)
    assert fake.writes == fake.reads == []
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize("section", list(ResearchSection))
@pytest.mark.parametrize("support", ["absent", "unreadable"])
async def test_required_position_characteristic_is_not_optional(section, support):
    desk, fake = await connected_desk()
    if support == "absent":
        fake.missing.add(HEIGHT_UUID)
    else:
        fake.unreadable.add(HEIGHT_UUID)
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(section)
    assert fake.writes == fake.reads == []
    assert not desk.connected


async def test_unreadable_optional_property_does_not_trigger_a_read():
    desk, fake = await connected_desk()
    uuid = EXPECTED_REFERENCE_UUIDS[1]
    fake.unreadable.add(uuid)
    result = await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert uuid not in fake.reads
    assert result["observations"][1] == {"uuid": uuid, "status": "not_readable"}
    assert desk.connected
    await desk.disconnect()


async def test_oversized_reference_payload_discards_session():
    desk, fake = await connected_desk()
    fake.read_responses[EXPECTED_REFERENCE_UUIDS[1]] = bytes(513)
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == EXPECTED_REFERENCE_UUIDS[:2]
    assert fake.writes == []
    assert not desk.connected


async def test_research_refuses_a_released_lock_with_an_awakened_waiter():
    desk, fake = await connected_desk()
    release_waiter = asyncio.Event()

    async def queued_reader():
        async with desk._lock:
            await release_waiter.wait()

    await desk._lock.acquire()
    waiter = asyncio.create_task(queued_reader())
    await asyncio.sleep(0)
    desk._lock.release()
    assert not desk._lock.locked()
    # Release the existing waiter if a broken implementation queues behind it.
    timer = asyncio.get_running_loop().call_later(1, release_waiter.set)
    try:
        with pytest.raises(MotionError) as error:
            await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
        assert error.value.reason is MotionFailure.BUSY
        assert not release_waiter.is_set()
        assert fake.writes == fake.reads == []
    finally:
        timer.cancel()
        release_waiter.set()
        await waiter
        await desk.disconnect()


@pytest.mark.parametrize(
    "invalidated_at",
    [HEIGHT_UUID, EXPECTED_REFERENCE_UUIDS[1], EXPECTED_REFERENCE_UUIDS[-1]],
)
async def test_invalid_height_notification_ends_reference_reads(invalidated_at):
    desk, fake = await connected_desk()
    read = fake.read_gatt_char

    async def invalidate_after_read(uuid):
        payload = await read(uuid)
        if uuid == invalidated_at:
            fake.callbacks[HEIGHT_UUID](None, bytearray(b"bad"))
        return payload

    fake.read_gatt_char = invalidate_after_read
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert (
        fake.reads
        == EXPECTED_REFERENCE_UUIDS[
            : EXPECTED_REFERENCE_UUIDS.index(invalidated_at) + 1
        ]
    )
    assert fake.writes == []
    assert not desk.connected


@pytest.mark.parametrize("invalidated_at", ["position", "capabilities", "product"])
async def test_invalid_height_notification_ends_product_research(invalidated_at):
    desk, fake = await connected_desk()
    read = fake.read_gatt_char
    write = fake.write_gatt_char

    async def invalidate_after_position(uuid):
        payload = await read(uuid)
        if invalidated_at == "position":
            fake.callbacks[HEIGHT_UUID](None, bytearray(b"bad"))
        return payload

    async def invalidate_after_exchange(uuid, payload, response):
        await write(uuid, payload, response)
        if (invalidated_at == "capabilities" and payload == b"\x7f\x80\x00") or (
            invalidated_at == "product" and payload == b"\x7f\x08\x00"
        ):
            fake.callbacks[HEIGHT_UUID](None, bytearray(b"bad"))

    fake.read_gatt_char = invalidate_after_position
    fake.write_gatt_char = invalidate_after_exchange
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    expected_writes = (
        []
        if invalidated_at == "position"
        else [(DPG_UUID, b"\x7f\x80\x00")]
        if invalidated_at == "capabilities"
        else [(DPG_UUID, b"\x7f\x80\x00"), (DPG_UUID, b"\x7f\x08\x00")]
    )
    assert fake.writes == expected_writes
    assert not desk.connected
    assert desk._product_pending is None


async def test_invalid_height_in_reply_delivery_cannot_publish_success():
    desk, fake = await connected_desk()
    write = fake.write_gatt_char

    def reply_and_invalidate():
        fake.callbacks[DPG_UUID](None, bytearray(fake.product_reply))
        fake.callbacks[HEIGHT_UUID](None, bytearray(b"bad"))

    async def reply_on_next_turn(uuid, payload, response):
        if payload != b"\x7f\x08\x00":
            await write(uuid, payload, response)
            return
        fake.writes.append((uuid, bytes(payload)))
        asyncio.get_running_loop().call_soon(reply_and_invalidate)

    fake.write_gatt_char = reply_on_next_turn
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    assert not desk.connected
    assert desk._product_pending is None


@pytest.mark.parametrize(
    "error",
    [
        BleakDBusError("org.bluez.Error.NotPermitted", []),
        BleakDBusError("org.bluez.Error.NotAuthorized", []),
        BleakDBusError("org.bluez.Error.NotSupported", []),
        BleakGATTProtocolError(2),
        BleakGATTProtocolError(5),
        BleakGATTProtocolError(6),
        BleakGATTProtocolError(8),
        BleakGATTProtocolError(12),
        BleakGATTProtocolError(15),
    ],
)
async def test_explicit_optional_read_denial_preserves_the_other_observations(error):
    desk, fake = await connected_desk()
    uuid = EXPECTED_REFERENCE_UUIDS[3]
    fake.read_errors[uuid] = error
    result = await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == EXPECTED_REFERENCE_UUIDS
    assert result["observations"][3] == {"uuid": uuid, "status": "not_readable"}
    assert result["observations"][4]["status"] == "returned"
    assert fake.writes == []
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize(
    "error",
    [
        BleakError("synthetic transport failure"),
        BleakDBusError("org.bluez.Error.Failed", []),
        BleakGATTProtocolError(1),
        BleakGATTProtocolError(256),
    ],
)
async def test_unknown_optional_read_failure_is_not_an_unreadable_feature(error):
    desk, fake = await connected_desk()
    fake.read_errors[EXPECTED_REFERENCE_UUIDS[1]] = error
    with pytest.raises(BleakError):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == EXPECTED_REFERENCE_UUIDS[:2]
    assert not desk.connected


async def test_explicit_denial_of_required_position_is_fatal():
    desk, fake = await connected_desk()
    fake.read_errors[HEIGHT_UUID] = BleakDBusError("org.bluez.Error.NotPermitted", [])
    with pytest.raises(BleakError):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert fake.reads == [HEIGHT_UUID]
    assert not desk.connected


async def test_last_optional_read_cannot_hide_link_loss_before_callback():
    desk, fake = await connected_desk()
    read = fake.read_gatt_char

    async def lose_link_on_last_read(uuid):
        if uuid == EXPECTED_REFERENCE_UUIDS[-1]:
            fake.is_connected = False
            raise BleakDBusError("org.bluez.Error.NotPermitted", [])
        return await read(uuid)

    fake.read_gatt_char = lose_link_on_last_read
    with pytest.raises(DeskLinkLost):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert not desk.connected
    assert fake.writes == []


async def test_optional_denial_cannot_hide_invalidated_position():
    desk, fake = await connected_desk()
    read = fake.read_gatt_char

    async def invalidate_and_deny(uuid):
        if uuid == EXPECTED_REFERENCE_UUIDS[-1]:
            fake.callbacks[HEIGHT_UUID](None, bytearray(b"bad"))
            raise BleakDBusError("org.bluez.Error.NotAuthorized", [])
        return await read(uuid)

    fake.read_gatt_char = invalidate_and_deny
    with pytest.raises(ValueError):
        await desk.read_protocol_inventory(ResearchSection.REFERENCE_OUTPUTS)
    assert not desk.connected
    assert fake.writes == []


async def test_disconnect_cancels_the_pending_product_future():
    desk, fake = await connected_desk()
    fake.product_gate = asyncio.Event()
    task = asyncio.create_task(
        desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    )
    await fake.product_started.wait()
    pending = desk._product_pending
    assert pending is not None and not pending.done()
    await desk.disconnect()
    with pytest.raises(DeskLinkLost):
        await task
    assert pending.cancelled()
    assert desk._product_pending is None
    assert not desk._lock.locked()
    assert fake.writes == [(DPG_UUID, b"\x7f\x80\x00"), (DPG_UUID, b"\x7f\x08\x00")]


async def test_reply_wait_has_its_own_deadline_after_the_write_returns():
    desk, fake = await connected_desk()
    fake.product_reply = None
    fake.emit_product_ack = False
    with (
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
        patch("custom_components.ha_linak.client.REFRESH_TIMEOUT", 5),
    ):
        task = asyncio.create_task(
            desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
        )
        try:
            done, _ = await asyncio.wait({task}, timeout=0.5)
            assert fake.product_written.is_set()
            assert task in done, "the reply wait fell through to the outer deadline"
            with pytest.raises(TimeoutError):
                await task
            assert not desk.connected
            assert desk._product_pending is None
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_cancelled_research_bounds_a_hung_disconnect():
    desk, fake = await connected_desk()
    fake.product_gate = asyncio.Event()
    fake.disconnect_gate = asyncio.Event()
    with patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01):
        task = asyncio.create_task(
            desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
        )
        await fake.product_started.wait()
        task.cancel()
        try:
            done, _ = await asyncio.wait({task}, timeout=0.5)
            assert task in done, "disconnect cleanup exceeded its own deadline"
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not desk.connected
            assert not desk._lock.locked()
        finally:
            fake.disconnect_gate.set()
            await asyncio.gather(task, return_exceptions=True)


async def test_cancellation_as_cleanup_settles_remains_cancellation():
    desk, fake = await connected_desk()
    fake.product_reply = b"bad"
    disconnect = fake.disconnect

    async def cancel_after_disconnect():
        await disconnect()
        asyncio.current_task().add_done_callback(lambda _: task.cancel())

    fake.disconnect = cancel_after_disconnect
    task = asyncio.create_task(
        desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
    )
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not desk.connected
    assert not desk._lock.locked()


@pytest.mark.parametrize("failure", ["write_error", "write_timeout", "cancelled"])
async def test_parser_error_is_observed_when_the_product_write_does_not_finish(failure):
    desk, fake = await connected_desk()
    write = fake.write_gatt_char
    loop = asyncio.get_running_loop()
    events = []
    pending_ref = None
    pending_audit = None
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: events.append(context))

    class ObservedFuture(asyncio.Future):
        def __init__(self):
            super().__init__(loop=loop)
            self.audit = []

        def exception(self):
            self.audit.append("exception")
            return super().exception()

    async def malformed_notification_during_write(uuid, payload, response):
        nonlocal pending_ref, pending_audit
        if payload != b"\x7f\x08\x00":
            await write(uuid, payload, response)
            return
        fake.writes.append((uuid, bytes(payload)))
        pending_ref = weakref.ref(desk._product_pending)
        pending_audit = desk._product_pending.audit
        fake.callbacks[DPG_UUID](None, bytearray(b"bad"))
        fake.product_started.set()
        if failure == "write_error":
            raise BleakError("synthetic write failure")
        await asyncio.Future()

    fake.write_gatt_char = malformed_notification_during_write

    async def finish_failed_read():
        with (
            patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
            patch.object(loop, "create_future", side_effect=ObservedFuture),
        ):
            task = asyncio.create_task(
                desk.read_protocol_inventory(ResearchSection.PRODUCT_INFO)
            )
            await fake.product_started.wait()
            if failure == "cancelled":
                task.cancel()
            expected = (
                BleakError
                if failure == "write_error"
                else TimeoutError
                if failure == "write_timeout"
                else asyncio.CancelledError
            )
            with pytest.raises(expected):
                await task
        assert desk._product_pending is None
        assert not desk.connected

    try:
        await finish_failed_read()
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)
        assert pending_audit == ["exception"], (
            "completed parser exception was not explicitly observed"
        )
        assert pending_ref is not None and pending_ref() is None
        assert not events
    finally:
        loop.set_exception_handler(previous_handler)


async def call_research_action(hass, entry_id):
    return await hass.services.async_call(
        DOMAIN,
        SERVICE_READ_PROTOCOL_INVENTORY,
        {"config_entry_id": entry_id, "section": "product_info"},
        blocking=True,
        return_response=True,
    )


async def test_reference_action_uses_native_session_without_publishing_raw_metadata(
    hass,
):
    entry, fake = await setup_entry(hass)
    sensors_before = {
        state.entity_id: state.state for state in hass.states.async_all("sensor")
    }
    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_READ_PROTOCOL_INVENTORY,
        {"config_entry_id": entry.entry_id, "section": "reference_outputs"},
        blocking=True,
        return_response=True,
    )
    assert result["section"] == "reference_outputs"
    assert result["semantics_verified"] is False
    assert len(result["observations"]) == 10
    assert fake.reads == EXPECTED_REFERENCE_UUIDS
    assert fake.writes == []
    assert entry.runtime_data.desk.connected
    assert {
        state.entity_id: state.state for state in hass.states.async_all("sensor")
    } == sensors_before
    await hass.config_entries.async_unload(entry.entry_id)


async def test_service_rejects_an_enabled_idasen_owner_without_io(hass):
    entry, fake = await setup_entry(hass)
    other = MockConfigEntry(
        domain="idasen_desk",
        unique_id=DEVICE.address,
        data={CONF_ADDRESS: DEVICE.address},
    )
    other.add_to_hass(hass)
    with pytest.raises(ServiceValidationError) as error:
        await call_research_action(hass, entry.entry_id)
    assert error.value.translation_key == "idasen_conflict"
    assert other.disabled_by is None
    assert fake.writes == fake.reads == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "failure",
    [
        MotionError("synthetic private detail"),
        BleakError("synthetic private detail"),
        ConnectionError("synthetic private detail"),
        TimeoutError("synthetic private detail"),
    ],
)
async def test_service_reports_read_failures_without_raw_backend_details(
    hass, caplog, failure
):
    entry, fake = await setup_entry(hass)
    with (
        patch.object(
            entry.runtime_data.desk,
            "read_protocol_inventory",
            AsyncMock(side_effect=failure),
        ),
        pytest.raises(HomeAssistantError) as error,
    ):
        await call_research_action(hass, entry.entry_id)
    assert error.value.translation_key == "research_failed"
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "custom_components.ha_linak.services"
    ]
    assert messages == [f"Protocol research read failed: {type(failure).__name__}"]
    assert fake.writes == fake.reads == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "entry_case",
    ["missing", "other_domain", "wrong_runtime", "no_client", "disconnected"],
)
async def test_service_refuses_invalid_or_unready_entries(hass, entry_case):
    entry, fake = await setup_entry(hass)
    coordinator = entry.runtime_data
    identifier = entry.entry_id
    if entry_case == "missing":
        identifier = "missing-synthetic-entry"
    elif entry_case == "other_domain":
        other = MockConfigEntry(domain="other_integration", data={})
        other.add_to_hass(hass)
        identifier = other.entry_id
    elif entry_case == "wrong_runtime":
        entry.runtime_data = SimpleNamespace()
    elif entry_case == "no_client":
        await coordinator.desk.disconnect()
        coordinator.desk = None
    else:
        await coordinator.desk.disconnect()
    try:
        with pytest.raises(ServiceValidationError) as error:
            await call_research_action(hass, identifier)
        assert error.value.translation_key == "research_not_ready"
        assert fake.writes == fake.reads == []
    finally:
        entry.runtime_data = coordinator
        await hass.config_entries.async_unload(entry.entry_id)
