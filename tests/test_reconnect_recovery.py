"""Recovery through real HA lifecycle with synthetic radio and no panel writes."""

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState, SOURCE_BLUETOOTH
from homeassistant.core import CoreState
from homeassistant.exceptions import HomeAssistantError

from test_connection_ownership import (
    CONNECTION,
    HEIGHT,
    add_entry,
    motion_writes,
    radio,
    start,
    tick,
)
from test_native_controls import ADDRESS, DEVICE, MotionBleak

from custom_components.ha_linak.const import DOMAIN


async def test_live_link_survives_missing_discovery_metadata(hass):
    """A quiet connected peripheral must not need to advertise to stay connected."""
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        lookup.reset_mock()
        lookup.return_value = None
        await entry.runtime_data.async_refresh()
        assert entry.runtime_data.last_update_success
        assert fake.is_connected
        assert hass.states.get(HEIGHT).state == "82"
        assert entry.runtime_data.data.height_cm == 82.38
        lookup.assert_not_called()
        assert connect.call_count == 1
        assert motion_writes(fake) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_link_loss_requests_recovery_without_waiting_for_poll(hass):
    """An established entry restores reads after a drop without a clock advance."""
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        desk = entry.runtime_data.desk
        replacement = MotionBleak()
        connect.side_effect = replacement.reconnect
        fake.is_connected = False
        desk._disconnected(fake)
        desk._disconnected(fake)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert connect.call_count == 2
        assert desk.connected
        assert desk.client is replacement
        assert hass.states.get(CONNECTION).state == "on"
        assert motion_writes(fake) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_release_cancels_a_queued_recovery(hass):
    """An owner's release wins even before the reconnect coroutine begins."""
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        coordinator = entry.runtime_data
        fake.is_connected = False
        coordinator.desk._disconnected(fake)
        await coordinator.async_set_connection_wanted(False)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert connect.call_count == 1
        assert not coordinator.desk.connected
        assert motion_writes(fake) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_cancels_a_queued_recovery(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        coordinator = entry.runtime_data
        fake.is_connected = False
        coordinator.desk._disconnected(fake)
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert connect.call_count == 1
        assert not fake.is_connected


async def test_shutdown_suppresses_a_queued_recovery(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        fake.is_connected = False
        entry.runtime_data.desk._disconnected(fake)
        hass.set_state(CoreState.stopping)
        try:
            await hass.async_block_till_done(wait_background_tasks=True)
            assert connect.call_count == 1
            assert not fake.is_connected
        finally:
            hass.set_state(CoreState.running)
            await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_drains_an_in_progress_reconnect(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked_connect(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with radio(fake) as (_, connect):
        await start(hass, entry)
        connect.side_effect = blocked_connect
        coordinator = entry.runtime_data
        fake.is_connected = False
        coordinator.desk._disconnected(fake)
        await asyncio.wait_for(entered.wait(), 1)
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert cancelled.is_set()
        assert coordinator._recovery_task is None
        assert connect.call_count == 2
        assert not fake.is_connected


async def test_separate_outages_each_get_one_recovery(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        for attempt in range(2):
            old = entry.runtime_data.desk.client
            replacement = MotionBleak()
            connect.side_effect = replacement.reconnect
            old.is_connected = False
            entry.runtime_data.desk._disconnected(old)
            await hass.async_block_till_done(wait_background_tasks=True)
            # A second request can be debounced by HA after the first refresh.
            if not entry.runtime_data.desk.connected:
                await tick(hass, 11)
            assert entry.runtime_data.desk.client is replacement
            assert entry.runtime_data.desk.connected
            assert connect.call_count == attempt + 2
            assert motion_writes(replacement) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_recovery_does_not_start_a_retry_loop(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        connect.side_effect = ConnectionError("synthetic unavailable desk")
        fake.is_connected = False
        entry.runtime_data.desk._disconnected(fake)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert connect.call_count == 2
        assert not entry.runtime_data.last_update_success
        assert hass.states.get(CONNECTION).state == "off"
        assert motion_writes(fake) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_missing_device_recovers_on_later_poll_without_replaying_controls(hass):
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (lookup, connect):
        await start(hass, entry)
        lookup.return_value = None
        fake.is_connected = False
        entry.runtime_data.desk._disconnected(fake)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert connect.call_count == 1
        assert hass.states.get(HEIGHT).state == "unavailable"
        replacement = MotionBleak()
        connect.side_effect = replacement.reconnect
        lookup.return_value = DEVICE
        await tick(hass)
        assert entry.runtime_data.desk.connected
        assert connect.call_count == 2
        assert motion_writes(replacement) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_discovery_accelerates_failed_startup_through_ha(hass):
    """HA already retries a configured entry when Bluetooth discovers it again."""
    fake = MotionBleak()
    entry = await add_entry(hass)
    with radio(fake) as (lookup, connect):
        lookup.return_value = None
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        lookup.return_value = DEVICE
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=SimpleNamespace(address=ADDRESS),
        )
        assert result["reason"] == "already_configured"
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.state is ConfigEntryState.LOADED
        assert connect.call_count == 1
        assert motion_writes(fake) == []
        await hass.config_entries.async_unload(entry.entry_id)


async def test_recovery_waits_for_motion_cleanup_and_never_resumes_target(hass):
    fake = MotionBleak()
    fake.stall = True
    entry = await add_entry(hass)
    with radio(fake) as (_, connect):
        await start(hass, entry)
        replacement = MotionBleak()
        connect.side_effect = replacement.reconnect
        coordinator = entry.runtime_data
        moving = asyncio.create_task(coordinator.async_move_to_cm(83))
        await fake.target_written.wait()
        fake.is_connected = False
        coordinator.desk._disconnected(fake)
        with pytest.raises(HomeAssistantError):
            await moving
        await hass.async_block_till_done(wait_background_tasks=True)
        assert coordinator.desk.connected
        assert coordinator.desk.client is replacement
        assert connect.call_count == 2
        assert motion_writes(replacement) == []
        await hass.config_entries.async_unload(entry.entry_id)
