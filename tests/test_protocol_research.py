"""Explicit research reads use the native lock and never write settings or move."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from bleak.backends.device import BLEDevice
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


class ResearchBleak(FakeBleak):
    def __init__(self):
        super().__init__()
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: SimpleNamespace(
                properties=["read", "write", "notify"] if uuid == DPG_UUID else ["read"]
            )
        )
        self.reads = []
        self.product_reply = b"\x01\x05\x10\x20\x30"
        self.product_started = asyncio.Event()
        self.product_gate = None
        self.read_gate = None
        self.disconnect_gate = None
        self.disconnect_started = asyncio.Event()
        self.nonstationary = False

    async def write_gatt_char(self, uuid, payload, response):
        if bytes(payload) != b"\x7f\x08\x00":
            await super().write_gatt_char(uuid, payload, response)
            return
        self.writes.append((uuid, bytes(payload)))
        self.product_started.set()
        if self.product_gate is not None:
            await self.product_gate.wait()
        self.callbacks[DPG_UUID](None, bytearray(b"\x01\x00"))
        self.callbacks[DPG_UUID](None, bytearray(self.product_reply))

    async def read_gatt_char(self, uuid):
        self.reads.append(uuid)
        if self.read_gate is not None:
            await self.read_gate.wait()
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
    assert fake.reads == list(REFERENCE_INVENTORY_UUIDS)
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
