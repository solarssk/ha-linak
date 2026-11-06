"""Operation status: transitions, entity contract and failure reasons, simulated."""

import asyncio
import json
from pathlib import Path
import struct
from unittest.mock import patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, EVENT_STATE_CHANGED
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ha_linak.client import DeskClient, DeskLinkLost
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_linak.motion import (
    CONTROL_UUID,
    REFERENCE_STOP,
    STOP,
    TARGET_UUID,
    MotionError,
    MotionFailure,
    MotionStopped,
)
from custom_components.ha_linak.operation import (
    OperationStatus,
    OperationTracker,
    Phase,
    Reason,
)
from test_native_controls import (
    ADDRESS,
    DEVICE,
    OPTIONS,
    MotionBleak,
    connected_desk,
    setup_entry,
)

COMPONENT = Path(__file__).parents[1] / "custom_components/ha_linak"
OPERATION_ID = "sensor.desk_operation"
FAST = "custom_components.ha_linak.motion.COMMAND_INTERVAL"
HOLD = 60


def tracker():
    changes = []
    return OperationTracker(lambda: changes.append(True)), changes


def reach(phase):
    status, changes = tracker()
    if phase is not Phase.IDLE:
        status.begin(83)
    if phase in (Phase.MOVING, Phase.STOPPING):
        status.moving()
    if phase is Phase.STOPPING:
        status.stopping()
    if phase is Phase.COMPLETED:
        status.complete()
    if phase is Phase.INTERRUPTED:
        status.interrupt()
    if phase is Phase.FAILED:
        status.fail(Reason.TIMEOUT)
    return status, changes


def test_a_complete_operation_publishes_each_phase_once():
    status, changes = tracker()
    status.begin(83)
    status.moving()
    status.stopping()
    status.stopping()
    status.complete()
    status.complete()
    assert status.status == OperationStatus(Phase.COMPLETED, 83)
    assert len(changes) == 4


@pytest.mark.parametrize("phase", list(Phase), ids=lambda phase: phase.value)
def test_a_new_operation_starts_only_when_none_is_active(phase):
    status, _ = reach(phase)
    before = status.status
    status.begin(90)
    if before.active:
        assert status.status == before
    else:
        assert status.status == OperationStatus(Phase.PREPARING, 90)


@pytest.mark.parametrize(
    "phase,action,expected",
    [
        (Phase.IDLE, "moving", Phase.IDLE),
        (Phase.PREPARING, "moving", Phase.MOVING),
        (Phase.MOVING, "moving", Phase.MOVING),
        (Phase.COMPLETED, "moving", Phase.COMPLETED),
        (Phase.IDLE, "stopping", Phase.IDLE),
        (Phase.PREPARING, "stopping", Phase.STOPPING),
        (Phase.MOVING, "stopping", Phase.STOPPING),
        (Phase.STOPPING, "stopping", Phase.STOPPING),
        (Phase.FAILED, "stopping", Phase.FAILED),
    ],
)
def test_phases_advance_only_in_order(phase, action, expected):
    status, _ = reach(phase)
    getattr(status, action)()
    assert status.status.phase is expected


SETTLED_AS = {
    "complete": Phase.COMPLETED,
    "interrupt": Phase.INTERRUPTED,
    "link_lost": Phase.FAILED,
}


@pytest.mark.parametrize("phase", list(Phase), ids=lambda phase: phase.value)
@pytest.mark.parametrize("action", list(SETTLED_AS))
def test_only_an_active_operation_settles(phase, action):
    status, _ = reach(phase)
    before = status.status
    getattr(status, action)()
    if before.active:
        assert status.status.phase is SETTLED_AS[action]
    else:
        assert status.status == before


def test_a_settled_result_is_never_rewritten_by_late_callers():
    status, changes = tracker()
    status.begin(83)
    status.moving()
    status.link_lost()
    settled = status.status
    published = len(changes)
    for late in (
        status.stopping,
        status.complete,
        status.interrupt,
        status.link_lost,
        lambda: status.fail(Reason.STOP_FAILED),
        lambda: status.request(70),
    ):
        late()
    assert status.status == settled
    assert settled == OperationStatus(Phase.FAILED, 83, Reason.LINK_LOST)
    assert len(changes) == published


def test_a_failed_stop_while_idle_is_recorded_without_a_goal():
    status, _ = reach(Phase.COMPLETED)
    status.stop_failed_while_idle()
    assert status.status == OperationStatus(Phase.FAILED, None, Reason.STOP_FAILED)
    active, _ = reach(Phase.MOVING)
    active.stop_failed_while_idle()
    assert active.status.phase is Phase.MOVING


def test_a_failing_listener_cannot_change_the_outcome():
    def broken():
        raise RuntimeError("listener failure")

    status = OperationTracker(broken)
    status.begin(83)
    status.moving()
    status.stopping()
    status.complete()
    assert status.status == OperationStatus(Phase.COMPLETED, 83)


async def faulty_listener_desk():
    desk, fake = await connected_desk()

    def failing():
        raise RuntimeError("listener failure")

    desk.operation._changed = failing
    return desk, fake, ControlSettings.from_options(OPTIONS)


async def test_a_failing_listener_cannot_wedge_a_move():
    desk, _, settings = await faulty_listener_desk()
    await desk.move_to_cm(83, settings)
    assert not desk.control_busy
    assert desk.last_control_result == "completed"
    assert desk.operation.status.phase is Phase.COMPLETED
    await desk.disconnect()


async def test_a_failing_listener_cannot_skip_stop():
    desk, fake, settings = await faulty_listener_desk()
    fake.stall = True
    with patch(FAST, HOLD):
        move = asyncio.create_task(desk.move_to_cm(83, settings))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        await desk.stop()
        with pytest.raises(MotionError):
            await move
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert not desk.control_busy
    assert desk.operation.status.phase is Phase.INTERRUPTED
    await desk.disconnect()


async def test_a_failing_listener_cannot_keep_a_failed_lone_stop_connected():
    desk, fake, _ = await faulty_listener_desk()
    fake.fail_stop = True
    with pytest.raises(MotionError):
        await desk.stop()
    assert not desk.connected
    assert desk.operation.status == OperationStatus(
        Phase.FAILED, None, Reason.STOP_FAILED
    )


async def test_a_stop_in_the_gap_before_a_request_settles_cannot_rewrite_its_result():
    desk, fake = await connected_desk()
    finished = asyncio.create_task(asyncio.sleep(0))
    await finished
    desk._motion_task = finished
    desk.operation.begin(83)
    desk.operation.moving()
    desk.operation.link_lost()
    fake.fail_stop = True
    with pytest.raises(MotionError):
        await desk.stop()
    desk._motion_task = None
    assert desk.operation.status == OperationStatus(Phase.FAILED, 83, Reason.LINK_LOST)
    await desk.disconnect()


def test_a_goal_is_recorded_only_for_an_active_operation():
    idle, _ = reach(Phase.IDLE)
    idle.request(80.04)
    assert idle.status == OperationStatus()
    status, changes = reach(Phase.PREPARING)
    published = len(changes)
    status.request(80.04)
    status.request(80.04)
    assert status.status.requested_height_cm == 80.04
    assert len(changes) == published + 1


@pytest.mark.parametrize(
    "steps,origin",
    [
        (("begin",), Phase.PREPARING),
        (("begin", "moving"), Phase.MOVING),
        (("begin", "stopping"), Phase.PREPARING),
        (("begin", "moving", "stopping"), Phase.MOVING),
        (("begin", "moving", "stopping", "stopping"), Phase.MOVING),
        (("begin", "moving", "stopping", "complete"), Phase.COMPLETED),
    ],
)
def test_the_origin_survives_the_announcement_of_the_final_stop(steps, origin):
    status, _ = tracker()
    for step in steps:
        getattr(status, step)()
    assert status.origin is origin


STEPS = {
    "preparing": ("begin",),
    "moving": ("begin", "moving"),
    "stopping_from_preparing": ("begin", "stopping"),
    "stopping_from_moving": ("begin", "moving", "stopping"),
}


def desk_at(steps, stop_requested=False, stop_sent=False):
    desk = DeskClient(DEVICE, lambda: None)
    for step in STEPS[steps]:
        getattr(desk.operation, step)()
    if stop_requested:
        desk._stop_requested = True
    desk._motion_stop_sent = stop_sent
    return desk


@pytest.mark.parametrize(
    "steps,error,reason",
    [
        ("moving", DeskLinkLost(), Reason.LINK_LOST),
        ("moving", TimeoutError(), Reason.TIMEOUT),
        ("moving", MotionError("x", MotionFailure.STALLED), Reason.NO_PROGRESS),
        ("moving", MotionError("x", MotionFailure.REVERSE), Reason.REVERSE_MOTION),
        ("moving", MotionError("x", MotionFailure.OVERSHOOT), Reason.OVERSHOOT),
        (
            "moving",
            MotionError("x", MotionFailure.OUTSIDE_LIMITS),
            Reason.OUTSIDE_LIMITS,
        ),
        (
            "stopping_from_moving",
            MotionError("x", MotionFailure.STOP_FAILED),
            Reason.STOP_FAILED,
        ),
        ("preparing", MotionError("x"), Reason.PREPARATION_FAILED),
        ("preparing", ValueError("private detail"), Reason.PREPARATION_FAILED),
        ("moving", MotionError("x"), Reason.UNKNOWN),
        ("moving", MotionError("x", MotionFailure.BUSY), Reason.UNKNOWN),
        ("moving", RuntimeError("private detail"), Reason.UNKNOWN),
        # Cleanup announces stopping on every exit; the failure keeps its origin.
        ("stopping_from_moving", BleakError("private detail"), Reason.UNKNOWN),
        ("stopping_from_moving", ValueError("private detail"), Reason.UNKNOWN),
        ("stopping_from_moving", MotionError("x"), Reason.UNKNOWN),
        (
            "stopping_from_moving",
            MotionError("x", MotionFailure.OVERSHOOT),
            Reason.OVERSHOOT,
        ),
        ("stopping_from_preparing", ValueError("x"), Reason.PREPARATION_FAILED),
    ],
)
def test_failure_reasons_name_what_was_detected(steps, error, reason):
    assert desk_at(steps)._failure_reason(error) is reason


@pytest.mark.parametrize(
    "steps,stop_sent,error,reason",
    [
        ("stopping_from_preparing", False, BleakError("x"), Reason.STOP_FAILED),
        ("stopping_from_preparing", False, TimeoutError(), Reason.STOP_FAILED),
        ("stopping_from_moving", False, MotionError("x"), Reason.STOP_FAILED),
        (
            "stopping_from_moving",
            False,
            MotionError("x", MotionFailure.OVERSHOOT),
            Reason.STOP_FAILED,
        ),
        ("stopping_from_moving", False, DeskLinkLost(), Reason.LINK_LOST),
        (
            "stopping_from_moving",
            True,
            MotionError("x", MotionFailure.OVERSHOOT),
            Reason.OVERSHOOT,
        ),
        ("stopping_from_moving", True, MotionError("x"), Reason.UNKNOWN),
    ],
)
def test_an_unconfirmed_explicit_stop_is_a_stop_failure(
    steps, stop_sent, error, reason
):
    desk = desk_at(steps, stop_requested=True, stop_sent=stop_sent)
    assert desk._failure_reason(error) is reason


@pytest.mark.parametrize(
    "name", ["strings.json", "translations/en.json", "translations/pl.json"]
)
def test_every_phase_reason_and_attribute_is_translated(name):
    entity = json.loads((COMPONENT / name).read_text())["entity"]["sensor"]["operation"]
    assert entity["name"]
    assert set(entity["state"]) == {phase.value for phase in Phase}
    attributes = entity["state_attributes"]
    assert attributes["requested_height_cm"]["name"]
    assert attributes["reason"]["name"]
    assert set(attributes["reason"]["state"]) == {reason.value for reason in Reason}


class Journal:
    """Every published state of the operation entity, in order."""

    def __init__(self, hass):
        self.entries = []
        hass.bus.async_listen(EVENT_STATE_CHANGED, self._record)

    @callback
    def _record(self, event):
        state = event.data["new_state"]
        if event.data["entity_id"] == OPERATION_ID and state is not None:
            self.entries.append((state.state, dict(state.attributes)))

    @property
    def phases(self):
        return [phase for phase, _ in self.entries]


class SteppedBleak(MotionBleak):
    """Moves a little per target write, so travel produces many position changes."""

    async def write_gatt_char(self, uuid, data, response):
        if uuid == TARGET_UUID and data != REFERENCE_STOP:
            self.writes.append((uuid, bytes(data)))
            self.target_written.set()
            target = struct.unpack("<H", data)[0]
            self.position += max(-100, min(100, target - self.position))
            return
        await super().write_gatt_char(uuid, data, response)


async def setup(hass, fake=None):
    if fake is None:
        return await setup_entry(hass, OPTIONS)
    with patch("test_native_controls.MotionBleak", return_value=fake):
        return await setup_entry(hass, OPTIONS)


def target_writes(writes):
    return [
        data for uuid, data in writes if uuid == TARGET_UUID and data != REFERENCE_STOP
    ]


async def test_operation_entity_contract(hass):
    entry, _ = await setup(hass)
    item = er.async_get(hass).async_get(OPERATION_ID)
    assert item.unique_id == f"{ADDRESS}_operation"
    assert item.translation_key == "operation"
    assert item.entity_category is None
    assert item.disabled_by is None
    assert item.original_device_class == "enum"
    state = hass.states.get(OPERATION_ID)
    assert state.state == "idle"
    assert state.attributes["options"] == [phase.value for phase in Phase]
    assert "reason" not in state.attributes
    assert "requested_height_cm" not in state.attributes
    await hass.config_entries.async_unload(entry.entry_id)


RESET = "custom_components.ha_linak.client.OPERATION_RESET_DELAY"


async def wait_for_state(hass, state, timeout=2.0):
    async with asyncio.timeout(timeout):
        while hass.states.get(OPERATION_ID).state != state:
            await asyncio.sleep(0.01)


async def test_a_settled_result_returns_to_idle_and_is_kept_as_the_last_result(hass):
    entry, _ = await setup(hass)
    journal = Journal(hass)
    with patch(RESET, 0.05), patch(FAST, 0.001):
        await entry.runtime_data.async_move_to_cm(90)
        assert hass.states.get(OPERATION_ID).state == "completed"
        # While the result is the live state, it is not repeated as the last one.
        assert "last_result" not in hass.states.get(OPERATION_ID).attributes
        await wait_for_state(hass, "idle")
    assert journal.phases == ["preparing", "moving", "stopping", "completed", "idle"]
    state = hass.states.get(OPERATION_ID)
    assert state.attributes["last_result"] == "completed"
    assert state.attributes["last_requested_height_cm"] == 90.0
    assert "reason" not in state.attributes
    assert "requested_height_cm" not in state.attributes
    assert "last_reason" not in state.attributes
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failure_keeps_its_reason_in_the_last_result_after_the_reset(hass):
    entry, fake = await setup(hass)
    fake.stall = True
    with (
        patch(RESET, 0.05),
        patch(FAST, 0.001),
        patch("custom_components.ha_linak.motion.STALL_TIMEOUT", 0.01),
        pytest.raises(HomeAssistantError),
    ):
        await entry.runtime_data.async_move_to_cm(83)
    assert hass.states.get(OPERATION_ID).state == "failed"
    await wait_for_state(hass, "idle")
    state = hass.states.get(OPERATION_ID)
    assert state.attributes["last_result"] == "failed"
    assert state.attributes["last_reason"] == "no_progress"
    assert state.attributes["last_requested_height_cm"] == 83.0
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_new_request_cancels_the_pending_reset(hass):
    entry, _ = await setup(hass)
    coordinator = entry.runtime_data
    journal = Journal(hass)
    with patch(RESET, 0.3), patch(FAST, 0.001):
        await coordinator.async_move_to_cm(90)
        first = coordinator.desk._operation_reset
        assert first is not None
        await coordinator.async_move_to_cm(91)
        second = coordinator.desk._operation_reset
        # The first timer is cancelled and replaced, so it can never reset the
        # second operation's result early.
        assert first.cancelled()
        assert second is not first
        assert journal.phases.count("idle") == 0
        await wait_for_state(hass, "idle")
    assert journal.phases.count("idle") == 1
    assert hass.states.get(OPERATION_ID).attributes["last_requested_height_cm"] == 91.0
    await hass.config_entries.async_unload(entry.entry_id)


async def test_the_reset_never_touches_an_active_operation(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    with patch(RESET, 0.05), patch(FAST, HOLD):
        move = asyncio.create_task(coordinator.async_move_to_cm(90))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        coordinator.desk.operation.reset()
        assert hass.states.get(OPERATION_ID).state == "moving"
        await coordinator.async_stop()
        await move
    await wait_for_state(hass, "idle")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_cancels_the_pending_reset(hass):
    entry, _ = await setup(hass)
    with patch(RESET, 30), patch(FAST, 0.001):
        await entry.runtime_data.async_move_to_cm(90)
        desk = entry.runtime_data.desk
        assert desk._operation_reset is not None
        await hass.config_entries.async_unload(entry.entry_id)
        assert desk._operation_reset is None


async def test_an_unload_during_travel_leaves_no_reset_timer_behind(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    desk = coordinator.desk
    fake.stall = True
    with patch(RESET, 30), patch(FAST, HOLD):
        move = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        await hass.config_entries.async_unload(entry.entry_id)
        await move
        # The movement settled while the entry closed, and must not schedule a reset.
        assert desk.operation.status.phase is Phase.INTERRUPTED
        assert desk._operation_reset is None


def test_reset_keeps_the_last_result_and_ignores_unsettled_phases():
    status, changes = tracker()
    status.reset()
    assert status.status == OperationStatus()
    assert status.last is None
    status.begin(83)
    status.moving()
    status.reset()
    assert status.status.phase is Phase.MOVING
    status.fail(Reason.TIMEOUT)
    settled = status.status
    status.reset()
    assert status.status == OperationStatus()
    assert status.last == settled
    published = len(changes)
    status.reset()
    assert len(changes) == published


def test_the_last_result_is_replaced_by_the_next_settled_operation():
    status, _ = tracker()
    status.begin(83)
    status.complete()
    status.reset()
    status.begin(90)
    assert status.last == OperationStatus(Phase.COMPLETED, 83)
    status.interrupt()
    assert status.last == OperationStatus(Phase.INTERRUPTED, 90)


async def test_one_move_publishes_each_phase_once_despite_many_position_ticks(hass):
    entry, fake = await setup(hass, SteppedBleak())
    coordinator = entry.runtime_data
    journal = Journal(hass)
    updates = []
    coordinator.async_add_listener(lambda: updates.append(True))
    with patch(FAST, 0.001):
        await coordinator.async_move_to_cm(90)
    await hass.async_block_till_done()
    assert len(updates) > 6
    assert journal.phases == ["preparing", "moving", "stopping", "completed"]
    assert {attrs["requested_height_cm"] for _, attrs in journal.entries} == {90.0}
    assert "reason" not in journal.entries[-1][1]
    assert hass.states.get("sensor.desk_height").state == "90"
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_saved_position_goal_is_recorded_once_the_slot_is_read(hass):
    entry, _ = await setup(hass)
    journal = Journal(hass)
    await entry.runtime_data.async_move_to_memory(0)
    await hass.async_block_till_done()
    assert journal.phases == [
        "preparing",
        "preparing",
        "moving",
        "stopping",
        "completed",
    ]
    assert "requested_height_cm" not in journal.entries[0][1]
    assert {attrs["requested_height_cm"] for _, attrs in journal.entries[1:]} == {80.04}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_rejected_target_leaves_the_active_operation_untouched(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    with patch(FAST, HOLD):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        before, published = list(fake.writes), len(journal.entries)
        with pytest.raises(ServiceValidationError) as error:
            await coordinator.async_move_to_cm(84)
        assert error.value.translation_key == "control_busy"
        assert fake.writes == before
        assert len(journal.entries) == published
        state = hass.states.get(OPERATION_ID)
        assert state.state == "moving"
        assert state.attributes["requested_height_cm"] == 83.0
        await coordinator.async_stop()
        await first
    assert journal.phases == ["preparing", "moving", "stopping", "interrupted"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_stop_during_travel_is_an_interruption_and_the_next_move_starts_fresh(
    hass,
):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    with patch(FAST, HOLD):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        await coordinator.async_stop()
        await first
    assert journal.phases == ["preparing", "moving", "stopping", "interrupted"]
    assert coordinator.desk.connected
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    fake.stall = False
    journal.entries.clear()
    with patch(FAST, 0.001):
        await coordinator.async_move_to_cm(84)
    assert journal.phases == ["preparing", "moving", "stopping", "completed"]
    assert journal.entries[0][1]["requested_height_cm"] == 84.0
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_cancelled_caller_interrupts_once_its_stop_is_delivered(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    with patch(FAST, HOLD):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    assert journal.phases == ["preparing", "moving", "stopping", "interrupted"]
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_cancelled_caller_whose_stop_fails_is_a_visible_failure(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    with patch(FAST, HOLD):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        fake.fail_stop = True
        first.cancel()
        with pytest.raises(HomeAssistantError):
            await first
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
    assert not coordinator.desk.connected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_cancelled_caller_during_preparation_interrupts_without_a_target(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    prepared = asyncio.Event()
    journal = Journal(hass)

    async def pending(*_args):
        prepared.set()
        await asyncio.Future()

    with patch.object(coordinator.desk, "_query", side_effect=pending):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(prepared.wait(), 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    assert journal.phases == ["preparing", "interrupted"]
    assert target_writes(fake.writes) == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "steps,stop_sent,expected",
    [
        ("preparing", False, Phase.INTERRUPTED),
        ("stopping_from_preparing", False, Phase.INTERRUPTED),
        ("moving", True, Phase.INTERRUPTED),
        ("stopping_from_moving", True, Phase.INTERRUPTED),
        ("moving", False, Phase.FAILED),
        ("stopping_from_moving", False, Phase.FAILED),
    ],
)
def test_a_cancelled_caller_settles_by_what_was_sent(steps, stop_sent, expected):
    desk = desk_at(steps, stop_sent=stop_sent)
    desk._settle_operation(asyncio.CancelledError())
    assert desk.operation.status.phase is expected


async def test_stop_during_preparation_is_an_interruption(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    prepared = asyncio.Event()
    journal = Journal(hass)

    async def pending(*_args):
        prepared.set()
        await asyncio.Future()

    with patch.object(coordinator.desk, "_query", side_effect=pending):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(prepared.wait(), 1)
        assert hass.states.get(OPERATION_ID).state == "preparing"
        await coordinator.async_stop()
        await first
    assert journal.phases == ["preparing", "stopping", "interrupted"]
    assert target_writes(fake.writes) == []
    await hass.config_entries.async_unload(entry.entry_id)


async def test_stop_during_final_cleanup_never_reports_a_completion(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    entered, release = asyncio.Event(), asyncio.Event()
    original = fake.write_gatt_char
    journal = Journal(hass)

    async def hold_final_stop(uuid, data, response):
        if uuid == CONTROL_UUID and data == STOP and fake.target_written.is_set():
            entered.set()
            await release.wait()
        await original(uuid, data, response)

    fake.write_gatt_char = hold_final_stop
    with patch(FAST, 0.001):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(entered.wait(), 1)
        assert hass.states.get(OPERATION_ID).state == "stopping"
        stop = asyncio.create_task(coordinator.async_stop())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, stop)
    assert journal.phases == ["preparing", "moving", "stopping", "interrupted"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failed_stop_is_a_visible_failure(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    with patch(FAST, HOLD):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        fake.fail_stop = True
        with pytest.raises(HomeAssistantError) as stop_error:
            await coordinator.async_stop()
        assert stop_error.value.translation_key == "stop_failed"
        with pytest.raises(HomeAssistantError):
            await first
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
    assert state.attributes["requested_height_cm"] == 83.0
    assert journal.phases[-1] == "failed"
    assert not coordinator.desk.connected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_delivered_stop_reaching_a_request_still_waiting_for_the_client(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    desk = coordinator.desk
    holding, release = asyncio.Event(), asyncio.Event()
    journal = Journal(hass)

    async def hold_client():
        async with desk._lock:
            holding.set()
            await release.wait()

    first = asyncio.create_task(coordinator.async_move_to_cm(83))
    holder = asyncio.create_task(hold_client())
    await asyncio.wait_for(holding.wait(), 1)
    await coordinator.async_stop()
    await first
    release.set()
    await holder
    state = hass.states.get(OPERATION_ID)
    assert state.state == "interrupted"
    assert "reason" not in state.attributes
    assert journal.phases[-1] == "interrupted"
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert target_writes(fake.writes) == []
    assert not desk.control_busy
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failed_stop_before_the_request_started_fails_the_operation(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    desk = coordinator.desk
    holding, release = asyncio.Event(), asyncio.Event()

    async def hold_client():
        async with desk._lock:
            holding.set()
            await release.wait()

    # The request has ended its work but still owns the client until it settles.
    original = desk._stop_outcome
    reached = asyncio.Event()

    async def late(*args):
        reached.set()
        await release.wait()
        return await original(*args)

    desk._stop_outcome = late
    first = asyncio.create_task(coordinator.async_move_to_cm(83))
    holder = asyncio.create_task(hold_client())
    await asyncio.wait_for(holding.wait(), 1)
    fake.fail_stop = True
    stop = asyncio.create_task(coordinator.async_stop())
    await asyncio.wait_for(reached.wait(), 1)
    release.set()
    with pytest.raises(HomeAssistantError):
        await stop
    with pytest.raises(HomeAssistantError):
        await first
    await holder
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "error,stop_error,expected",
    [
        (None, None, Phase.COMPLETED),
        (None, BleakError("x"), Phase.FAILED),
        (MotionStopped("x"), None, Phase.INTERRUPTED),
        (MotionStopped("x"), BleakError("x"), Phase.FAILED),
    ],
)
def test_a_failed_stop_outranks_the_request_outcome(error, stop_error, expected):
    desk = desk_at("moving")
    desk._settle_operation(error, stop_error)
    status = desk.operation.status
    assert status.phase is expected
    assert status.reason is (Reason.STOP_FAILED if stop_error else None)


async def test_the_sensor_follows_changes_while_the_link_stays_down(hass):
    entry, _ = await setup(hass)
    coordinator = entry.runtime_data
    await coordinator.desk._disconnect_link()
    coordinator._changed()
    assert not coordinator.last_update_success
    coordinator.desk.operation.begin(83)
    assert hass.states.get(OPERATION_ID).state == "preparing"
    coordinator.desk.operation.fail(Reason.TIMEOUT)
    assert hass.states.get(OPERATION_ID).state == "failed"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failed_stop_reaching_a_request_still_waiting_for_the_client(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    desk = coordinator.desk
    holding, release = asyncio.Event(), asyncio.Event()

    async def hold_client():
        async with desk._lock:
            holding.set()
            await release.wait()

    # A background read takes the client right after the request is accepted, so
    # the request is still waiting to prepare and has nothing of its own to stop.
    first = asyncio.create_task(coordinator.async_move_to_cm(83))
    holder = asyncio.create_task(hold_client())
    await asyncio.wait_for(holding.wait(), 1)
    assert hass.states.get(OPERATION_ID).state == "preparing"
    fake.fail_stop = True
    with pytest.raises(HomeAssistantError) as stop_error:
        await coordinator.async_stop()
    assert stop_error.value.translation_key == "stop_failed"
    with pytest.raises(HomeAssistantError):
        await first
    release.set()
    await holder
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
    assert state.attributes["requested_height_cm"] == 83.0
    assert not desk.connected
    assert target_writes(fake.writes) == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "guard,reason",
    [("no_progress", "no_progress"), ("timeout", "timeout")],
)
async def test_a_guard_or_deadline_failure_reports_its_reason(hass, guard, reason):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    limits = {
        "no_progress": {"STALL_TIMEOUT": 0.01},
        "timeout": {"STALL_TIMEOUT": 10, "MOVE_TIMEOUT": 0.05},
    }[guard]
    with (
        patch(FAST, 0.001),
        patch.multiple("custom_components.ha_linak.motion", **limits),
    ):
        with pytest.raises(HomeAssistantError) as error:
            await coordinator.async_move_to_cm(83)
    assert error.value.translation_key == "movement_failed"
    assert journal.phases == ["preparing", "moving", "stopping", "failed"]
    state = hass.states.get(OPERATION_ID)
    assert state.attributes["reason"] == reason
    assert state.attributes["requested_height_cm"] == 83.0
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_preparation_failure_never_reaches_travel(hass):
    fake = MotionBleak()
    fake.activation = 0
    fake.reject_activation = True
    entry, _ = await setup(hass, fake)
    journal = Journal(hass)
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_move_to_cm(83)
    assert journal.phases == ["preparing", "failed"]
    assert journal.entries[-1][1]["reason"] == "preparation_failed"
    assert target_writes(fake.writes) == []
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("fault", ["backend_error", "malformed_frame"])
async def test_a_travel_exception_with_a_delivered_stop_is_not_a_stop_failure(
    hass, fault
):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    original = fake.read_gatt_char

    async def faulty(uuid):
        if not fake.target_written.is_set():
            return await original(uuid)
        if fault == "backend_error":
            raise BleakError("private backend details")
        return b"\x01\x02\x03"

    fake.read_gatt_char = faulty
    with patch(FAST, 0.001), pytest.raises(HomeAssistantError):
        await coordinator.async_move_to_cm(83)
    assert journal.phases == ["preparing", "moving", "stopping", "failed"]
    assert journal.entries[-1][1]["reason"] == "unknown"
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_an_earlier_stop_does_not_color_a_later_failure(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    with patch(FAST, HOLD):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        await coordinator.async_stop()
        await first
    assert hass.states.get(OPERATION_ID).state == "interrupted"
    fake.activation = 0
    fake.reject_activation = True
    with pytest.raises(HomeAssistantError):
        await coordinator.async_move_to_cm(84)
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "preparation_failed")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_failed_stop_during_preparation_is_a_visible_failure(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    prepared = asyncio.Event()

    async def pending(*_args):
        prepared.set()
        await asyncio.Future()

    with patch.object(coordinator.desk, "_query", side_effect=pending):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(prepared.wait(), 1)
        fake.fail_stop = True
        with pytest.raises(HomeAssistantError) as stop_error:
            await coordinator.async_stop()
        assert stop_error.value.translation_key == "stop_failed"
        with pytest.raises(HomeAssistantError):
            await first
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
    assert target_writes(fake.writes) == []
    await hass.config_entries.async_unload(entry.entry_id)


async def test_link_loss_during_travel_is_reported_at_once_and_stays_visible(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    journal = Journal(hass)
    with patch(FAST, 0.05):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        fake.is_connected = False
        coordinator.desk._disconnected(fake)
        state = hass.states.get(OPERATION_ID)
        assert (state.state, state.attributes["reason"]) == ("failed", "link_lost")
        with pytest.raises(HomeAssistantError):
            await first
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "link_lost")
    assert journal.phases[0] == "preparing"
    assert hass.states.get("sensor.desk_height").state == "unavailable"
    assert hass.states.get("binary_sensor.desk_connection").state == "off"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_stop_after_link_loss_does_not_rewrite_the_reason(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    fake.stall = True
    with patch(FAST, 0.05):
        first = asyncio.create_task(coordinator.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        fake.is_connected = False
        coordinator.desk._disconnected(fake)
        with pytest.raises(HomeAssistantError) as stop_error:
            await coordinator.async_stop()
        assert stop_error.value.translation_key == "stop_failed"
        with pytest.raises(HomeAssistantError):
            await first
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "link_lost")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_idle_stop_changes_the_status_only_when_it_fails(hass):
    entry, fake = await setup(hass)
    coordinator = entry.runtime_data
    await coordinator.async_stop()
    assert hass.states.get(OPERATION_ID).state == "idle"
    fake.fail_stop = True
    with pytest.raises(HomeAssistantError):
        await coordinator.async_stop()
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "stop_failed")
    assert "requested_height_cm" not in state.attributes
    with patch(RESET, 0.05):
        coordinator.desk.operation.reset()
    state = hass.states.get(OPERATION_ID)
    assert state.state == "idle"
    assert state.attributes["last_result"] == "failed"
    assert state.attributes["last_reason"] == "stop_failed"
    # A lone Stop carried no goal, so none is reported as the last one.
    assert "last_requested_height_cm" not in state.attributes
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconnect_keeps_a_failed_result_and_never_resumes_the_goal():
    desk, fake = await connected_desk()
    fake.stall = True
    settings = ControlSettings.from_options(OPTIONS)
    with patch(FAST, 0.05):
        move = asyncio.create_task(desk.move_to_cm(83, settings))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        fake.is_connected = False
        desk._disconnected(fake)
        assert desk.operation.status == OperationStatus(
            Phase.FAILED, 83, Reason.LINK_LOST
        )
        with pytest.raises(MotionError):
            await move
    assert desk.operation.status.reason is Reason.LINK_LOST
    fresh = MotionBleak()
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fresh
    ):
        await desk.refresh()
    assert desk.connected
    assert desk.operation.status.phase is Phase.FAILED
    assert not desk.operation.status.active
    assert target_writes(fresh.writes) == []
    await desk.disconnect()


async def test_reload_starts_idle_and_replays_nothing(hass):
    fake = MotionBleak()
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
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        fake.stall = True
        with (
            patch(FAST, 0.001),
            patch("custom_components.ha_linak.motion.STALL_TIMEOUT", 0.01),
            pytest.raises(HomeAssistantError),
        ):
            await entry.runtime_data.async_move_to_cm(83)
        assert hass.states.get(OPERATION_ID).attributes["reason"] == "no_progress"
        fake.stall = False
        written = len(fake.writes)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        state = hass.states.get(OPERATION_ID)
        assert state.state == "idle"
        assert "reason" not in state.attributes
        assert "requested_height_cm" not in state.attributes
        assert target_writes(fake.writes[written:]) == []
    await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_report_the_operation_without_identifiers(hass):
    entry, fake = await setup(hass)
    fake.stall = True
    with (
        patch(FAST, 0.001),
        patch("custom_components.ha_linak.motion.STALL_TIMEOUT", 0.01),
        pytest.raises(HomeAssistantError),
    ):
        await entry.runtime_data.async_move_to_cm(83)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["controls"]["operation"] == {
        "phase": "failed",
        "reason": "no_progress",
        "requested_height_cm": 83.0,
        "last_result": "failed",
    }
    assert ADDRESS not in json.dumps(result)
    await hass.config_entries.async_unload(entry.entry_id)


class ReversingBleak(MotionBleak):
    """Moves toward the target once, then retreats like an anti-collision reversal."""

    def __init__(self):
        super().__init__()
        self.reversed = False

    async def write_gatt_char(self, uuid, data, response):
        if uuid == TARGET_UUID and data != REFERENCE_STOP:
            self.writes.append((uuid, bytes(data)))
            self.target_written.set()
            self.position += -100 if self.reversed else 0
            self.reversed = True
            return
        await super().write_gatt_char(uuid, data, response)


async def test_a_reversal_with_a_delivered_stop_fails_without_dropping_the_link(hass):
    fake = ReversingBleak()
    entry, _ = await setup(hass, fake)
    coordinator = entry.runtime_data
    journal = Journal(hass)
    with patch(FAST, 0.001), pytest.raises(HomeAssistantError) as error:
        await coordinator.async_move_to_cm(83)
    assert error.value.translation_key == "movement_reversed"
    assert journal.phases == ["preparing", "moving", "stopping", "failed"]
    assert journal.entries[-1][1]["reason"] == "reverse_motion"
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert coordinator.desk.connected
    await hass.config_entries.async_unload(entry.entry_id)


# --- movement started on the desk panel -------------------------------------

from custom_components.ha_linak.operation import (  # noqa: E402
    PANEL_SETTLE_DELAY,
    PanelMovementWatcher,
    Source,
)


def watcher():
    changes = []
    tr = OperationTracker(lambda: changes.append(tr.status))
    return PanelMovementWatcher(tr), tr


def test_a_panel_movement_is_reported_and_settles_after_a_pause():
    w, tr = watcher()
    w.observe(10_000, 0)
    assert tr.status.phase is Phase.IDLE
    w.observe(10_000, 5)
    assert (tr.status.phase, tr.status.source) == (Phase.MOVING, Source.PANEL)
    assert tr.status.requested_height_cm is None
    w.observe(10_500, 5)
    w._settled()
    assert tr.status.phase is Phase.COMPLETED
    assert tr.status.source is Source.PANEL


def test_residual_speed_before_a_stationary_sample_is_not_a_movement():
    w, tr = watcher()
    w.observe(10_000, 7)
    assert tr.status.phase is Phase.IDLE


def test_a_turn_back_during_a_panel_movement_is_a_possible_obstruction():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    w.observe(9_500, 5)
    w.observe(9_300, 5)
    w.observe(9_600, 5)
    assert (tr.status.phase, tr.status.reason) == (Phase.FAILED, Reason.REVERSE_MOTION)
    # The retreat itself must not start another operation.
    w.observe(9_900, 5)
    assert tr.status.phase is Phase.FAILED


def test_small_jitter_is_not_a_reversal():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    w.observe(10_400, 5)
    w.observe(10_395, 5)
    assert tr.status.phase is Phase.MOVING


def test_a_panel_movement_never_displaces_or_joins_an_explicit_request():
    w, tr = watcher()
    tr.begin(83.0)
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    assert (tr.status.phase, tr.status.source) == (
        Phase.PREPARING,
        Source.HOME_ASSISTANT,
    )
    tr.complete()
    # Residual speed right after the request must not look like a new movement.
    w.observe(10_000, 3)
    assert tr.status.phase is Phase.COMPLETED


def test_an_explicit_request_replaces_an_observed_panel_movement():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    tr.begin(83.0)
    assert (tr.status.phase, tr.status.source) == (
        Phase.PREPARING,
        Source.HOME_ASSISTANT,
    )
    assert tr.status.requested_height_cm == 83.0


def test_the_settle_delay_is_a_real_pause():
    assert PANEL_SETTLE_DELAY >= 1.0


async def test_a_stationary_pause_settles_a_panel_movement_by_timer(hass):
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    with patch("custom_components.ha_linak.operation.PANEL_SETTLE_DELAY", 0.01):
        w.observe(10_300, 0)
        assert tr.status.phase is Phase.MOVING
        await asyncio.sleep(0.05)
    assert tr.status.phase is Phase.COMPLETED


async def test_speed_resuming_cancels_the_pending_settle(hass):
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    with patch("custom_components.ha_linak.operation.PANEL_SETTLE_DELAY", 0.05):
        w.observe(10_300, 0)
        w.observe(10_400, 5)
        await asyncio.sleep(0.1)
    assert tr.status.phase is Phase.MOVING
    w.close()


async def test_a_movement_on_the_panel_reaches_the_operation_sensor(hass):
    entry, _ = await setup(hass)
    desk = entry.runtime_data.desk
    generation = desk._generation

    def notify(position, speed):
        desk._position(generation, bytearray(struct.pack("<HH", position, speed)))

    notify(10_000, 0)
    notify(10_200, 9)
    await hass.async_block_till_done()
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["source"]) == ("moving", "panel")
    assert "requested_height_cm" not in state.attributes
    notify(10_600, 9)
    notify(10_900, 9)
    notify(10_500, 9)
    await hass.async_block_till_done()
    state = hass.states.get(OPERATION_ID)
    assert (state.state, state.attributes["reason"]) == ("failed", "reverse_motion")
    assert desk.connected
    await hass.config_entries.async_unload(entry.entry_id)


def test_a_new_direction_after_a_stationary_sample_is_not_a_turn_back():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    w.observe(9_500, 5)
    w.observe(9_000, 5)
    w.observe(9_000, 0)
    w.observe(9_200, 5)
    w.observe(9_700, 5)
    assert tr.status.phase is Phase.MOVING
    # A turn back without any stationary feedback in between is still reported.
    w.observe(9_300, 5)
    assert (tr.status.phase, tr.status.reason) == (Phase.FAILED, Reason.REVERSE_MOTION)


def test_losing_the_link_during_a_panel_movement_is_not_a_failure():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    tr.link_lost()
    assert tr.status.phase is Phase.IDLE
    assert tr.last is None
    # The next sample cannot resurrect it until feedback is stationary again.
    w.observe(9_000, 5)
    assert tr.status.phase is Phase.IDLE


def test_losing_the_link_during_a_requested_movement_still_fails():
    _, tr = watcher()
    tr.begin(83.0)
    tr.link_lost()
    assert (tr.status.phase, tr.status.reason) == (Phase.FAILED, Reason.LINK_LOST)


def test_a_desk_error_fails_a_panel_movement_but_never_rewrites_a_request():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    tr.desk_error("01005d")
    assert (tr.status.phase, tr.status.reason, tr.status.error_code) == (
        Phase.FAILED,
        Reason.DESK_ERROR,
        "01005d",
    )
    assert tr.status.source is Source.PANEL
    # Speed after the fault must not revive the movement.
    w.observe(9_000, 5)
    assert tr.status.phase is Phase.FAILED
    _, other = watcher()
    other.begin(83.0)
    other.desk_error("01005d")
    assert other.status.phase is Phase.PREPARING


def test_a_desk_error_while_idle_is_still_reported():
    _, tr = watcher()
    tr.desk_error("01005d")
    assert tr.status.phase is Phase.FAILED


def test_the_retreat_after_a_desk_error_does_not_replace_the_reported_fault():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    w.observe(9_000, 5)
    w.observe(9_000, 0)
    tr.desk_error("01005d")
    w.faulted()
    # The desk backs away by itself right after the fault.
    w.observe(9_050, 5)
    w.observe(9_300, 5)
    assert (tr.status.phase, tr.status.reason) == (Phase.FAILED, Reason.DESK_ERROR)
    # The fault is held while the desk retreats, until it reports the fault cleared
    # and has stopped.
    w.observe(9_300, 0)
    w.observe(9_300, 6)
    assert tr.status.phase is Phase.FAILED
    w.fault_cleared()
    w.observe(9_300, 6)
    assert tr.status.phase is Phase.FAILED
    w.observe(9_300, 0)
    w.observe(9_300, 6)
    assert tr.status.phase is Phase.MOVING
    # The reported fault stays available as the last result.
    assert tr.last is not None and tr.last.reason is Reason.DESK_ERROR


def test_an_unreported_clear_still_ends_the_hold_when_the_result_returns_to_idle():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    tr.desk_error("01005d")
    w.faulted()
    tr.reset()
    w.observe(9_000, 0)
    w.observe(9_000, 6)
    assert tr.status.phase is Phase.MOVING


def test_a_retreat_in_several_runs_never_replaces_a_reported_desk_error():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    w.observe(9_000, 5)
    w.observe(9_000, 0)
    tr.desk_error("01005d")
    w.faulted()
    for position in (9_100, 9_300):
        w.observe(position, 5)
        w.observe(position, 0)
        w.observe(position + 10, 6)
    assert (tr.status.phase, tr.status.reason) == (Phase.FAILED, Reason.DESK_ERROR)
    # After the result returns to idle, a new movement is followed again.
    tr.reset()
    w.observe(9_400, 0)
    w.observe(9_400, 6)
    assert tr.status.phase is Phase.MOVING


def test_the_end_of_the_retreat_after_the_cleared_frame_is_not_a_new_movement():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    w.observe(9_000, 5)
    tr.desk_error("01005d")
    w.faulted()
    # The desk stops, backs away, and reports the fault over while still moving.
    w.observe(9_000, 0)
    w.observe(9_100, 6_208)
    w.fault_cleared()
    for position, speed in ((9_300, 5_168), (9_330, 3_808), (9_360, 2_016)):
        w.observe(position, speed)
        assert tr.status.phase is Phase.FAILED
    w.observe(9_370, 0)
    assert tr.status.phase is Phase.FAILED
    w.observe(9_370, 400)
    assert tr.status.phase is Phase.MOVING


def test_a_fault_cleared_while_already_stationary_releases_at_once():
    w, tr = watcher()
    w.observe(10_000, 0)
    w.observe(10_000, 5)
    tr.desk_error("01005d")
    w.faulted()
    w.observe(9_500, 0)
    w.fault_cleared()
    w.observe(9_500, 400)
    assert tr.status.phase is Phase.MOVING
