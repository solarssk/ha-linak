"""Synthetic reminder writes and real HA select registration, without radio I/O."""

import asyncio
import struct
from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ha_linak.client import DeskLinkLost
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.motion import MotionError
from custom_components.ha_linak.protocol import (
    DPG_UUID,
    HEIGHT_UUID,
    ReminderSettings,
    ReminderClientInactive,
    reminder_profile_request,
)
from test_native_controls import DEVICE, ADDRESS, OPTIONS, MotionBleak, connected_desk


class ReminderBleak(MotionBleak):
    def __init__(self):
        super().__init__()
        # Synthetic values, including unknown high bits and zero/maximum intervals.
        self.body = bytes((0xED, 0, 255, 17, 23, 41, 59))
        self.counter = 42
        self.ack = b"\x01\x00"
        self.mismatch = None
        self.hang = False
        self.echo = False
        self.speed = 0
        self.written = asyncio.Event()
        self.read_started = asyncio.Event()
        self.hang_read = False
        self.bad_read = False
        self.reads = 0
        self.on_write = None

    async def read_gatt_char(self, uuid):
        assert uuid == HEIGHT_UUID
        return struct.pack("<HH", self.position, self.speed)

    async def write_gatt_char(self, uuid, data, response):
        if uuid == DPG_UUID and data[:2] == b"\x7f\x88":
            assert response
            self.writes.append((uuid, bytes(data)))
            if data[2] == 0:
                self.reads += 1
                self.read_started.set()
                if self.hang_read:
                    await asyncio.Future()
                reply = b"\x01\x0b" + self.body + struct.pack("<I", self.counter)
                if self.bad_read:
                    reply = reply[:-1]
            else:
                assert data[:3] == b"\x7f\x88\x80"
                assert len(data) == 10
                self.body = bytes(data[3:])
                self.counter += 123  # Counter changes are deliberately not a mismatch.
                self.written.set()
                if self.hang:
                    await asyncio.Future()
                if self.on_write:
                    self.on_write()
                reply = self.ack
            self.callbacks[DPG_UUID](None, bytearray(reply))
            if data[2] == 0x80:
                if self.echo:
                    self.callbacks[DPG_UUID](
                        None, bytearray(b"\x01\x0b" + self.body + bytes(4))
                    )
                if self.mismatch is not None:
                    changed = bytearray(self.body)
                    changed[self.mismatch] ^= 1
                    self.body = bytes(changed)
            return
        await super().write_gatt_char(uuid, data, response)


def settings_writes(fake):
    return [data for _, data in fake.writes if data[2] == 0x80]


@pytest.mark.parametrize("flags", range(256))
def test_profile_encoder_preserves_bits_intervals_and_omits_counter(flags):
    settings = ReminderSettings(flags, ((0, 255), (17, 23), (41, 59)), 0xFFFFFFFF)
    for profile in range(4):
        payload = reminder_profile_request(settings, profile)
        assert payload == b"\x7f\x88\x80" + bytes(
            ((flags & 0xFC) | profile, 0, 255, 17, 23, 41, 59)
        )


@pytest.mark.parametrize("profile", [-1, 4, True, 1.0, "1", None])
async def test_invalid_profile_never_sends(profile):
    desk, fake = await connected_desk(ReminderBleak())
    fake.writes.clear()
    with pytest.raises(ValueError):
        await desk.set_reminder_profile(profile)
    with pytest.raises(ValueError):
        reminder_profile_request(desk.state.reminders, profile)
    assert not fake.writes
    await desk.disconnect()


@pytest.mark.parametrize("profile", range(4))
async def test_fresh_idempotent_assignment_and_independent_readback(profile):
    desk, fake = await connected_desk(ReminderBleak())
    old = fake.body
    # Deliberately stale local cache; fresh wire data owns preservation and no-op.
    desk.state.reminders = ReminderSettings(3, ((1, 2), (3, 4), (5, 6)), 99)
    fake.echo = True
    fake.writes.clear()
    state = await desk.set_reminder_profile(profile)
    assert state.reminders.selected_profile == profile
    assert state.reminders.profiles_raw == ((0, 255), (17, 23), (41, 59))
    assert state.reminders.flags_raw & 0xFC == old[0] & 0xFC
    if profile == 1:
        assert settings_writes(fake) == []
        assert b"\x7f\x86\x00" not in [data for _, data in fake.writes]
    else:
        assert len(settings_writes(fake)) == 1
        assert state.reminders.counter_raw == 165
        assert [data for _, data in fake.writes][-2:] == [
            b"\x7f\x80\x00",
            b"\x7f\x88\x00",
        ]
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert desk.settings_health["reminders"].valid
    assert desk.connected
    assert not desk.control_busy
    await desk.disconnect()


@pytest.mark.parametrize("activation", [0, 2])
async def test_no_activation_for_inactive_or_unknown_client_status(activation):
    desk, fake = await connected_desk(ReminderBleak())
    fake.activation = activation
    with pytest.raises(ReminderClientInactive if activation == 0 else ValueError):
        await desk.set_reminder_profile(2)
    assert not settings_writes(fake)
    assert desk.connected == (activation == 0)
    await desk.disconnect()


@pytest.mark.parametrize(
    "kind", ["group", "disconnected", "speed", "lock", "capabilities"]
)
async def test_unavailable_busy_moving_and_changed_capabilities_refuse(kind):
    desk, fake = await connected_desk(ReminderBleak())
    if kind == "group":
        desk.settings_health["reminders"].valid = False
    elif kind == "disconnected":
        await desk.disconnect()
    elif kind == "speed":
        fake.speed = 1
    elif kind == "lock":
        await desk._lock.acquire()
    else:
        desk.state.capabilities = replace(desk.state.capabilities, flags_raw=0)
    with pytest.raises((MotionError, ValueError)):
        await desk.set_reminder_profile(2)
    assert not settings_writes(fake)
    if kind == "lock":
        desk._lock.release()
    await desk.disconnect()


@pytest.mark.parametrize(
    "ack", [b"\x0b\x00", b"\x01\x00\x01", b"\x01\x01", b"\x00\x00"]
)
async def test_rejected_malformed_and_wrong_ack_never_report_success(ack):
    desk, fake = await connected_desk(ReminderBleak())
    fake.ack = ack
    with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.02):
        with pytest.raises((ValueError, TimeoutError)):
            await desk.set_reminder_profile(2)
    assert len(settings_writes(fake)) == 1
    assert not desk.connected
    assert not desk.settings_health["reminders"].valid


@pytest.mark.parametrize("byte", range(7))
async def test_readback_must_match_profile_other_bits_and_all_times(byte):
    desk, fake = await connected_desk(ReminderBleak())
    fake.mismatch = byte
    with pytest.raises(ValueError, match="readback mismatch"):
        await desk.set_reminder_profile(2)
    assert len(settings_writes(fake)) == 1
    assert not desk.connected


async def test_malformed_fresh_read_prevents_write():
    desk, fake = await connected_desk(ReminderBleak())
    fake.bad_read = True
    with pytest.raises(ValueError):
        await desk.set_reminder_profile(2)
    assert not settings_writes(fake)
    assert not desk.connected


@pytest.mark.parametrize("phase", ["fresh_read", "write"])
@pytest.mark.parametrize("ending", ["timeout", "cancel", "disconnect", "link_loss"])
async def test_interruption_discards_generation_without_retry(phase, ending):
    desk, fake = await connected_desk(ReminderBleak())
    before = desk._generation
    fake.read_started.clear()
    fake.hang_read = phase == "fresh_read"
    fake.hang = phase == "write"
    started = fake.read_started if phase == "fresh_read" else fake.written
    with patch(
        "custom_components.ha_linak.client.QUERY_TIMEOUT",
        0.05 if ending == "timeout" else 8,
    ):
        task = asyncio.create_task(desk.set_reminder_profile(2))
        await asyncio.wait_for(started.wait(), 1)
        if ending == "cancel":
            task.cancel()
        elif ending == "disconnect":
            await desk.disconnect()
        elif ending == "link_loss":
            fake.is_connected = False
            desk._disconnected(fake)
        with pytest.raises((TimeoutError, asyncio.CancelledError, DeskLinkLost)):
            await task
    assert len(settings_writes(fake)) == (1 if phase == "write" else 0)
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert desk._generation > before
    assert not desk.connected
    assert not desk.control_busy
    assert not desk.settings_health["reminders"].valid
    fake.hang_read = fake.hang = False
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        side_effect=fake.reconnect,
    ):
        await desk.refresh()
    assert len(settings_writes(fake)) == (1 if phase == "write" else 0)
    await desk.disconnect()


async def test_generation_change_even_with_connected_transport_is_rejected():
    desk, fake = await connected_desk(ReminderBleak())
    fake.on_write = lambda: setattr(desk, "_generation", desk._generation + 1)
    with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.02):
        with pytest.raises((DeskLinkLost, TimeoutError)):
            await desk.set_reminder_profile(2)
    assert len(settings_writes(fake)) == 1
    assert not desk.connected


async def test_reminder_reservation_excludes_motion_calibration_polling_and_another_setter():
    from custom_components.ha_linak.calibration import HeightCalibration

    desk, fake = await connected_desk(ReminderBleak())
    fake.hang = True
    task = asyncio.create_task(desk.set_reminder_profile(2))
    await fake.written.wait()
    count = len(fake.writes)
    assert await desk.refresh() is desk.state
    for operation in [
        desk.set_reminder_profile(3),
        desk.move_to_cm(83, ControlSettings.from_options(OPTIONS)),
        desk.calibrate_height(
            HeightCalibration.prepare(desk.state.position, desk.state.offset_raw, 83)
        ),
    ]:
        with pytest.raises(MotionError):
            await operation
    assert len(fake.writes) == count
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def setup_select(hass, fake=None, *, entry=None):
    fake = fake or ReminderBleak()
    if entry is None:
        entry = MockConfigEntry(
            domain=DOMAIN, title="Desk", unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
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
    return entry, fake, hass.states.async_all("select")[0].entity_id


async def test_real_select_service_updates_existing_sensor_without_travel_range(hass):
    entry, fake, entity_id = await setup_select(hass)
    assert entry.runtime_data.controls is None
    registry = er.async_get(hass)
    select = registry.async_get(entity_id)
    sensor = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{ADDRESS}_reminder_profile"
    )
    assert select.unique_id == f"{ADDRESS}_reminder_profile"
    assert select.entity_category.value == "config"
    assert sensor is not None
    assert hass.states.get(entity_id).state == "profile_1"
    assert hass.states.get(entity_id).attributes["options"] == [
        "off",
        "profile_1",
        "profile_2",
        "profile_3",
    ]
    assert not settings_writes(fake)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "profile_2"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "profile_2"
    assert hass.states.get(sensor).state == "2"
    fake.activation = 0
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "off"},
            blocking=True,
        )
    assert exc.value.translation_key == "reminder_client_inactive"
    fake.activation = 1
    fake.mismatch = 1
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "off"},
            blocking=True,
        )
    assert exc.value.translation_key == "reminder_failed"
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    assert hass.states.get(sensor).state == "unavailable"
    desk = entry.runtime_data.desk
    await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get(entity_id).attributes["restored"]
    assert not desk.connected


async def test_motion_reservation_refuses_reminder_without_any_packets():
    desk, fake = await connected_desk(ReminderBleak())
    fake.stall = True
    task = asyncio.create_task(
        desk.move_to_cm(83, ControlSettings.from_options(OPTIONS))
    )
    await fake.target_written.wait()
    before = list(fake.writes)
    with pytest.raises(MotionError) as exc:
        await desk.set_reminder_profile(2)
    assert exc.value.reason.value == "busy"
    assert fake.writes == before
    await desk.stop()
    with pytest.raises(MotionError):
        await task
    await desk.disconnect()


async def test_select_group_availability_and_busy_error(hass):
    entry, fake, entity_id = await setup_select(hass)
    desk = entry.runtime_data.desk
    desk.settings_health["reminders"].valid = False
    entry.runtime_data._changed()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    desk.settings_health["reminders"].valid = True
    entry.runtime_data._changed()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "profile_1"
    await desk._lock.acquire()
    try:
        with pytest.raises(ServiceValidationError) as exc:
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": "profile_3"},
                blocking=True,
            )
        assert exc.value.translation_key == "control_busy"
        assert not settings_writes(fake)
    finally:
        desk._lock.release()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_repeated_cancellation_waits_for_disconnect_cleanup():
    desk, fake = await connected_desk(ReminderBleak())
    fake.hang = True
    started, finish = asyncio.Event(), asyncio.Event()
    original = fake.disconnect

    async def delayed_disconnect():
        started.set()
        await finish.wait()
        await original()

    fake.disconnect = delayed_disconnect
    task = asyncio.create_task(desk.set_reminder_profile(2))
    await fake.written.wait()
    task.cancel()
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert desk.control_busy
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not desk.control_busy
    assert not fake.is_connected
    assert len(settings_writes(fake)) == 1


@pytest.mark.parametrize("phase", ["before_write", "readback"])
@pytest.mark.parametrize("change", ["capabilities", "generation"])
async def test_barrier_changes_abort_and_never_replay(phase, change):
    from custom_components.ha_linak.protocol import ReadCommand

    desk, fake = await connected_desk(ReminderBleak())
    original = desk._query
    barriers = 0

    async def query(command, response_type, **kwargs):
        nonlocal barriers
        payload = await original(command, response_type, **kwargs)
        if command == ReadCommand.CAPABILITIES:
            barriers += 1
            if barriers == (2 if phase == "before_write" else 3):
                if change == "generation":
                    desk._generation += 1
                else:
                    return payload[:2] + bytes([payload[2] ^ 8]) + payload[3:]
        return payload

    desk._query = query
    with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.02):
        with pytest.raises((ValueError, DeskLinkLost, TimeoutError)):
            await desk.set_reminder_profile(2)
    assert len(settings_writes(fake)) == (0 if phase == "before_write" else 1)
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert not desk.connected


async def test_position_change_during_preflight_prevents_write():
    from custom_components.ha_linak.protocol import ReadCommand

    desk, fake = await connected_desk(ReminderBleak())
    original = desk._query

    async def query(command, response_type, **kwargs):
        payload = await original(command, response_type, **kwargs)
        if command == ReadCommand.USER_ID:
            fake.position += 1
        return payload

    desk._query = query
    with pytest.raises(ValueError, match="position changed"):
        await desk.set_reminder_profile(2)
    assert not settings_writes(fake)
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)


async def test_unknown_reminder_layout_is_not_encoded():
    settings = ReminderSettings(0, ((1, 2),), 0)
    with pytest.raises(ValueError, match="three interval pairs"):
        reminder_profile_request(settings, 1)


async def test_coordinator_rejects_conflict_and_missing_connection(hass):
    entry, fake, _ = await setup_select(hass)
    coordinator = entry.runtime_data
    before = list(fake.writes)
    with patch(
        "custom_components.ha_linak.coordinator.has_idasen_conflict", return_value=True
    ):
        with pytest.raises(HomeAssistantError) as exc:
            await coordinator.async_set_reminder_profile(2)
    assert exc.value.translation_key == "idasen_conflict"
    assert fake.writes == before
    await coordinator.desk.disconnect()
    with pytest.raises(HomeAssistantError) as exc:
        await coordinator.async_set_reminder_profile(2)
    assert exc.value.translation_key == "control_unavailable"
    await hass.config_entries.async_unload(entry.entry_id)
