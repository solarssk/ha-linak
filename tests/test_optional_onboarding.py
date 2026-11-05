"""Optional settings cannot prevent onboarding or compromise reply ownership."""

import asyncio
from itertools import product
from unittest.mock import patch

import pytest

from custom_components.ha_linak.client import (
    DeskLinkLost,
    QUERY_TIMEOUT,
    REFRESH_TIMEOUT,
)
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID
from replay_transport import (
    Position,
    ReplayBleak,
    connections,
    default_replies,
    expect_failure,
    memory_frame,
    new_desk,
    sent_commands,
)


@pytest.mark.parametrize("populated", list(product((False, True), repeat=4)))
async def test_every_empty_slot_combination_keeps_numbering(populated):
    fake = ReplayBleak(
        default_replies(
            tuple(
                memory_frame(1000 + index if present else None, index)
                for index, present in enumerate(populated)
            )
        )
    )
    desk = new_desk()
    with connections(fake):
        state = await desk.refresh(allow_partial_settings=True)
    assert [m.position_raw for m in state.memories] == [
        1000 + index if present else None for index, present in enumerate(populated)
    ]
    assert desk.settings_health["memories"].valid
    await desk.disconnect()


@pytest.mark.parametrize(
    "position",
    [
        Position.SLOT1,
        Position.SLOT2,
        Position.SLOT3,
        Position.SLOT4,
        Position.REMINDERS,
    ],
)
@pytest.mark.parametrize("runtime", [False, True])
async def test_timeout_recovers_height_on_new_session_and_retries_later(
    position, runtime
):
    first, recovered = ReplayBleak(), ReplayBleak()
    desk = new_desk()
    group = "reminders" if position == Position.REMINDERS else "memories"
    with connections(first, recovered):
        if runtime:
            await desk.refresh()
        first.script(failures={position: "silent"})
        with patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01):
            state = await desk.refresh(allow_partial_settings=True)
        assert first.disconnected.is_set()
        assert desk.connected
        assert state.height_cm == 82.38
        assert not desk.settings_health[group].valid
        assert desk.settings_health[group].error == "timeout"
        assert desk.settings_health[
            "memories" if group == "reminders" else "reminders"
        ].valid
        excluded = {0x88} if group == "reminders" else set(range(0x89, 0x8D))
        assert not excluded.intersection(sent_commands(recovered))
        # All old callbacks are inert after recovery, even during another query.
        previous = state.position
        first.callbacks[HEIGHT_UUID](None, bytearray(b"\x00" * 4))
        assert state.position == previous
        recovered.writes.clear()
        recovered.script()
        await desk.refresh(allow_partial_settings=True)
        assert not excluded.intersection(sent_commands(recovered))
        retry_at = desk.settings_health[group].retry_after
        recovered.script()
        with patch(
            "custom_components.ha_linak.client.monotonic", return_value=retry_at + 1
        ):
            await desk.refresh(allow_partial_settings=True)
        assert desk.settings_health[group].valid
        assert excluded.intersection(sent_commands(recovered))
        assert desk.settings_health[group].error is None
    await desk.disconnect()


async def test_both_optional_groups_can_timeout_with_only_two_recoveries():
    first, second, third = ReplayBleak(), ReplayBleak(), ReplayBleak()
    first.script(failures={Position.SLOT3: "silent"})
    # With memories excluded: capabilities, offset, reminders.
    second.script(failures={2: "silent"})
    desk = new_desk()
    with (
        connections(first, second, third),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
    ):
        state = await desk.refresh(allow_partial_settings=True)
    assert desk.connected
    assert state.height_cm == 82.38
    assert sent_commands(third) == [0x80, 0x81]
    assert all(
        not health.valid and health.error == "timeout"
        for health in desk.settings_health.values()
    )
    await desk.disconnect()


@pytest.mark.parametrize("failure", ["silent", "link_loss"])
@pytest.mark.parametrize(
    "position",
    [Position.CAPABILITIES, Position.OFFSET, Position.BARRIER1, Position.POSITION_READ],
)
async def test_required_failure_is_never_degraded(position, failure):
    fake = ReplayBleak()
    fake.script(failures={position: failure})
    desk = new_desk()
    with (
        connections(fake),
        patch.multiple(
            "custom_components.ha_linak.client", QUERY_TIMEOUT=0.01, IO_TIMEOUT=0.01
        ),
    ):
        with pytest.raises(TimeoutError if failure == "silent" else DeskLinkLost):
            await desk.refresh(allow_partial_settings=True)
    assert not desk.connected
    assert desk.state.offset_raw is None


async def test_failed_recovery_does_not_publish_partial_state():
    fake, recovery = ReplayBleak(), ReplayBleak()
    fake.script(failures={Position.SLOT3: "silent"})
    recovery.script(failures={Position.OFFSET: "link_loss"})
    desk = new_desk()
    with (
        connections(fake, recovery),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
    ):
        with pytest.raises(DeskLinkLost):
            await desk.refresh(allow_partial_settings=True)
    assert not desk.connected
    assert desk.state.offset_raw is None


async def test_old_dpg_cannot_complete_recovery_query():
    fake, recovery = ReplayBleak(), ReplayBleak()
    fake.script(failures={Position.SLOT3: "silent"})
    recovery.script(failures={Position.CAPABILITIES: "silent"})
    desk = new_desk()
    with (
        connections(fake, recovery),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.1),
    ):
        task = asyncio.create_task(desk.refresh(allow_partial_settings=True))
        try:
            await asyncio.wait_for(recovery.stalled.wait(), 1)
            pending = desk._pending
            fake.callbacks[DPG_UUID](None, bytearray(recovery.replies[0x80]))
            assert pending is not None
            assert not pending.done()
            recovery.release()
            await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize("command", [0x89, 0x8A, 0x8B, 0x8C, 0x88])
async def test_real_ha_startup_creates_unavailable_settings_and_live_height(
    hass, command
):
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.exceptions import HomeAssistantError
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.ha_linak.const import DOMAIN
    from test_integration import DEVICE, ADDRESS
    from test_native_controls import OPTIONS
    from test_settings_freshness import GroupReplies

    fake = GroupReplies()
    fake.silent = command
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Desk",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS},
        options=OPTIONS,
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    desk = entry.runtime_data.desk
    assert desk.connected
    assert entry.runtime_data.last_update_success
    assert hass.states.get("sensor.desk_height").state == "82"
    assert (
        len(
            [
                s
                for s in hass.states.async_all("sensor")
                if "stored_height" in s.entity_id
            ]
        )
        == 4
    )
    assert len(hass.states.async_all("button")) == 6
    if command != 0x88:
        assert all(
            s.state == "unavailable"
            for s in hass.states.async_all("button")
            if "stored_position" in s.entity_id
        )
        before = len(fake.writes)
        with pytest.raises(HomeAssistantError):
            await entry.runtime_data.async_move_to_memory(0)
        assert len(fake.writes) == before
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_wizard_and_calibration_finish_with_silent_empty_slots(hass):
    from test_calibration import CalibrationBleak, DEVICE, initial_form, writes
    from test_guided_setup import complete_progress

    class SilentMemories(CalibrationBleak):
        async def write_gatt_char(self, uuid, data, response):
            if data[2] == 0 and data[1] in (0x8B, 0x8C):
                self.writes.append((uuid, bytes(data)))
                return
            await super().write_gatt_char(uuid, data, response)

    fake = SilentMemories()
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
    ):
        result = await initial_form(hass, fake, guide=False)
        assert result["step_id"] == "name"
        assert result["description_placeholders"]["height"] == "82"
        assert all(
            result["description_placeholders"][f"memory_{index}"] == "?"
            for index in range(1, 5)
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Office"}
        )
        result = await complete_progress(hass, result)
        assert result["step_id"] == "finish"
        assert result["description_placeholders"]["memory_1"] == "?"
        # Preparation performs the existing explicit activation, never motion.
        assert len(writes(fake)) <= 1
        assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
        hass.config_entries.flow.async_abort(result["flow_id"])
        await hass.async_block_till_done()


async def test_reference_calibration_verification_does_not_query_unavailable_settings():
    from test_calibration import ready, writes
    from custom_components.ha_linak.calibration import HeightCalibration

    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 83.0
    )
    fake.writes.clear()
    state = await desk.calibrate_height(proposal)
    assert state.height_cm == 83.0
    assert len(writes(fake)) == 1
    assert not any(
        data[2] == 0 and data[1] in (0x88, 0x89, 0x8A, 0x8B, 0x8C)
        for _, data in fake.writes
    )
    assert all(not health.valid for health in desk.settings_health.values())
    await desk.disconnect()


async def test_cooldown_survives_disconnect_and_reconnect():
    first, recovery, restart = ReplayBleak(), ReplayBleak(), ReplayBleak()
    first.script(failures={Position.SLOT3: "silent"})
    desk = new_desk()
    with (
        connections(first, recovery, restart),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
    ):
        await desk.refresh(allow_partial_settings=True)
        await desk.disconnect()
        await desk.refresh(allow_partial_settings=True)
    assert desk.connected
    assert sent_commands(restart) == [0x80, 0x81, 0x88]
    assert not desk.settings_health["memories"].valid
    await desk.disconnect()


async def test_cancelling_recovery_closes_the_new_session():
    first, recovery = ReplayBleak(), ReplayBleak()
    first.script(failures={Position.SLOT3: "silent"})
    recovery.script(failures={Position.CAPABILITIES: "silent"})
    desk = new_desk()
    with (
        connections(first, recovery),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.1),
    ):
        task = asyncio.create_task(desk.refresh(allow_partial_settings=True))
        await asyncio.wait_for(recovery.stalled.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert first.disconnected.is_set()
    assert recovery.disconnected.is_set()
    assert not desk.connected
    assert desk.state.offset_raw is None


async def test_recovery_shares_the_original_refresh_deadline():
    first, recovery = ReplayBleak(), ReplayBleak()
    first.script(failures={Position.SLOT3: "silent"})
    recovery.script(failures={Position.CAPABILITIES: "silent"})
    desk = new_desk()
    real_timeout = asyncio.timeout
    refresh_timeouts: list[asyncio.Timeout] = []
    query_timeouts: list[asyncio.Timeout] = []

    def controlled_timeout(budget):
        # Expire real timeout contexts at protocol events, not wall-clock races.
        if budget in (REFRESH_TIMEOUT, QUERY_TIMEOUT):
            context = real_timeout(None)
            contexts = refresh_timeouts if budget == REFRESH_TIMEOUT else query_timeouts
            contexts.append(context)
            return context
        return real_timeout(budget)

    with (
        connections(first, recovery),
        patch(
            "custom_components.ha_linak.client.asyncio.timeout",
            side_effect=controlled_timeout,
        ),
    ):
        task = asyncio.create_task(desk.refresh(allow_partial_settings=True))
        try:
            await asyncio.wait_for(first.stalled.wait(), 2)
            original_query = query_timeouts[-1]
            original_query.reschedule(asyncio.get_running_loop().time())
            await asyncio.wait_for(recovery.stalled.wait(), 2)
            assert original_query.expired()
            assert first.disconnected.is_set()
            assert len(refresh_timeouts) == 1
            original_refresh = refresh_timeouts[0]
            assert not original_refresh.expired()
            original_refresh.reschedule(asyncio.get_running_loop().time())
            await expect_failure(task, TimeoutError)
            assert original_refresh.expired()
            assert not query_timeouts[-1].expired()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert recovery.stalled.is_set()
    assert recovery.disconnected.is_set()
    assert not desk.connected
    assert desk.state.offset_raw is None


async def test_unchanged_calibration_keeps_already_valid_memories():
    from test_calibration import ready, writes
    from custom_components.ha_linak.calibration import HeightCalibration

    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, desk.state.height_cm
    )
    fake.writes.clear()
    await desk.calibrate_height(proposal)
    assert not writes(fake)
    assert all(health.valid for health in desk.settings_health.values())
    await desk.disconnect()
