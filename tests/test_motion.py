"""Movement failure scenarios without Bluetooth or physical desk movement."""

import asyncio
import struct
from unittest.mock import patch

import pytest

from custom_components.ha_linak.motion import (
    MotionController,
    MotionError,
    STOP,
    WAKE,
    TravelLimits,
)
from custom_components.ha_linak.protocol import PositionSample


class Transport:
    connected = True

    def __init__(self, positions=(1400, 1450, 1500)):
        self.positions = iter(positions)
        self.last = 1400
        self.writes = []
        self.target_written = asyncio.Event()
        self.fail_stop = False
        self.hang_target = False

    async def read_position(self):
        self.last = next(self.positions, self.last)
        return PositionSample(self.last, 0)

    async def write_control(self, payload):
        self.writes.append(payload)
        if payload == STOP and self.fail_stop:
            raise ConnectionError("Stop failed")

    async def write_target(self, payload):
        self.writes.append(payload)
        self.target_written.set()
        if self.hang_target:
            await asyncio.Future()

    async def disconnect(self):
        self.connected = False


@pytest.fixture(autouse=True)
def fast_motion():
    with (
        patch("custom_components.ha_linak.motion.COMMAND_INTERVAL", 0.001),
        patch("custom_components.ha_linak.motion.STALL_TIMEOUT", 0.01),
        patch("custom_components.ha_linak.motion.IO_TIMEOUT", 0.03),
    ):
        yield


def controller(transport):
    return MotionController(transport, TravelLimits(0, 6000), 6800)


def test_measured_limits_and_centimeter_conversion():
    limits = TravelLimits(0, 6000)
    assert limits.target(82.38, 6800) == 1438
    for height in (float("nan"), float("inf"), -1, 129, True):
        with pytest.raises(ValueError):
            limits.target(height, 6800)
    for bounds in ((6000, 0), (-1, 10), (0, 65535), (0.0, 6000), (0, 0)):
        with pytest.raises(ValueError):
            TravelLimits(*bounds)


async def test_target_and_final_stop():
    transport = Transport()
    await controller(transport).move_to_cm(83)
    assert transport.writes == [
        STOP,
        WAKE,
        struct.pack("<H", 1500),
        struct.pack("<H", 1500),
        STOP,
    ]


async def test_already_at_height_does_not_wake_or_target():
    transport = Transport((1500,))
    await controller(transport).move_to_cm(83)
    assert transport.writes == [STOP]


@pytest.mark.parametrize(
    "positions,reason",
    [
        ((1400,), "progress"),
        ((1400, 1300), "away"),
        ((1400, 1600), "passed"),
        ((1400, 6500), "limits"),
    ],
)
async def test_feedback_abort_always_stops(positions, reason):
    transport = Transport(positions)
    motion = controller(transport)
    with pytest.raises(MotionError, match=reason):
        await motion.move_to_cm(83)
    assert transport.writes[-1] == STOP


async def test_timeout_always_stops():
    transport = Transport()
    transport.hang_target = True
    motion = controller(transport)
    with pytest.raises(TimeoutError):
        await motion.move_to_cm(83)
    assert transport.writes[-1] == STOP


async def test_explicit_stop_cancels_pending_write_and_no_later_targets():
    transport = Transport()
    transport.hang_target = True
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await transport.target_written.wait()
    with pytest.raises(MotionError, match="active"):
        await motion.move_to_cm(84)
    await motion.stop()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not motion.moving
    assert transport.writes[-1] == STOP
    writes = list(transport.writes)
    await asyncio.sleep(0.01)
    assert transport.writes == writes


async def test_caller_cancellation_and_close_stop_before_disconnect():
    transport = Transport()
    transport.hang_target = True
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await transport.target_written.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.writes[-1] == STOP
    await motion.close()
    assert not transport.connected
    with pytest.raises(MotionError, match="open"):
        await motion.move_to_cm(83)


async def test_link_loss_never_reconnects_or_resumes():
    transport = Transport()
    transport.hang_target = True
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await transport.target_written.wait()
    transport.connected = False
    with pytest.raises(MotionError, match="discarded"):
        await task
    assert not motion.moving
    with pytest.raises(MotionError):
        await motion.move_to_cm(83)


async def test_stop_failure_discards_session():
    transport = Transport()
    transport.fail_stop = True
    motion = controller(transport)
    with pytest.raises(MotionError, match="discarded"):
        await motion.move_to_cm(83)
    assert not transport.connected


def test_movement_is_not_imported_by_runtime():
    from pathlib import Path

    root = Path(__file__).parents[1] / "custom_components/ha_linak"
    for path in root.glob("*.py"):
        if path.name != "motion.py":
            assert "from .motion import" not in path.read_text()
            assert "import motion" not in path.read_text()


async def test_total_movement_deadline_stops_even_with_slow_progress():
    transport = Transport(tuple(range(1400, 1500)))
    motion = controller(transport)
    with (
        patch("custom_components.ha_linak.motion.MOVE_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await motion.move_to_cm(83)
    assert transport.writes[-1] == STOP


async def test_downward_target_uses_same_feedback_and_stop_path():
    transport = Transport((1500, 1450, 1400))
    await controller(transport).move_to_cm(82)
    assert transport.writes == [
        STOP,
        WAKE,
        struct.pack("<H", 1400),
        struct.pack("<H", 1400),
        STOP,
    ]


async def test_bad_target_sends_no_packets():
    transport = Transport()
    motion = controller(transport)
    with pytest.raises(ValueError):
        await motion.move_to_cm(200)
    assert transport.writes == []


async def test_stop_before_worker_starts_still_sends_stop():
    transport = Transport()
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await asyncio.sleep(0)  # move_to reserves its child; the child has not run yet.
    await motion.stop()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.writes == [STOP]
    assert not motion.moving


async def test_malformed_feedback_stops_without_waking():
    transport = Transport((65535,))
    motion = controller(transport)
    with pytest.raises(MotionError, match="limits"):
        await motion.move_to_cm(83)
    assert transport.writes == [STOP]


async def test_concurrent_stop_requests_do_not_cancel_cleanup():
    transport = Transport()
    transport.hang_target = True
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await transport.target_written.wait()
    await asyncio.gather(motion.stop(), motion.stop())
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.writes[-1] == STOP
    assert not motion.moving


async def test_bleak_adapter_uses_expected_characteristics_and_write_mode():
    from unittest.mock import AsyncMock, Mock

    from custom_components.ha_linak.motion import (
        BleakMotionTransport,
        CONTROL_UUID,
        TARGET_UUID,
    )
    from custom_components.ha_linak.protocol import HEIGHT_UUID

    client = Mock()
    client.is_connected = True
    client.read_gatt_char = AsyncMock(return_value=bytearray.fromhex("9e050000"))
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    adapter = BleakMotionTransport(client)
    assert adapter.connected
    assert await adapter.read_position() == PositionSample(1438, 0)
    client.read_gatt_char.assert_awaited_once_with(HEIGHT_UUID)
    await adapter.write_control(STOP)
    client.write_gatt_char.assert_awaited_with(CONTROL_UUID, STOP, response=False)
    target = struct.pack("<H", 1500)
    await adapter.write_target(target)
    client.write_gatt_char.assert_awaited_with(TARGET_UUID, target, response=False)
    await adapter.disconnect()
    client.disconnect.assert_awaited_once()
    client.is_connected = False
    assert not adapter.connected


async def test_disconnect_between_command_acceptance_and_first_read():
    transport = Transport()
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await asyncio.sleep(0)  # reserve the worker before its first read
    transport.connected = False
    with pytest.raises(MotionError, match="discarded"):
        await task
    assert transport.writes == []
    assert not motion.moving


async def test_disconnect_after_wake_sends_no_target():
    class DisconnectOnWake(Transport):
        async def write_control(self, payload):
            await super().write_control(payload)
            if payload == WAKE:
                self.connected = False

    transport = DisconnectOnWake()
    motion = controller(transport)
    with pytest.raises(MotionError, match="discarded"):
        await motion.move_to_cm(83)
    assert transport.writes == [STOP, WAKE]
    assert not motion.moving


async def test_stop_and_disconnect_failure_keeps_controller_closed():
    class FailedDisconnect(Transport):
        async def disconnect(self):
            raise ConnectionError("disconnect failed")

    transport = FailedDisconnect()
    transport.fail_stop = True
    motion = controller(transport)
    with pytest.raises(MotionError, match="discarded"):
        await motion.stop()
    # Even if disconnect fails and BLE still reports connected, no new target
    # may be accepted on a session whose Stop failed.
    assert transport.connected
    with pytest.raises(MotionError, match="open"):
        await motion.move_to_cm(83)
    assert transport.writes == [STOP]


class DelayedFinalStop(Transport):
    def __init__(self):
        super().__init__((1500,))
        self.stop_started = asyncio.Event()
        self.release_stop = asyncio.Event()

    async def write_control(self, payload):
        assert payload == STOP
        self.stop_started.set()
        await self.release_stop.wait()
        await super().write_control(payload)


async def test_cancellation_during_final_stop_preserves_stop_delivery():
    transport = DelayedFinalStop()
    motion = controller(transport)
    task = asyncio.create_task(motion.move_to_cm(83))
    await transport.stop_started.wait()
    task.cancel()
    # Worker is cancelled while awaiting its shielded cleanup. The Stop itself
    # must stay alive and finish before the movement caller observes cancellation.
    await asyncio.sleep(0)
    assert not task.done()
    transport.release_stop.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.writes == [STOP]
    assert not motion.moving


async def test_cancelling_stop_caller_does_not_cancel_worker_cleanup():
    transport = DelayedFinalStop()
    motion = controller(transport)
    move = asyncio.create_task(motion.move_to_cm(83))
    await transport.stop_started.wait()
    stop = asyncio.create_task(motion.stop())
    await asyncio.sleep(0)  # Stop cancels the worker and waits for its cleanup
    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    assert motion.moving  # reservation remains until cleanup completes
    with pytest.raises(MotionError, match="active"):
        await motion.move_to_cm(84)
    transport.release_stop.set()
    with pytest.raises(asyncio.CancelledError):
        await move
    await motion.stop()  # join the reserved Stop after its original caller cancelled
    assert transport.writes == [STOP, STOP]
    assert not motion.moving


async def test_stop_at_worker_completion_releases_ownership_before_caller_resumes():
    # Python supports eagerly started tasks. A completion callback can finish a
    # Stop before the original movement caller resumes from its worker await.
    transport = DelayedFinalStop()
    motion = controller(transport)
    loop = asyncio.get_running_loop()
    old_factory = loop.get_task_factory()
    stops = []

    def worker_done(_task):
        stops.append(asyncio.create_task(motion.stop(), eager_start=True))

    def task_factory(loop, coro, **kwargs):
        task = asyncio.Task(coro, loop=loop, **kwargs)
        if coro.__qualname__ == "MotionController._move":
            task.add_done_callback(worker_done)
        return task

    loop.set_task_factory(task_factory)
    try:
        move = asyncio.create_task(motion.move_to_cm(83))
        await transport.stop_started.wait()
        transport.release_stop.set()
        await move
        await asyncio.gather(*stops)
    finally:
        loop.set_task_factory(old_factory)
    assert len(stops) == 1
    assert transport.writes == [STOP, STOP]
    assert not motion.moving
    # Completion has released ownership; another explicit target is accepted.
    await motion.move_to_cm(83)
    assert not motion.moving


@pytest.mark.parametrize("operation", ["target", "read"])
async def test_io_timeout_discards_session_even_when_final_stop_succeeds(operation):
    class HangingIO(Transport):
        async def read_position(self):
            if operation == "read":
                await asyncio.Future()
            return await super().read_position()

    transport = HangingIO()
    transport.hang_target = operation == "target"
    motion = controller(transport)
    with pytest.raises(TimeoutError):
        await motion.move_to_cm(83)
    assert transport.writes[-1] == STOP
    assert not transport.connected
    with pytest.raises(MotionError, match="open"):
        await motion.move_to_cm(83)


async def test_pending_explicit_stop_blocks_new_targets_and_concurrent_stops():
    class DelayedThirdStop(Transport):
        def __init__(self):
            super().__init__()
            self.hang_target = True
            self.stop_count = 0
            self.final_stop_started = asyncio.Event()
            self.release_final_stop = asyncio.Event()

        async def write_control(self, payload):
            if payload == STOP:
                self.stop_count += 1
                if self.stop_count == 3:
                    self.final_stop_started.set()
                    await self.release_final_stop.wait()
            await super().write_control(payload)

    transport = DelayedThirdStop()
    motion = controller(transport)
    move = asyncio.create_task(motion.move_to_cm(83))
    await transport.target_written.wait()
    stop = asyncio.create_task(motion.stop())
    await transport.final_stop_started.wait()
    try:
        with pytest.raises(asyncio.CancelledError):
            await move
        assert motion.moving
        with pytest.raises(MotionError, match="active"):
            await motion.move_to_cm(84)
        another_stop = asyncio.create_task(motion.stop())
        await asyncio.sleep(0)
        assert not another_stop.done()
        transport.release_final_stop.set()
        await asyncio.gather(stop, another_stop)
        assert not motion.moving
        writes = list(transport.writes)
        await asyncio.sleep(0.01)
        assert transport.writes == writes
    finally:
        transport.release_final_stop.set()
        await asyncio.gather(stop, return_exceptions=True)


async def test_worker_stop_failure_is_reported_to_explicit_stop_caller():
    transport = Transport()
    transport.hang_target = True
    motion = controller(transport)
    move = asyncio.create_task(motion.move_to_cm(83))
    await transport.target_written.wait()
    transport.fail_stop = True
    with pytest.raises(MotionError, match="discarded"):
        await motion.stop()
    with pytest.raises(MotionError, match="discarded"):
        await move
    assert not transport.connected
    assert not motion.moving


async def test_cancelling_caller_during_last_explicit_stop_keeps_reservation():
    class FinalStop(Transport):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def write_control(self, payload):
            self.started.set()
            await self.release.wait()
            await super().write_control(payload)

    transport = FinalStop()
    motion = controller(transport)
    caller = asyncio.create_task(motion.stop())
    await transport.started.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert motion.moving
    with pytest.raises(MotionError, match="active"):
        await motion.move_to_cm(83)
    transport.release.set()
    await motion.stop()
    assert transport.writes == [STOP]
    assert not motion.moving


@pytest.mark.parametrize("repeat_cancel", ["none", "pending", "completion"])
async def test_cancelled_close_waits_for_final_stop_before_disconnect(repeat_cancel):
    class OrderedClose(DelayedFinalStop):
        def __init__(self):
            super().__init__()
            self.events = []

        async def write_control(self, payload):
            await super().write_control(payload)
            assert self.connected
            self.events.append("stop")
            current = asyncio.current_task()
            if (
                repeat_cancel == "completion"
                and current.get_coro().__qualname__ == "MotionController._finish_stop"
            ):
                current.add_done_callback(lambda _task: close.cancel())

        async def disconnect(self):
            self.events.append("disconnect")
            await super().disconnect()

    transport = OrderedClose()
    motion = controller(transport)
    move = asyncio.create_task(motion.move_to_cm(83))
    await transport.stop_started.wait()
    close = asyncio.create_task(motion.close())
    await asyncio.sleep(0)
    close.cancel()
    await asyncio.sleep(0)
    try:
        assert transport.connected
        assert not close.done()
        if repeat_cancel == "pending":
            close.cancel()
            await asyncio.sleep(0)
            assert transport.connected
            assert not close.done()
        transport.release_stop.set()
        with pytest.raises(asyncio.CancelledError):
            await close
        with pytest.raises(asyncio.CancelledError):
            await move
        assert transport.events[-1] == "disconnect"
        assert transport.events[:-1] == ["stop", "stop"]
        assert not motion.moving
    finally:
        transport.release_stop.set()
        await asyncio.gather(close, move, return_exceptions=True)
        await asyncio.gather(motion.stop(), return_exceptions=True)


async def test_cancelled_close_respects_stop_deadline_and_discards_failed_session():
    transport = DelayedFinalStop()
    motion = controller(transport)
    move = asyncio.create_task(motion.move_to_cm(83))
    await transport.stop_started.wait()
    close = asyncio.create_task(motion.close())
    await asyncio.sleep(0)
    close.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close
    with pytest.raises(MotionError, match="discarded"):
        await move
    assert not transport.connected
    assert not motion.moving


@pytest.mark.parametrize("stop_succeeds", [True, False])
async def test_repeated_move_cancellation_keeps_stop_and_reservation_alive(
    stop_succeeds,
):
    transport = DelayedFinalStop()
    motion = controller(transport)
    move = asyncio.create_task(motion.move_to_cm(83))
    await transport.stop_started.wait()
    try:
        move.cancel()
        await asyncio.sleep(0)
        move.cancel()
        await asyncio.sleep(0)
        assert motion.moving
        assert not move.done()
        with pytest.raises(MotionError, match="active"):
            await motion.move_to_cm(84)
        if stop_succeeds:
            transport.release_stop.set()
            with pytest.raises(asyncio.CancelledError):
                await move
            assert transport.writes == [STOP]
        else:
            with pytest.raises(MotionError, match="discarded"):
                await move
            assert not transport.connected
            with pytest.raises(MotionError, match="open"):
                await motion.move_to_cm(83)
        assert not motion.moving
    finally:
        transport.release_stop.set()
        await asyncio.gather(move, return_exceptions=True)


@pytest.mark.parametrize(
    "positions,expected_targets",
    [
        ((1400, 1395, 1390, 1385), 3),
        ((1600, 1605, 1610, 1615), 3),
        ((1400, 1420, 1415, 1410, 1405), 4),
        ((1600, 1580, 1585, 1590, 1595), 4),
    ],
)
async def test_cumulative_retreat_from_best_position_aborts(
    positions, expected_targets
):
    transport = Transport(positions)
    motion = controller(transport)
    with pytest.raises(MotionError, match="away"):
        await motion.move_to_cm(83)
    assert transport.writes[-1] == STOP
    assert transport.writes.count(struct.pack("<H", 1500)) == expected_targets
    assert not motion.moving


async def test_backward_jitter_does_not_reset_progress_deadline():
    transport = Transport((1400, 1395, 1400, 1395, 1400))
    motion = controller(transport)
    with (
        patch("custom_components.ha_linak.motion.STALL_TIMEOUT", 0),
        pytest.raises(MotionError, match="progress"),
    ):
        await motion.move_to_cm(83)
    assert transport.writes == [STOP, WAKE, struct.pack("<H", 1500), STOP]


@pytest.mark.parametrize(
    "positions",
    [
        (1400, 1408, 1403, 1410, 1405, 1450, 1445, 1500),
        (1600, 1592, 1597, 1590, 1595, 1550, 1555, 1500),
    ],
)
async def test_small_feedback_retreat_with_forward_progress_is_tolerated(positions):
    transport = Transport(positions)
    motion = controller(transport)
    await motion.move_to_cm(83)
    assert transport.writes[-1] == STOP
    assert transport.last == 1500
    assert not motion.moving
