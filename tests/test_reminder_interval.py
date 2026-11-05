"""Single-field reminder edits with synthetic BLE and actual HA services."""

import asyncio
from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.ha_linak.calibration import HeightCalibration
from custom_components.ha_linak.client import DeskLinkLost
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.motion import MotionError
from custom_components.ha_linak.protocol import (
    DPG_UUID,
    ReadCommand,
    ReminderClientInactive,
    ReminderSettings,
    reminder_request,
    reminder_sitting_request,
)
from custom_components.ha_linak.reminder_settings import (
    InvalidReminderInterval,
    ReminderProfileActive,
)
from test_native_controls import ADDRESS, OPTIONS, connected_desk
from test_reminder_profile import ReminderBleak, settings_writes, setup_select


class IntervalBleak(ReminderBleak):
    def __init__(self):
        super().__init__()
        # Deliberately outside the host edit policy, including untouched extremes.
        self.body = bytes((0xEF, 90, 0, 0, 255, 255, 0))


@pytest.mark.parametrize("flags", range(256))
def test_codec_changes_only_one_byte_and_never_normalizes_pairs(flags):
    settings = ReminderSettings(flags, ((90, 0), (0, 255), (255, 0)), 0xFFFFFFFF)
    for minutes in (0, 1, 50, 55, 60, 255):
        request = reminder_sitting_request(settings, minutes)
        assert request == b"\x7f\x88\x80" + bytes((flags, minutes, 0, 0, 255, 255, 0))
        assert len(request) == 10
    assert settings.profiles_raw[0][0] == 90
    assert reminder_request(settings)[4] == 90


@pytest.mark.parametrize("pairs", [(), ((1, 2),), ((1,), (2, 3), (4, 5, 6))])
def test_codec_requires_exact_layout(pairs):
    settings = ReminderSettings(3, pairs, 0)
    with pytest.raises(ValueError, match="three interval pairs"):
        reminder_sitting_request(settings, 50)


@pytest.mark.parametrize("value", [-1, 256, True, 50.0, "50", None])
def test_codec_rejects_non_byte_input(value):
    settings = ReminderSettings(3, ((1, 2), (3, 4), (5, 6)), 0)
    with pytest.raises(ValueError):
        reminder_sitting_request(settings, value)


@pytest.mark.parametrize(
    "value", [0, -1, 61, 255, 50.5, True, "50", None, float("nan"), float("inf")]
)
async def test_invalid_input_is_refused_before_any_io(value):
    desk, fake = await connected_desk(IntervalBleak())
    fake.writes.clear()
    with pytest.raises(InvalidReminderInterval):
        await desk.set_reminder_sitting_minutes(value)
    assert fake.writes == []
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize("minutes", [1, 50, 55.0, 60])
@pytest.mark.parametrize("profile", [0, 2, 3])
async def test_fresh_single_field_transaction_and_returned_state(minutes, profile):
    fake = IntervalBleak()
    fake.body = bytes(((fake.body[0] & ~3) | profile,)) + fake.body[1:]
    desk, fake = await connected_desk(fake)
    before = desk.state
    memories = list(before.memories)
    desk.state.reminders = ReminderSettings(1, ((55, 5), (10, 20), (30, 40)), 99)
    fake.echo = True
    fake.writes.clear()
    result = await desk.set_reminder_sitting_minutes(minutes)
    expected = fake.body[:1] + bytes((int(minutes),)) + bytes((0, 0, 255, 255, 0))
    assert settings_writes(fake) == [b"\x7f\x88\x80" + expected]
    assert reminder_request(result.reminders) == b"\x7f\x88\x80" + expected
    assert result.reminders.counter_raw == 165
    assert result.memories == memories
    assert result.offset_raw == before.offset_raw
    assert result.capabilities == before.capabilities
    assert [data for _, data in fake.writes][-2:] == [
        b"\x7f\x80\x00",
        b"\x7f\x88\x00",
    ]
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert desk.connected
    assert desk.settings_health["reminders"].valid
    await desk.disconnect()


async def test_pair_50_5_is_not_changed_to_total_60():
    fake = IntervalBleak()
    fake.body = bytes((0xEF, 55, 5, 12, 3, 27, 8))
    desk, fake = await connected_desk(fake)
    await desk.set_reminder_sitting_minutes(50)
    assert desk.state.reminders.profiles_raw == ((50, 5), (12, 3), (27, 8))
    await desk.disconnect()


async def test_noop_uses_fresh_value_without_status_check_even_if_profile_is_active():
    fake = IntervalBleak()
    fake.body = bytes((0xED, 50)) + fake.body[2:]
    desk, fake = await connected_desk(fake)
    desk.state.reminders = replace(desk.state.reminders, profiles_raw=((55, 0),) * 3)
    fake.activation = 0
    fake.writes.clear()
    await desk.set_reminder_sitting_minutes(50)
    assert not settings_writes(fake)
    assert b"\x7f\x86\x00" not in [data for _, data in fake.writes]
    assert desk.state.reminders.profiles_raw[0] == (50, 0)
    assert desk.connected
    await desk.disconnect()


async def test_active_profile_is_refused_from_fresh_state_without_disconnecting():
    desk, fake = await connected_desk(IntervalBleak())
    fake.body = bytes(((fake.body[0] & ~3) | 1,)) + fake.body[1:]
    with pytest.raises(ReminderProfileActive):
        await desk.set_reminder_sitting_minutes(50)
    assert not settings_writes(fake)
    assert desk.connected
    assert not desk.control_busy
    await desk.disconnect()


async def test_policy_refusal_cannot_hide_a_lost_generation():
    desk, fake = await connected_desk(IntervalBleak())
    fake.body = bytes((0xED,)) + fake.body[1:]
    original = desk._query

    async def query(command, response_type, **kwargs):
        payload = await original(command, response_type, **kwargs)
        if command == ReadCommand.REMINDERS:
            desk._generation += 1
        return payload

    desk._query = query
    with pytest.raises(DeskLinkLost):
        await desk.set_reminder_sitting_minutes(50)
    assert not settings_writes(fake)
    assert not desk.connected


async def test_profile_selection_preserves_out_of_policy_duration():
    desk, fake = await connected_desk(IntervalBleak())
    await desk.set_reminder_profile(1)
    assert desk.state.reminders.profiles_raw == ((90, 0), (0, 255), (255, 0))
    assert settings_writes(fake)[0][4] == 90
    await desk.disconnect()


@pytest.mark.parametrize("status", [0, 2])
async def test_inactive_or_unknown_identity_never_activates(status):
    desk, fake = await connected_desk(IntervalBleak())
    fake.activation = status
    with pytest.raises(ReminderClientInactive if status == 0 else ValueError):
        await desk.set_reminder_sitting_minutes(50)
    assert not settings_writes(fake)
    assert desk.connected == (status == 0)
    await desk.disconnect()


@pytest.mark.parametrize(
    "ack", [b"\x0b\x00", b"\x01\x01", b"\x01\x00\x01", b"\x00\x00"]
)
async def test_bad_ack_discards_session_without_restoration(ack):
    desk, fake = await connected_desk(IntervalBleak())
    fake.ack = ack
    with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.02):
        with pytest.raises((ValueError, TimeoutError)):
            await desk.set_reminder_sitting_minutes(50)
    assert len(settings_writes(fake)) == 1
    assert not desk.connected
    assert not desk.settings_health["reminders"].valid


@pytest.mark.parametrize("byte", range(7))
async def test_each_body_byte_must_match_independent_readback(byte):
    desk, fake = await connected_desk(IntervalBleak())
    fake.mismatch = byte
    with pytest.raises(ValueError, match="readback mismatch"):
        await desk.set_reminder_sitting_minutes(50)
    assert len(settings_writes(fake)) == 1
    assert not desk.connected


@pytest.mark.parametrize("phase", ["fresh_read", "write", "readback"])
@pytest.mark.parametrize("ending", ["timeout", "cancel", "disconnect", "link_loss"])
async def test_interruption_invalidates_generation_and_reconnect_never_replays(
    phase, ending
):
    desk, fake = await connected_desk(IntervalBleak())
    generation = desk._generation
    fake.read_started.clear()
    fake.hang_read = phase == "fresh_read"
    fake.hang = phase == "write"
    if phase == "readback":

        def hang_readback():
            fake.read_started.clear()
            fake.hang_read = True

        fake.on_write = hang_readback
    started = fake.written if phase == "write" else fake.read_started
    if phase == "readback":
        # The fresh read also sets the event; wait for the setter before readback.
        started = fake.written
    with patch(
        "custom_components.ha_linak.client.QUERY_TIMEOUT",
        0.04 if ending == "timeout" else 8,
    ):
        task = asyncio.create_task(desk.set_reminder_sitting_minutes(50))
        await asyncio.wait_for(started.wait(), 1)
        if phase == "readback":
            await asyncio.wait_for(fake.read_started.wait(), 1)
        if ending == "cancel":
            task.cancel()
        elif ending == "disconnect":
            await desk.disconnect()
        elif ending == "link_loss":
            fake.is_connected = False
            desk._disconnected(fake)
        with pytest.raises((TimeoutError, asyncio.CancelledError, DeskLinkLost)):
            await task
    count = 0 if phase == "fresh_read" else 1
    assert len(settings_writes(fake)) == count
    assert desk._generation > generation
    assert not desk.connected
    assert not desk.control_busy
    fake.hang = fake.hang_read = False
    fake.on_write = None
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        side_effect=fake.reconnect,
    ):
        await desk.refresh()
    assert len(settings_writes(fake)) == count
    await desk.disconnect()


@pytest.mark.parametrize("kind", ["group", "speed", "capabilities", "malformed"])
async def test_bad_preflight_never_writes(kind):
    desk, fake = await connected_desk(IntervalBleak())
    if kind == "group":
        desk.settings_health["reminders"].valid = False
    elif kind == "speed":
        fake.speed = 1
    elif kind == "capabilities":
        desk.state.capabilities = replace(desk.state.capabilities, flags_raw=0)
    else:
        fake.bad_read = True
    with pytest.raises((MotionError, ValueError)):
        await desk.set_reminder_sitting_minutes(50)
    assert not settings_writes(fake)
    await desk.disconnect()


@pytest.mark.parametrize("owner", ["profile", "interval"])
async def test_setters_and_other_foreground_operations_cannot_queue(owner):
    desk, fake = await connected_desk(IntervalBleak())
    fake.hang_read = True
    fake.read_started.clear()
    first = (
        desk.set_reminder_profile(2)
        if owner == "profile"
        else desk.set_reminder_sitting_minutes(50)
    )
    task = asyncio.create_task(first)
    await fake.read_started.wait()
    writes = list(fake.writes)
    operations = [
        desk.set_reminder_profile(0),
        desk.set_reminder_sitting_minutes(55),
        desk.move_to_cm(83, ControlSettings.from_options(OPTIONS)),
        desk.calibrate_height(
            HeightCalibration.prepare(desk.state.position, desk.state.offset_raw, 83)
        ),
    ]
    for operation in operations:
        with pytest.raises(MotionError):
            await operation
    assert await desk.refresh() is desk.state
    assert fake.writes == writes
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("phase", ["before_write", "readback"])
@pytest.mark.parametrize("change", ["capabilities", "generation", "position"])
async def test_session_and_stationary_barriers_are_shared(phase, change):
    desk, fake = await connected_desk(IntervalBleak())
    original = desk._query
    barriers = 0

    async def query(command, response_type, **kwargs):
        nonlocal barriers
        payload = await original(command, response_type, **kwargs)
        if change == "position" and command == ReadCommand.USER_ID:
            fake.position += 1
        if command == ReadCommand.CAPABILITIES:
            barriers += 1
            if barriers == (2 if phase == "before_write" else 3):
                if change == "generation":
                    desk._generation += 1
                elif change == "capabilities":
                    return payload[:2] + bytes((payload[2] ^ 8,)) + payload[3:]
        return payload

    desk._query = query
    with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.02):
        with pytest.raises((ValueError, DeskLinkLost, TimeoutError)):
            await desk.set_reminder_sitting_minutes(50)
    count = 0 if phase == "before_write" or change == "position" else 1
    assert len(settings_writes(fake)) == count
    assert not desk.connected


def entity_ids(hass):
    registry = er.async_get(hass)
    return tuple(
        registry.async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}")
        for platform, key in (
            ("number", "reminder_1_sitting_time"),
            ("button", "reminder_1_standard_time"),
            ("sensor", "reminder_1_sit"),
        )
    )


async def test_real_number_box_and_standard_button_preserve_existing_outlier(hass):
    entry, fake, _ = await setup_select(hass, IntervalBleak())
    number, button, sensor = entity_ids(hass)
    registry = er.async_get(hass)
    assert entry.runtime_data.controls is None
    assert registry.async_get(number).entity_category.value == "config"
    assert registry.async_get(button).entity_category.value == "config"
    assert registry.async_get(sensor).entity_category is None
    state = hass.states.get(number)
    assert state.state == "90"
    assert hass.states.get(sensor).state == "90"
    assert state.attributes["mode"] == "box"
    assert state.attributes["unit_of_measurement"] == "min"
    assert state.attributes["min"] == 1
    assert state.attributes["max"] == 60
    assert state.attributes["step"] == 1
    assert not settings_writes(fake)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number, "value": 50}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(number).state == "50"
    assert hass.states.get(sensor).state == "50"
    assert len(settings_writes(fake)) == 1
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(number).state == "55"
    assert hass.states.get(sensor).state == "55"
    assert settings_writes(fake)[-1] == b"\x7f\x88\x80" + bytes(
        (0xEF, 55, 0, 0, 255, 255, 0)
    )
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("value", [0, 61, 50.5])
async def test_ha_invalid_input_never_writes(hass, value):
    entry, fake, _ = await setup_select(hass, IntervalBleak())
    number, _, _ = entity_ids(hass)
    writes = list(fake.writes)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": number, "value": value}, blocking=True
        )
    assert fake.writes == writes
    assert hass.states.get(number).state == "90"
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "kind, key",
    [
        ("invalid", "reminder_interval_invalid"),
        ("active", "reminder_profile_active"),
        ("inactive", "reminder_client_inactive"),
        ("busy", "control_busy"),
        ("conflict", "idasen_conflict"),
        ("offline", "control_unavailable"),
    ],
)
async def test_coordinator_maps_refusals_without_setting_writes(hass, kind, key):
    entry, fake, _ = await setup_select(hass, IntervalBleak())
    coordinator = entry.runtime_data
    desk = coordinator.desk
    if kind == "active":
        fake.body = bytes((0xED,)) + fake.body[1:]
    elif kind == "inactive":
        fake.activation = 0
    elif kind == "offline":
        await desk.disconnect()
    elif kind == "busy":
        await desk._lock.acquire()
    try:
        with patch(
            "custom_components.ha_linak.coordinator.has_idasen_conflict",
            return_value=kind == "conflict",
        ):
            with pytest.raises(HomeAssistantError) as exc:
                await coordinator.async_set_reminder_sitting_minutes(
                    50.5 if kind == "invalid" else 50
                )
        assert exc.value.translation_key == key
        assert not settings_writes(fake)
    finally:
        if kind == "busy":
            desk._lock.release()
        await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_write_is_not_published_as_success_and_controls_become_unavailable(
    hass,
):
    entry, fake, _ = await setup_select(hass, IntervalBleak())
    number, button, sensor = entity_ids(hass)
    fake.mismatch = 2
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": number, "value": 50}, blocking=True
        )
    assert exc.value.translation_key == "reminder_failed"
    await hass.async_block_till_done()
    for entity_id in (number, button, sensor):
        assert hass.states.get(entity_id).state == "unavailable"
    assert len(settings_writes(fake)) == 1
    assert entry.runtime_data.data.reminders.profiles_raw[0][0] == 90
    await hass.config_entries.async_unload(entry.entry_id)


async def test_both_controls_follow_group_validity(hass):
    entry, fake, _ = await setup_select(hass, IntervalBleak())
    number, button, _ = entity_ids(hass)
    entry.runtime_data.desk.settings_health["reminders"].valid = False
    entry.runtime_data._changed()
    await hass.async_block_till_done()
    assert hass.states.get(number).state == "unavailable"
    assert hass.states.get(button).state == "unavailable"
    assert not settings_writes(fake)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_standard_button_is_explicit_and_never_switches_an_active_profile(hass):
    fake = IntervalBleak()
    fake.body = bytes((0xED, 50)) + fake.body[2:]
    entry, fake, select = await setup_select(hass, fake)
    number, button, _ = entity_ids(hass)
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=True
        )
    assert exc.value.translation_key == "reminder_profile_active"
    assert not settings_writes(fake)
    assert hass.states.get(select).state == "profile_1"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "off"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(number).state == "55"
    assert hass.states.get(select).state == "off"
    assert len(settings_writes(fake)) == 2
    await hass.config_entries.async_unload(entry.entry_id)
