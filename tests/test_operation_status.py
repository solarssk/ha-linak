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
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    }
    assert ADDRESS not in json.dumps(result)
    await hass.config_entries.async_unload(entry.entry_id)
