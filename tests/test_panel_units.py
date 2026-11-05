"""Stored inch/metric preference with synthetic BLE and actual HA services."""

import asyncio
from copy import deepcopy
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
    decode_reminders,
    reminder_request,
    reminder_unit_request,
)
from test_native_controls import ADDRESS, OPTIONS, connected_desk
from test_reminder_profile import ReminderBleak, settings_writes, setup_select


def assert_only_unit_io(fake, writes):
    """No control channel, reference, activation, target or other setting writes."""
    for uuid, payload in fake.writes:
        assert uuid == DPG_UUID
        assert payload in (
            b"\x7f\x80\x00",
            b"\x7f\x86\x00",
            b"\x7f\x88\x00",
            *writes,
        )
    assert settings_writes(fake) == writes


@pytest.mark.parametrize("flags", range(256))
@pytest.mark.parametrize("inch", [False, True])
def test_codec_changes_only_bit04_and_never_invents_a_metric_subunit(flags, inch):
    settings = ReminderSettings(flags, ((0, 255), (90, 0), (255, 17)), 0xFFFFFFFF)
    expected = (flags & ~4) | (4 if inch else 0)
    request = reminder_unit_request(settings, inch)
    assert request == b"\x7f\x88\x80" + bytes((expected, 0, 255, 90, 0, 255, 17))
    assert len(request) == 10
    decoded = decode_reminders(b"\x01\x0b" + request[3:] + bytes(4))
    assert decoded.inch_preference is inch
    assert decoded.selected_profile == settings.selected_profile
    assert settings.flags_raw == flags
    assert settings.inch_preference is bool(flags & 4)


@pytest.mark.parametrize("value", [0, 1, None, "mm", "cm", "inch", 4])
async def test_invalid_preference_is_refused_before_io(value):
    desk, fake = await connected_desk(ReminderBleak())
    fake.writes.clear()
    with pytest.raises(ValueError):
        reminder_unit_request(desk.state.reminders, value)
    with pytest.raises(ValueError):
        await desk.set_panel_unit_preference(value)
    assert fake.writes == []
    await desk.disconnect()


@pytest.mark.parametrize("pairs", [(), ((1, 2),), ((1,), (2, 3), (4, 5, 6))])
def test_unknown_layout_is_never_encoded(pairs):
    settings = ReminderSettings(0, pairs, 0)
    with pytest.raises(ValueError, match="three interval pairs"):
        reminder_unit_request(settings, True)


@pytest.mark.parametrize("flags", range(256))
@pytest.mark.parametrize("inch", [False, True])
async def test_fresh_transaction_preserves_all_other_bits_and_geometry(flags, inch):
    fake = ReminderBleak()
    fake.body = bytes((flags, 0, 255, 90, 0, 255, 17))
    desk, fake = await connected_desk(fake)
    before = deepcopy(desk.state)
    memory_health = deepcopy(desk.settings_health["memories"])
    # Stale cache must not supply either no-op detection or preserved bytes.
    desk.state.reminders = ReminderSettings(flags ^ 4, ((1, 2),) * 3, 99)
    fake.echo = True
    fake.writes.clear()
    expected = reminder_unit_request(before.reminders, inch)
    changed = before.reminders.inch_preference != inch
    result = await desk.set_panel_unit_preference(inch)
    assert reminder_request(result.reminders) == expected
    assert result.reminders.inch_preference is inch
    assert result.reminders.counter_raw == (165 if changed else 42)
    assert_only_unit_io(fake, [expected] if changed else [])
    requests = [data for _, data in fake.writes]
    if changed:
        assert requests == [
            b"\x7f\x80\x00",
            b"\x7f\x88\x00",
            b"\x7f\x86\x00",
            b"\x7f\x80\x00",
            expected,
            b"\x7f\x80\x00",
            b"\x7f\x88\x00",
        ]
    else:
        assert requests == [b"\x7f\x80\x00", b"\x7f\x88\x00"]
    assert replace(result, reminders=before.reminders) == before
    assert desk.settings_health["memories"] == memory_health
    assert desk.settings_health["reminders"].valid
    assert desk.connected
    await desk.disconnect()


async def test_noop_does_not_require_active_client():
    desk, fake = await connected_desk(ReminderBleak())
    fake.activation = 0
    fake.writes.clear()
    await desk.set_panel_unit_preference(True)
    assert_only_unit_io(fake, [])
    assert b"\x7f\x86\x00" not in [data for _, data in fake.writes]
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize("status", [0, 2])
async def test_inactive_or_unknown_identity_never_activates(status):
    desk, fake = await connected_desk(ReminderBleak())
    fake.activation = status
    fake.writes.clear()
    with pytest.raises(ReminderClientInactive if status == 0 else ValueError):
        await desk.set_panel_unit_preference(False)
    assert_only_unit_io(fake, [])
    assert desk.connected == (status == 0)
    await desk.disconnect()


@pytest.mark.parametrize(
    "kind", ["group", "disconnected", "speed", "lock", "capabilities", "malformed"]
)
async def test_bad_preflight_never_writes(kind):
    desk, fake = await connected_desk(ReminderBleak())
    fake.writes.clear()
    if kind == "group":
        desk.settings_health["reminders"].valid = False
    elif kind == "disconnected":
        await desk.disconnect()
    elif kind == "speed":
        fake.speed = 1
    elif kind == "lock":
        await desk._lock.acquire()
    elif kind == "capabilities":
        desk.state.capabilities = replace(desk.state.capabilities, flags_raw=0)
    else:
        fake.bad_read = True
    try:
        with pytest.raises((MotionError, ValueError)):
            await desk.set_panel_unit_preference(False)
        assert_only_unit_io(fake, [])
    finally:
        if kind == "lock":
            desk._lock.release()
        await desk.disconnect()


@pytest.mark.parametrize(
    "ack", [b"", b"\x01", b"\x0b\x00", b"\x01\x01", b"\x01\x00\x01", b"\x00\x00"]
)
async def test_att_success_is_not_exact_application_success(ack):
    desk, fake = await connected_desk(ReminderBleak())
    fake.ack = ack
    fake.writes.clear()
    expected = reminder_unit_request(desk.state.reminders, False)
    with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.02):
        with pytest.raises((ValueError, TimeoutError)):
            await desk.set_panel_unit_preference(False)
    assert_only_unit_io(fake, [expected])
    assert not desk.connected
    assert not desk.settings_health["reminders"].valid


@pytest.mark.parametrize("byte", range(7))
async def test_every_body_byte_is_verified_from_independent_readback(byte):
    desk, fake = await connected_desk(ReminderBleak())
    fake.mismatch = byte
    fake.echo = True
    fake.writes.clear()
    expected = reminder_unit_request(desk.state.reminders, False)
    with pytest.raises(ValueError, match="readback mismatch"):
        await desk.set_panel_unit_preference(False)
    assert_only_unit_io(fake, [expected])
    assert not desk.connected


async def test_malformed_readback_is_not_success():
    desk, fake = await connected_desk(ReminderBleak())
    fake.on_write = lambda: setattr(fake, "bad_read", True)
    with pytest.raises(ValueError):
        await desk.set_panel_unit_preference(False)
    assert len(settings_writes(fake)) == 1
    assert not desk.connected


@pytest.mark.parametrize("phase", ["fresh_read", "write", "readback"])
@pytest.mark.parametrize("ending", ["timeout", "cancel", "disconnect", "link_loss"])
async def test_interruption_discards_generation_and_never_replays(phase, ending):
    desk, fake = await connected_desk(ReminderBleak())
    generation = desk._generation
    expected = reminder_unit_request(desk.state.reminders, False)
    fake.writes.clear()
    fake.read_started.clear()
    fake.hang_read = phase == "fresh_read"
    fake.hang = phase == "write"
    if phase == "readback":

        def hang_readback():
            fake.read_started.clear()
            fake.hang_read = True

        fake.on_write = hang_readback
    started = fake.read_started if phase == "fresh_read" else fake.written
    with patch(
        "custom_components.ha_linak.client.QUERY_TIMEOUT",
        0.04 if ending == "timeout" else 8,
    ):
        task = asyncio.create_task(desk.set_panel_unit_preference(False))
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
    writes = [] if phase == "fresh_read" else [expected]
    assert_only_unit_io(fake, writes)
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
    assert settings_writes(fake) == writes
    await desk.disconnect()


@pytest.mark.parametrize("phase", ["before_write", "readback"])
@pytest.mark.parametrize("change", ["capabilities", "generation", "position"])
async def test_generation_capabilities_and_stationary_barriers(phase, change):
    desk, fake = await connected_desk(ReminderBleak())
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
            await desk.set_panel_unit_preference(False)
    assert len(settings_writes(fake)) == (
        0 if phase == "before_write" or change == "position" else 1
    )
    assert not desk.connected


@pytest.mark.parametrize("owner", ["unit", "profile", "interval", "motion"])
async def test_foreground_operations_cannot_queue_or_compete(owner):
    desk, fake = await connected_desk(ReminderBleak())
    controls = ControlSettings.from_options(OPTIONS)
    fake.hang_read = fake.stall = True
    fake.read_started.clear()
    operations = {
        "unit": lambda: desk.set_panel_unit_preference(False),
        "profile": lambda: desk.set_reminder_profile(2),
        "interval": lambda: desk.set_reminder_sitting_minutes(50),
        "motion": lambda: desk.move_to_cm(83, controls),
    }
    task = asyncio.create_task(operations[owner]())
    await asyncio.wait_for(
        (fake.target_written if owner == "motion" else fake.read_started).wait(), 1
    )
    writes = list(fake.writes)
    for operation in [
        *[factory() for factory in operations.values()],
        desk.calibrate_height(
            HeightCalibration.prepare(desk.state.position, desk.state.offset_raw, 83)
        ),
    ]:
        with pytest.raises(MotionError):
            await operation
    assert await desk.refresh() is desk.state
    assert fake.writes == writes
    if owner == "motion":
        await desk.stop()
        with pytest.raises(MotionError):
            await task
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    await desk.disconnect()


def unit_entity(hass):
    return er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{ADDRESS}_panel_unit_preference"
    )


async def test_real_ha_config_select_and_services_preserve_native_centimeters(hass):
    entry, fake, profile = await setup_select(hass)
    entity_id = unit_entity(hass)
    registry = er.async_get(hass)
    assert registry.async_get(entity_id).entity_category.value == "config"
    assert entry.runtime_data.controls is None
    state = hass.states.get(entity_id)
    assert state.state == "inch"
    assert state.attributes["options"] == ["metric", "inch"]
    before = {
        state.entity_id: state
        for state in hass.states.async_all()
        if state.attributes.get("unit_of_measurement") == "cm"
    }
    assert before
    fake.writes.clear()
    for option in ("metric", "metric", "inch"):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == option
        assert hass.states.get(profile).state == "profile_1"
        for other_id, original in before.items():
            current = hass.states.get(other_id)
            assert current.state == original.state
            assert current.attributes == original.attributes
    assert len(settings_writes(fake)) == 2
    assert_only_unit_io(fake, settings_writes(fake))
    for invalid in ("mm", "cm"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": invalid},
                blocking=True,
            )
    assert len(settings_writes(fake)) == 2
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "kind, key",
    [
        ("inactive", "reminder_client_inactive"),
        ("busy", "control_busy"),
        ("conflict", "idasen_conflict"),
        ("offline", "control_unavailable"),
        ("readback", "reminder_failed"),
    ],
)
async def test_service_and_coordinator_errors_never_publish_success(hass, kind, key):
    entry, fake, _ = await setup_select(hass)
    entity_id = unit_entity(hass)
    desk = entry.runtime_data.desk
    if kind == "inactive":
        fake.activation = 0
    elif kind == "busy":
        await desk._lock.acquire()
    elif kind == "offline":
        await desk.disconnect()
        entry.runtime_data._changed()
    elif kind == "readback":
        fake.mismatch = 0
    if kind == "offline":
        # HA filters unavailable entities before service dispatch.
        change = entry.runtime_data.async_set_panel_unit_preference(False)
    else:
        change = hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "metric"},
            blocking=True,
        )
    try:
        with patch(
            "custom_components.ha_linak.coordinator.has_idasen_conflict",
            return_value=kind == "conflict",
        ):
            with pytest.raises(HomeAssistantError) as exc:
                await change
        assert exc.value.translation_key == key
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == (
            "unavailable" if kind in ("offline", "readback") else "inch"
        )
        assert entry.runtime_data.data.reminders.inch_preference
        assert len(settings_writes(fake)) == (1 if kind == "readback" else 0)
    finally:
        if kind == "busy":
            desk._lock.release()
        await hass.config_entries.async_unload(entry.entry_id)


async def test_group_availability_is_independent_of_memories(hass):
    entry, fake, _ = await setup_select(hass)
    entity_id = unit_entity(hass)
    desk = entry.runtime_data.desk
    desk.settings_health["memories"].valid = False
    entry.runtime_data._changed()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "inch"
    desk.settings_health["reminders"].valid = False
    entry.runtime_data._changed()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    assert not settings_writes(fake)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_repeated_cancellation_keeps_reservation_until_cleanup_finishes():
    desk, fake = await connected_desk(ReminderBleak())
    fake.hang = True
    started, finish = asyncio.Event(), asyncio.Event()
    original = fake.disconnect

    async def delayed_disconnect():
        started.set()
        await finish.wait()
        await original()

    fake.disconnect = delayed_disconnect
    task = asyncio.create_task(desk.set_panel_unit_preference(False))
    await asyncio.wait_for(fake.written.wait(), 1)
    task.cancel()
    await asyncio.wait_for(started.wait(), 1)
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


@pytest.mark.parametrize("inch", [False, True])
async def test_lost_generation_after_baseline_cannot_pass_even_as_a_noop(inch):
    desk, fake = await connected_desk(ReminderBleak())
    original = desk._query

    async def query(command, response_type, **kwargs):
        payload = await original(command, response_type, **kwargs)
        if command == ReadCommand.REMINDERS:
            desk._generation += 1
        return payload

    desk._query = query
    with pytest.raises(DeskLinkLost):
        await desk.set_panel_unit_preference(inch)
    assert not settings_writes(fake)
    assert not desk.connected
