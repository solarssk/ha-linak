"""Supervised runner checks use fake clients; no scanning or hardware writes."""

import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from scripts.test_motion_hardware import (
    CONTROL_UUID,
    HEIGHT_UUID,
    TARGET_UUID,
    experiment,
    preflight,
    raw_cm,
    run,
    validate,
)


def args(**changes):
    values = dict(
        device="synthetic-device",
        offset_cm=6800,
        minimum_cm=7000,
        maximum_cm=12000,
        target_cm=None,
        stop_after=None,
        confirm_supervised_motion=False,
    )
    return SimpleNamespace(**(values | changes))


def client():
    chars = {
        HEIGHT_UUID: SimpleNamespace(properties=["read"]),
        CONTROL_UUID: SimpleNamespace(properties=["write-without-response"]),
        TARGET_UUID: SimpleNamespace(properties=["write-without-response"]),
    }
    return SimpleNamespace(
        services=SimpleNamespace(get_characteristic=chars.get),
        read_gatt_char=AsyncMock(return_value=b"\xb0\x04\x00\x00"),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
        is_connected=True,
    )


@pytest.mark.parametrize("value", ["NaN", "inf", "1.001", "abc"])
def test_exact_cm(value):
    with pytest.raises(argparse.ArgumentTypeError):
        raw_cm(value)
    assert raw_cm("68.00") == 6800


@pytest.mark.parametrize(
    "changes",
    [
        {"offset_cm": -1},
        {"minimum_cm": 13000},
        {"target_cm": 80},
        {"stop_after": 0.5},
        {"confirm_supervised_motion": True},
        {"target_cm": float("nan"), "confirm_supervised_motion": True},
        {"target_cm": 80, "confirm_supervised_motion": True, "stop_after": 2},
    ],
)
async def test_invalid_input_never_connects(changes):
    with patch("scripts.test_motion_hardware.BleakClient") as factory:
        with pytest.raises(ValueError):
            await run(args(**changes), {})
        factory.assert_not_called()


def test_preflight_rejects_wrong_write_mode():
    fake = client()
    fake.services.get_characteristic(CONTROL_UUID).properties = ["write"]
    with pytest.raises(ValueError):
        preflight(fake)


async def test_inspection_never_sends_control():
    fake, report, options = client(), {}, args()
    await experiment(fake, options, validate(options), report)
    assert report["initial_height_cm"] == 80
    assert report["result"] == "inspection_only_no_control_writes"
    fake.write_gatt_char.assert_not_awaited()


async def test_long_move_rejected_before_any_control_write():
    fake = client()
    options = args(target_cm=83, confirm_supervised_motion=True)
    with pytest.raises(ValueError, match="at most 2 cm"):
        await experiment(fake, options, validate(options), {})
    fake.write_gatt_char.assert_not_awaited()


async def test_motion_uses_shared_controller_and_closes():
    fake, report = client(), {}
    options = args(target_cm=81, confirm_supervised_motion=True)
    with patch("scripts.test_motion_hardware.MotionController") as factory:
        controller = factory.return_value
        controller.move_to_cm = AsyncMock()
        controller.close = AsyncMock()
        controller.stop = AsyncMock()
        await experiment(fake, options, validate(options), report)
        controller.move_to_cm.assert_awaited_once_with(81)
        controller.close.assert_awaited_once()
        assert report["final_height_cm"] == 80


async def test_failed_inspection_disconnects_and_never_writes():
    fake = client()
    fake.connect = AsyncMock(side_effect=ConnectionError("private"))
    with patch("scripts.test_motion_hardware.BleakClient", return_value=fake):
        with pytest.raises(ConnectionError):
            await run(args(), {})
    fake.disconnect.assert_awaited_once()
    fake.write_gatt_char.assert_not_awaited()


async def test_timed_stop_cancels_motion_and_closes():
    import asyncio

    fake, report = client(), {}
    options = args(target_cm=81, confirm_supervised_motion=True, stop_after=0.1)
    with patch("scripts.test_motion_hardware.MotionController") as factory:
        controller = factory.return_value
        worker = None

        async def move(_target):
            nonlocal worker
            worker = asyncio.current_task()
            await asyncio.Future()

        async def stop():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

        controller.move_to_cm = AsyncMock(side_effect=move)
        controller.stop = AsyncMock(side_effect=stop)
        controller.close = AsyncMock()
        await experiment(fake, options, validate(options), report)
        controller.stop.assert_awaited_once()
        controller.close.assert_awaited_once()
        assert report["result"] == "timed_stop_sent_physical_stop_unverified"


async def test_motion_error_still_closes():
    fake = client()
    options = args(target_cm=81, confirm_supervised_motion=True)
    with patch("scripts.test_motion_hardware.MotionController") as factory:
        controller = factory.return_value
        controller.move_to_cm = AsyncMock(side_effect=TimeoutError())
        controller.close = AsyncMock()
        with pytest.raises(TimeoutError):
            await experiment(fake, options, validate(options), {})
        controller.close.assert_awaited_once()
