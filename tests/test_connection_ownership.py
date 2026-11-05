"""Deliberate connection ownership: intent, polling, races and recovery, simulated."""

import asyncio
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.connection_intent import (
    CONF_KEEP_CONNECTED,
    wants_connection,
)
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_linak.motion import (
    CONTROL_UUID,
    REFERENCE_STOP,
    STOP,
    TARGET_UUID,
)
from custom_components.ha_linak.protocol import DPG_UUID
from custom_components.ha_linak.setup_session import offer_session
from custom_components.ha_linak.switch import LinakKeepConnectedSwitch
from homeassistant.const import CONF_ADDRESS
from test_native_controls import ADDRESS, DEVICE, OPTIONS, MotionBleak

SWITCH = "switch.desk_keep_connected"


@pytest.fixture(autouse=True)
def enabled_switch():
    """The switch is disabled by default; these tests act as an owner who enabled it."""
    with patch.object(
        LinakKeepConnectedSwitch, "_attr_entity_registry_enabled_default", True
    ):
        yield


CONNECTION = "binary_sensor.desk_connection"
HEIGHT = "sensor.desk_height"
OPERATION = "sensor.desk_operation"
FAST = "custom_components.ha_linak.motion.COMMAND_INTERVAL"
HOLD = 60


@contextmanager
def radio(fake):
    """The only radio the test allows, with counters for what was attempted."""
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ) as lookup,
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ) as connect,
    ):
        yield lookup, connect


async def add_entry(hass, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Desk",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, **data},
        options=OPTIONS,
    )
    entry.add_to_hass(hass)
    return entry


async def start(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def switch(hass, service):
    await hass.services.async_call(
        "switch", service, {"entity_id": SWITCH}, blocking=True
    )


async def tick(hass, seconds=61):
    """Fire the scheduled poll and let its task finish."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    for _ in range(6):
        await asyncio.sleep(0.02)
    await hass.async_block_till_done()


def dpg_writes(fake):
    return [data for uuid, data in fake.writes if uuid == DPG_UUID]


def motion_writes(fake):
    return [
        (uuid, data)
        for uuid, data in fake.writes
        if uuid in (CONTROL_UUID, TARGET_UUID)
    ]


async def test_an_existing_entry_stays_connected_and_gets_the_switch(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    assert CONF_KEEP_CONNECTED not in entry.data
    with radio(fake):
        await start(hass, entry)
        assert hass.states.get(SWITCH).state == "on"
        assert hass.states.get(CONNECTION).state == "on"
        item = er.async_get(hass).async_get(SWITCH)
        assert item.unique_id == f"{ADDRESS}_keep_connected"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_deliberate_disconnect_is_persisted_and_changes_nothing_on_the_desk(
    hass,
):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        before = len(motion_writes(fake))
        await switch(hass, "turn_off")
        coordinator = entry.runtime_data
        assert entry.data[CONF_KEEP_CONNECTED] is False
        assert not wants_connection(entry)
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(CONNECTION).state == "off"
        assert not fake.is_connected
        assert not coordinator.desk.connected
        # Nothing moved and no Stop was invented: there was nothing to stop.
        assert len(motion_writes(fake)) == before
        assert hass.states.get(OPERATION).state == "idle"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_cached_measurements_are_not_live_while_released(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        assert hass.states.get(HEIGHT).state != "unavailable"
        await switch(hass, "turn_off")
        assert hass.states.get(HEIGHT).state == "unavailable"
        assert hass.states.get("sensor.desk_stored_height_1").state == "unavailable"
        assert hass.states.get("button.desk_stop").state == "unavailable"
        # The owner's control and the actual link stay visible.
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(CONNECTION).state == "off"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_polling_and_refreshes_never_reconnect_a_released_desk(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        await switch(hass, "turn_off")
        lookups, connects = lookup.call_count, connect.call_count
        coordinator = entry.runtime_data
        polls = patch.object(
            coordinator,
            "_async_update_data",
            wraps=coordinator._async_update_data,
        )
        with polls as update:
            for _ in range(3):
                await coordinator.async_refresh()
            await tick(hass, 61)
            await tick(hass, 200)
            # The scheduled poll really ran, and still did nothing radio-related.
            assert update.call_count >= 4
        assert lookup.call_count == lookups
        assert connect.call_count == connects
        assert not coordinator.desk.connected
        assert hass.states.get(SWITCH).state == "off"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_an_explicit_reconnect_reads_fresh_data_and_replays_nothing(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        await switch(hass, "turn_off")
        written = len(fake.writes)
        connects = connect.call_count
        await switch(hass, "turn_on")
        assert connect.call_count == connects + 1
        assert hass.states.get(SWITCH).state == "on"
        assert hass.states.get(CONNECTION).state == "on"
        assert hass.states.get(HEIGHT).state != "unavailable"
        assert entry.data[CONF_KEEP_CONNECTED] is True
        later = fake.writes[written:]
        assert len(dpg_writes(fake)) > 0
        assert [w for w in later if w[0] in (CONTROL_UUID, TARGET_UUID)] == []
        assert any(uuid == DPG_UUID for uuid, _ in later)
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_released_start_restores_exactly_the_registered_slots(hass):
    fake = MotionBleak()
    entry = await add_entry(hass, **{CONF_KEEP_CONNECTED: False})
    registry = er.async_get(hass)
    for slot in (1, 4):
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{ADDRESS}_memory_{slot}",
            config_entry=entry,
            suggested_object_id=f"desk_stored_height_{slot}",
        )
        registry.async_get_or_create(
            "button",
            DOMAIN,
            f"{ADDRESS}_go_to_memory_{slot}",
            config_entry=entry,
            suggested_object_id=f"desk_go_to_stored_position_{slot}",
        )
    with radio(fake):
        await start(hass, entry)
        for slot in (1, 4):
            for entity_id in (
                f"sensor.desk_stored_height_{slot}",
                f"button.desk_go_to_stored_position_{slot}",
            ):
                state = hass.states.get(entity_id)
                assert state.state == "unavailable"
                assert "restored" not in state.attributes
        # The registered numbers are restored, not the first N slots.
        assert hass.states.get("sensor.desk_stored_height_2") is None
        assert hass.states.get("button.desk_go_to_stored_position_3") is None
        await switch(hass, "turn_on")
        for slot in (1, 2, 3, 4):
            assert hass.states.get(f"sensor.desk_stored_height_{slot}").state != (
                "unavailable"
            )
        assert len(hass.states.async_all("button")) == 6
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_persisted_release_survives_a_restart_without_touching_the_radio(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        await switch(hass, "turn_off")
        assert await hass.config_entries.async_unload(entry.entry_id)
        lookups, connects = lookup.call_count, connect.call_count
        await start(hass, entry)
        assert lookup.call_count == lookups
        assert connect.call_count == connects
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(CONNECTION).state == "off"
        # The entities the desk exposed before are real again, not restored stubs.
        assert len(hass.states.async_all("button")) == 6
        for entity_id in (
            "button.desk_go_to_stored_position_4",
            "sensor.desk_stored_height_4",
        ):
            state = hass.states.get(entity_id)
            assert state.state == "unavailable"
            assert "restored" not in state.attributes
        assert hass.states.get(HEIGHT).state == "unavailable"
        assert hass.states.get(OPERATION).state == "idle"
        coordinator = entry.runtime_data
        await coordinator.async_refresh()
        await tick(hass, 61)
        assert connect.call_count == connects
        await switch(hass, "turn_on")
        assert connect.call_count == connects + 1
        assert hass.states.get(HEIGHT).state != "unavailable"
        assert hass.states.get("sensor.desk_stored_height_4").state != "unavailable"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_first_start_in_the_released_state_adds_stored_positions_later(hass):
    fake = MotionBleak()
    entry = await add_entry(hass, **{CONF_KEEP_CONNECTED: False})
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        assert lookup.call_count == 0
        assert connect.call_count == 0
        assert hass.states.get(SWITCH).state == "off"
        assert len(hass.states.async_all("button")) == 2
        assert hass.states.get("sensor.desk_stored_height_1") is None
        await switch(hass, "turn_on")
        assert len(hass.states.async_all("button")) == 6
        assert hass.states.get("sensor.desk_stored_height_1").state != "unavailable"
        assert len(hass.states.async_all("sensor")) == 14
        await hass.config_entries.async_unload(entry.entry_id)


async def test_releasing_again_before_any_desk_exists_changes_nothing(hass):
    fake = MotionBleak()
    entry = await add_entry(hass, **{CONF_KEEP_CONNECTED: False})
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        coordinator = entry.runtime_data
        assert coordinator.desk is None
        await switch(hass, "turn_off")
        await switch(hass, "turn_off")
        assert coordinator.desk is None
        assert lookup.call_count == 0
        assert connect.call_count == 0
        assert hass.states.get(SWITCH).state == "off"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_wizard_session_is_released_when_the_owner_asked_for_none(hass):
    fake = MotionBleak()
    entry = await add_entry(hass, **{CONF_KEEP_CONNECTED: False})
    desk = DeskClient(DEVICE, lambda: None)
    with radio(fake):
        await desk.refresh()
        assert desk.connected
        offer_session(hass, desk)
        await start(hass, entry)
        assert entry.runtime_data.desk is desk
        assert desk.released
        assert not desk.connected
        assert not fake.is_connected
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_release_during_travel_stops_before_it_drops_the_link(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        coordinator = entry.runtime_data
        fake.stall = True
        with patch(FAST, HOLD):
            move = asyncio.create_task(coordinator.async_move_to_cm(83))
            await asyncio.wait_for(fake.target_written.wait(), 1)
            await switch(hass, "turn_off")
            await move
        assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
        assert not fake.is_connected
        assert hass.states.get(OPERATION).state == "interrupted"
        assert hass.states.get(SWITCH).state == "off"
        assert not coordinator.desk.control_busy
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failed_stop_during_release_is_reported_and_the_link_is_dropped(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        coordinator = entry.runtime_data
        fake.stall = True
        with patch(FAST, HOLD):
            move = asyncio.create_task(coordinator.async_move_to_cm(83))
            await asyncio.wait_for(fake.target_written.wait(), 1)
            fake.fail_stop = True
            with pytest.raises(HomeAssistantError) as error:
                await switch(hass, "turn_off")
            assert error.value.translation_key == "stop_failed"
            with pytest.raises(HomeAssistantError):
                await move
        assert entry.data[CONF_KEEP_CONNECTED] is False
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(CONNECTION).state == "off"
        assert not fake.is_connected
        state = hass.states.get(OPERATION)
        assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_released_client_refuses_to_connect_until_resumed():
    fake = MotionBleak()
    desk = DeskClient(DEVICE, lambda: None)
    with radio(fake) as (_, connect):
        await desk.release()
        assert desk.released
        with pytest.raises(ConnectionError):
            await desk.refresh()
        assert connect.call_count == 0
        desk.resume()
        await desk.refresh()
        assert connect.call_count == 1
        assert desk.connected
        await desk.disconnect()


async def test_a_release_while_the_connector_runs_is_not_undone_by_its_session():
    fake = MotionBleak()
    desk = DeskClient(DEVICE, lambda: None)
    gate, started = asyncio.Event(), asyncio.Event()

    async def slow_connect(*_args, **_kwargs):
        started.set()
        await gate.wait()
        return fake.reconnect()

    with radio(fake) as (_, connect):
        connect.side_effect = slow_connect
        refresh = asyncio.create_task(desk.refresh())
        await asyncio.wait_for(started.wait(), 1)
        await desk.release()
        gate.set()
        with pytest.raises(ConnectionError):
            await refresh
        assert not desk.connected
        assert not fake.is_connected
        assert fake.writes == []
        assert not fake.callbacks
        # A released desk is never paired or bonded by a session that lost the race.
        assert not fake.paired


async def test_a_failing_link_drop_still_hides_the_cached_readings(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        coordinator = entry.runtime_data

        async def broken_drop():
            raise TimeoutError

        with patch.object(coordinator.desk, "_disconnect_link", broken_drop):
            with pytest.raises(TimeoutError):
                await switch(hass, "turn_off")
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(HEIGHT).state == "unavailable"
        assert entry.data[CONF_KEEP_CONNECTED] is False
        await hass.config_entries.async_unload(entry.entry_id)


async def test_the_first_connection_after_a_released_start_reads_everything(hass):
    fake = MotionBleak()
    entry = await add_entry(hass, **{CONF_KEEP_CONNECTED: False})
    original = DeskClient.refresh
    seen = []

    async def spy(self, **kwargs):
        seen.append(kwargs["allow_partial_settings"])
        return await original(self, **kwargs)

    with radio(fake), patch.object(DeskClient, "refresh", spy):
        await start(hass, entry)
        await switch(hass, "turn_on")
        await entry.runtime_data.async_refresh()
        # Optional settings must not block even the first connection.
        assert seen == [True, True]
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_turn_off_during_a_turn_on_refresh_wins_and_discards_it(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    gate, started = asyncio.Event(), asyncio.Event()

    async def slow_connect(*_args, **_kwargs):
        started.set()
        await gate.wait()
        return fake.reconnect()

    with radio(fake) as (_, connect):
        await start(hass, entry)
        coordinator = entry.runtime_data
        await switch(hass, "turn_off")
        connect.side_effect = slow_connect
        turn_on = asyncio.create_task(coordinator.async_set_connection_wanted(True))
        await asyncio.wait_for(started.wait(), 1)
        turn_off = asyncio.create_task(coordinator.async_set_connection_wanted(False))
        await asyncio.sleep(0)
        # The newest intent is saved at once, while the older call still runs.
        assert entry.data[CONF_KEEP_CONNECTED] is False
        gate.set()
        await turn_on
        await turn_off
        await hass.async_block_till_done()
        assert not coordinator.desk.connected
        assert not fake.is_connected
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(HEIGHT).state == "unavailable"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_refresh_racing_a_release_cannot_revive_the_session(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    gate, started = asyncio.Event(), asyncio.Event()

    async def slow_connect(*_args, **_kwargs):
        started.set()
        await gate.wait()
        return fake.reconnect()

    with radio(fake) as (_, connect):
        await start(hass, entry)
        coordinator = entry.runtime_data
        await coordinator.desk._disconnect_link()
        connect.side_effect = slow_connect
        refresh = asyncio.create_task(coordinator.async_refresh())
        await asyncio.wait_for(started.wait(), 1)
        await switch(hass, "turn_off")
        gate.set()
        await refresh
        await hass.async_block_till_done()
        assert not coordinator.desk.connected
        assert not fake.is_connected
        assert not coordinator.last_update_success
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(CONNECTION).state == "off"
        assert hass.states.get(HEIGHT).state == "unavailable"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_release_between_a_finished_read_and_its_publication_wins(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        coordinator = entry.runtime_data
        original = coordinator.desk.refresh

        async def release_after_read(**kwargs):
            state = await original(**kwargs)
            # The persisted intent flips after the read, before it is published.
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_KEEP_CONNECTED: False}
            )
            return state

        coordinator.desk.refresh = release_after_read
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert not coordinator.desk.connected
        assert coordinator.desk.released
        assert not coordinator.last_update_success
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failing_release_after_a_raced_refresh_is_still_reported_as_released(
    hass,
):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        coordinator = entry.runtime_data
        original = coordinator.desk.refresh

        async def flip_then_fail(**kwargs):
            state = await original(**kwargs)
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_KEEP_CONNECTED: False}
            )
            return state

        async def broken_release():
            raise TimeoutError

        coordinator.desk.refresh = flip_then_fail
        coordinator.desk.release = broken_release
        await coordinator.async_refresh()
        assert not coordinator.last_update_success
        assert "connection_released" in str(coordinator.last_exception.translation_key)
        await hass.config_entries.async_unload(entry.entry_id)


async def test_repeated_and_overlapping_callers_end_in_one_consistent_state(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        coordinator = entry.runtime_data
        await asyncio.gather(
            coordinator.async_set_connection_wanted(False),
            coordinator.async_set_connection_wanted(False),
            coordinator.async_set_connection_wanted(False),
        )
        assert not coordinator.desk.connected
        assert not wants_connection(entry)
        connects = connect.call_count
        await asyncio.gather(
            coordinator.async_set_connection_wanted(True),
            coordinator.async_set_connection_wanted(True),
        )
        assert coordinator.desk.connected
        assert wants_connection(entry)
        assert connect.call_count == connects + 1
        connects = connect.call_count
        gate = asyncio.Event()
        original = coordinator.desk.release
        calls = []

        async def held_release():
            calls.append(True)
            if len(calls) == 1:
                await gate.wait()
            await original()

        coordinator.desk.release = held_release
        first = asyncio.create_task(coordinator.async_set_connection_wanted(False))
        await asyncio.sleep(0)
        later = [
            asyncio.create_task(coordinator.async_set_connection_wanted(True)),
            asyncio.create_task(coordinator.async_set_connection_wanted(False)),
        ]
        await asyncio.sleep(0)
        gate.set()
        await asyncio.gather(first, *later)
        # The turn-on was superseded by the later turn-off, so it never connected.
        assert connect.call_count == connects
        assert not coordinator.desk.connected
        assert not wants_connection(entry)
        assert hass.states.get(SWITCH).state == "off"
        assert hass.states.get(CONNECTION).state == "off"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failed_reconnect_keeps_the_intent_and_a_later_poll_recovers(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        await switch(hass, "turn_off")
        connect.side_effect = BleakError("private backend details")
        with pytest.raises(HomeAssistantError) as error:
            await switch(hass, "turn_on")
        assert error.value.translation_key == "connection_failed"
        assert "private" not in str(error.value)
        assert entry.data[CONF_KEEP_CONNECTED] is True
        assert hass.states.get(SWITCH).state == "on"
        assert hass.states.get(CONNECTION).state == "off"
        assert hass.states.get(HEIGHT).state == "unavailable"
        connect.side_effect = fake.reconnect
        await tick(hass, 61)
        assert hass.states.get(CONNECTION).state == "on"
        assert hass.states.get(HEIGHT).state != "unavailable"
        assert motion_writes(fake) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_turning_on_an_unreachable_desk_is_reported_without_a_radio_lookup_loop(
    hass,
):
    fake = MotionBleak()
    entry = await add_entry(hass, **{CONF_KEEP_CONNECTED: False})
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        lookup.return_value = None
        with pytest.raises(HomeAssistantError) as error:
            await switch(hass, "turn_on")
        assert error.value.translation_key == "connection_failed"
        assert connect.call_count == 0
        assert hass.states.get(SWITCH).state == "on"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_while_released_leaves_nothing_pending(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        await switch(hass, "turn_off")
        connects = connect.call_count
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        await tick(hass, 300)
        assert connect.call_count == connects


async def test_diagnostics_report_the_intent_apart_from_the_link(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake):
        await start(hass, entry)
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["connection_wanted"] is True
        assert result["connected"] is True
        await switch(hass, "turn_off")
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["connection_wanted"] is False
        assert result["connected"] is False
        await hass.config_entries.async_unload(entry.entry_id)
