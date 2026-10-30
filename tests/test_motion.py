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
