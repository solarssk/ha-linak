"""Explicit, supervised motion experiment; never imported by the integration.

Run from the repository root with python -m scripts.test_motion_hardware --help.
"""

import argparse
import asyncio
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
import json
import math
import platform

from bleak import BleakClient

from custom_components.ha_linak.motion import (
    BleakMotionTransport,
    CONTROL_UUID,
    IO_TIMEOUT,
    MotionController,
    TARGET_UUID,
    TravelLimits,
)
from custom_components.ha_linak.protocol import HEIGHT_UUID

MAX_TEST_DISTANCE_CM = 2.0


def raw_cm(value: str) -> int:
    """Accept exact 0.01 cm input rather than silently rounding measurements."""
    try:
        number = Decimal(value) * 100
    except InvalidOperation as err:
        raise argparse.ArgumentTypeError("Use a numeric centimeter value") from err
    if not number.is_finite() or number != number.to_integral_value():
        raise argparse.ArgumentTypeError(
            "Use finite centimeters with at most 2 decimals"
        )
    return int(number)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--device", required=True, help="Private local BLE identifier")
    result.add_argument("--offset-cm", required=True, type=raw_cm)
    result.add_argument("--minimum-cm", required=True, type=raw_cm)
    result.add_argument("--maximum-cm", required=True, type=raw_cm)
    result.add_argument("--target-cm", type=float)
    result.add_argument(
        "--stop-after", type=float, help="Request Stop after 0.1–1 seconds"
    )
    result.add_argument("--confirm-supervised-motion", action="store_true")
    return result


def validate(args) -> TravelLimits:
    if not 0 <= args.offset_cm < 0xFFFF:
        raise ValueError("Offset is outside the protocol range")
    limits = TravelLimits(
        args.minimum_cm - args.offset_cm, args.maximum_cm - args.offset_cm
    )
    if args.target_cm is not None:
        limits.target(args.target_cm, args.offset_cm)
        if not args.confirm_supervised_motion:
            raise ValueError("Movement requires --confirm-supervised-motion")
    elif args.confirm_supervised_motion or args.stop_after is not None:
        raise ValueError("Confirmation and timed Stop require a target")
    if args.stop_after is not None and (
        not math.isfinite(args.stop_after) or not 0.1 <= args.stop_after <= 1
    ):
        raise ValueError("Timed Stop must be between 0.1 and 1 seconds")
    return limits


def preflight(client) -> dict:
    properties = {}
    for uuid, required in (
        (HEIGHT_UUID, "read"),
        (CONTROL_UUID, "write-without-response"),
        (TARGET_UUID, "write-without-response"),
    ):
        char = client.services.get_characteristic(uuid)
        if char is None or required not in char.properties:
            raise ValueError("Required characteristic or operation is unavailable")
        properties[uuid] = sorted(char.properties)
    return properties


async def experiment(client, args, limits, report) -> None:
    """Use one dedicated connection; the caller must disable other desk clients."""
    report["stage"] = "characteristic_preflight"
    report["properties"] = preflight(client)
    report["stage"] = "initial_height"
    transport = BleakMotionTransport(client)
    async with asyncio.timeout(IO_TIMEOUT):
        initial = (await transport.read_position()).position_raw
    if not limits.minimum_raw <= initial <= limits.maximum_raw:
        raise ValueError("Initial height is outside supplied measured limits")
    report["initial_height_cm"] = (initial + args.offset_cm) / 100
    if args.target_cm is None:
        report["result"] = "inspection_only_no_control_writes"
        return
    report["stage"] = "short_target_validation"
    target = limits.target(args.target_cm, args.offset_cm)
    if abs(target - initial) > MAX_TEST_DISTANCE_CM * 100:
        raise ValueError("A supervised test may move at most 2 cm from current height")
    report["target_height_cm"] = args.target_cm
    report["stage"] = "movement"
    controller = MotionController(transport, limits, args.offset_cm)
    try:
        task = asyncio.create_task(controller.move_to_cm(args.target_cm))
        try:
            if args.stop_after is None:
                await task
                report["result"] = "target_loop_completed_physical_result_unverified"
            else:
                done, _ = await asyncio.wait({task}, timeout=args.stop_after)
                if done:
                    await task
                    report["result"] = "completed_before_timed_stop"
                else:
                    await controller.stop()
                    report["result"] = "timed_stop_sent_physical_stop_unverified"
        finally:
            if not task.done():
                await controller.stop()
            await asyncio.gather(task, return_exceptions=True)
        async with asyncio.timeout(IO_TIMEOUT):
            final = (await transport.read_position()).position_raw
        report["final_height_cm"] = (final + args.offset_cm) / 100
    finally:
        # close() settles Stop before disconnect, including caller cancellation.
        await controller.close()


async def run(args, report) -> None:
    report["stage"] = "input_validation"
    limits = validate(args)  # Reject invalid input before any BLE connection.
    report["configuration"] = {
        "offset_cm": args.offset_cm / 100,
        "minimum_cm": args.minimum_cm / 100,
        "maximum_cm": args.maximum_cm / 100,
        "stop_after_seconds": args.stop_after,
    }
    report["stage"] = "connect"
    client = BleakClient(args.device, timeout=15)
    try:
        async with asyncio.timeout(20):
            await client.connect()
        await experiment(client, args, limits, report)
    finally:
        async with asyncio.timeout(IO_TIMEOUT):
            await client.disconnect()


def main() -> int:
    args = parser().parse_args()
    report = {
        "schema": 1,
        "physical_observation_required": True,
        "python": platform.python_version(),
        "os": platform.system(),
        "bleak": version("bleak"),
    }
    code = 0
    try:
        asyncio.run(run(args, report))
    except KeyboardInterrupt:
        report["result"] = "interrupted_check_physical_stop"
        code = 130
    except Exception as err:
        # Never serialize backend errors: they may contain private identifiers.
        report["result"] = "failed_check_physical_stop"
        report["error_type"] = type(err).__name__
        code = 1
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
