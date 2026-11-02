"""Bounded movement shared by native HA controls and the supervised runner.

The caller must own the BLE session exclusively for the entire operation.
Physical behavior still requires supervised validation; see docs/movement.md.
"""

import asyncio
from dataclasses import dataclass
from enum import StrEnum
import math
import struct
from typing import Protocol

from bleak import BleakClient

from .protocol import (
    HEIGHT_UUID,
    DISPLAY_HALF_STEP_RAW,
    PositionSample,
    decode_position,
)

CONTROL_UUID = "99fa0002-338a-1024-8a49-009c0215f78a"
TARGET_UUID = "99fa0031-338a-1024-8a49-009c0215f78a"
WAKE = b"\xfe\x00"
STOP = b"\xff\x00"
REFERENCE_STOP = b"\x01\x80"
IO_TIMEOUT = 1.0
READ_TIMEOUT = 3.0
COMMAND_INTERVAL = 0.2
MOVE_TIMEOUT = 30.0
STALL_TIMEOUT = 2.0
TOLERANCE_RAW = 10  # 1 mm; not a promise of the desk's positioning accuracy.


async def _drain_cleanup(settled: asyncio.Future) -> None:
    """Defer repeated cancellation until an already bounded cleanup settles.

    The caller retains ownership until the gather future settles. Cancellation
    handlers re-raise afterward; gather observes failures without cancelling work.
    """
    while not settled.done():
        try:
            await asyncio.shield(settled)
        except asyncio.CancelledError:
            if settled.done():
                raise


class MotionFailure(StrEnum):
    UNKNOWN = "unknown"
    BUSY = "busy"
    LINK_LOST = "link_lost"
    OUTSIDE_LIMITS = "outside_limits"
    REVERSE = "reverse_motion"
    OVERSHOOT = "overshoot"
    STALLED = "no_progress"
    STOP_FAILED = "stop_failed"


class MotionError(Exception):
    """Movement could not complete; never retry automatically."""

    def __init__(self, message: str, reason: MotionFailure = MotionFailure.UNKNOWN):
        super().__init__(message)
        self.reason = reason


class MotionStopped(MotionError):
    """An explicit Stop interrupted movement and its release was delivered."""


@dataclass(frozen=True)
class TravelLimits:
    """Explicitly measured relative travel bounds, not inferred from memories."""

    minimum_raw: int
    maximum_raw: int

    def __post_init__(self) -> None:
        if (
            type(self.minimum_raw) is not int
            or type(self.maximum_raw) is not int
            or not 0 <= self.minimum_raw < self.maximum_raw < 0xFFFF
        ):
            raise ValueError("Travel limits must be ordered unsigned position words")

    def target(self, height_cm: float, offset_raw: int) -> int:
        if (
            isinstance(height_cm, bool)
            or not math.isfinite(height_cm)
            or type(offset_raw) is not int
            or not 0 <= offset_raw < 0xFFFF
        ):
            raise ValueError("Height and offset must be finite valid measurements")
        relative = height_cm * 100 - offset_raw
        if self.minimum_raw == 0 and -DISPLAY_HALF_STEP_RAW <= relative < 0:
            relative = 0
        if not self.minimum_raw <= relative <= self.maximum_raw:
            raise ValueError("Target height is outside the measured travel limits")
        return round(relative)


class MotionTransport(Protocol):
    """An already connected, exclusively owned session; no connect/retry API."""

    @property
    def connected(self) -> bool: ...

    async def read_position(self) -> PositionSample: ...
    async def write_control(self, payload: bytes) -> None: ...
    async def write_target(self, payload: bytes) -> None: ...
    async def disconnect(self) -> None: ...


class BleakMotionTransport:
    """Transport adapter for an already connected, exclusively owned session."""

    def __init__(self, client: BleakClient) -> None:
        self.client = client

    @property
    def connected(self) -> bool:
        return self.client.is_connected

    async def read_position(self) -> PositionSample:
        return decode_position(bytes(await self.client.read_gatt_char(HEIGHT_UUID)))

    async def write_control(self, payload: bytes) -> None:
        if payload != STOP:
            await self.client.write_gatt_char(CONTROL_UUID, payload, response=False)
            return
        # Stop both command channels. A failed control write must not skip the
        # reference release; both writes share the caller's bounded deadline.
        failure: Exception | None = None
        try:
            await self.client.write_gatt_char(CONTROL_UUID, STOP, response=False)
        except Exception as err:
            failure = err
        await self.client.write_gatt_char(TARGET_UUID, REFERENCE_STOP, response=False)
        if failure is not None:
            raise failure

    async def write_target(self, payload: bytes) -> None:
        await self.client.write_gatt_char(TARGET_UUID, payload, response=False)

    async def disconnect(self) -> None:
        await self.client.disconnect()


class MotionController:
    """One explicit target at a time; cancellation and failures attempt Stop."""

    def __init__(
        self, transport: MotionTransport, limits: TravelLimits, offset_raw: int
    ) -> None:
        self.transport = transport
        self.limits = limits
        self.offset_raw = offset_raw
        self._task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def moving(self) -> bool:
        return self._task is not None or (
            self._stop_task is not None and not self._stop_task.done()
        )

    async def _control(self, payload: bytes) -> None:
        async with asyncio.timeout(IO_TIMEOUT):
            await self.transport.write_control(payload)

    async def _read(self) -> int:
        if not self.transport.connected:
            raise MotionError(
                "Desk disconnected; movement will not resume", MotionFailure.LINK_LOST
            )
        async with asyncio.timeout(READ_TIMEOUT):
            position = (await self.transport.read_position()).position_raw
        if not self.limits.minimum_raw <= position <= self.limits.maximum_raw:
            raise MotionError(
                "Position is outside the measured travel limits",
                MotionFailure.OUTSIDE_LIMITS,
            )
        return position

    async def _discard(self) -> None:
        self._closed = True
        try:
            async with asyncio.timeout(IO_TIMEOUT):
                await self.transport.disconnect()
        except Exception:
            pass

    async def _stop(self) -> None:
        try:
            if not self.transport.connected:
                raise MotionError("Desk disconnected; Stop cannot be delivered")
            await self._control(STOP)
        except Exception as err:
            await self._discard()
            raise MotionError(
                "Stop could not be confirmed; session discarded",
                MotionFailure.STOP_FAILED,
            ) from err

    async def _finish_move(self, discard: bool) -> None:
        try:
            await self._stop()
        finally:
            if discard:
                await self._discard()

    async def move_to_cm(self, height_cm: float) -> None:
        target = self.limits.target(height_cm, self.offset_raw)
        if self._closed or not self.transport.connected:
            raise MotionError("Movement requires an open, connected session")
        if self.moving:
            raise MotionError("Another movement is active; stop it first")
        # No await between the busy check and reservation.
        task = self._task = asyncio.create_task(self._move(target))
        try:
            await task
        finally:
            # Only the movement caller releases this reservation. Explicit Stop
            # keeps its separate reservation until its entire operation finishes.
            self._task = None

    async def _move(self, target: int) -> None:
        discard = False
        try:
            async with asyncio.timeout(MOVE_TIMEOUT):
                position = await self._read()
                if abs(target - position) <= TOLERANCE_RAW:
                    return
                direction = 1 if target > position else -1
                await self._control(STOP)
                await self._control(WAKE)
                loop = asyncio.get_running_loop()
                progress_at = loop.time()
                best_position = position
                payload = struct.pack("<H", target)
                while abs(target - position) > TOLERANCE_RAW:
                    if not self.transport.connected:
                        raise MotionError(
                            "Desk disconnected; movement will not resume",
                            MotionFailure.LINK_LOST,
                        )
                    async with asyncio.timeout(IO_TIMEOUT):
                        await self.transport.write_target(payload)
                    # Target writes require a timed keepalive, rather than an
                    # event emitted by the desk. Schedule that deadline explicitly.
                    tick = asyncio.Event()
                    timer = loop.call_later(COMMAND_INTERVAL, tick.set)
                    try:
                        await tick.wait()
                    finally:
                        timer.cancel()
                    position = await self._read()
                    if (position - best_position) * direction < -TOLERANCE_RAW:
                        raise MotionError(
                            "Desk moved away from the requested target",
                            MotionFailure.REVERSE,
                        )
                    if (target - position) * direction < -TOLERANCE_RAW:
                        raise MotionError(
                            "Desk passed the requested target", MotionFailure.OVERSHOOT
                        )
                    if (position - best_position) * direction > 0:
                        progress_at = loop.time()
                        best_position = position
                    elif loop.time() - progress_at >= STALL_TIMEOUT:
                        raise MotionError(
                            "Desk stopped making progress", MotionFailure.STALLED
                        )
        except TimeoutError:
            # A timed-out GATT operation may still have reached the device.
            # Never accept another target on this ambiguous session.
            self._closed = True
            discard = True
            raise
        finally:
            # Stop uses its own deadline, outside the movement deadline. Shield it
            # so cancellation of an HA action cannot cancel the Stop packet.
            cleanup = asyncio.create_task(self._finish_move(discard))
            settled = asyncio.gather(cleanup, return_exceptions=True)
            try:
                await asyncio.shield(settled)
            except asyncio.CancelledError:
                await _drain_cleanup(settled)
                cleanup.result()
                raise
            cleanup.result()

    async def stop(self) -> None:
        # All callers share one reserved operation, including its last Stop write.
        # Cancelling a caller must neither release ownership nor cancel that write.
        if self._stop_task is None or self._stop_task.done():
            if self._task is not None and not self._task.cancelling():
                self._task.cancel()
            self._stop_task = asyncio.create_task(self._finish_stop())
        # Observe late errors even if the caller cancels its shielded await.
        result = (
            await asyncio.shield(
                asyncio.gather(self._stop_task, return_exceptions=True)
            )
        )[0]
        if isinstance(result, BaseException):
            raise result

    async def _finish_stop(self) -> None:
        task = self._task
        if task is not None:
            result = (await asyncio.gather(task, return_exceptions=True))[0]
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                raise result
        # Also needed when cancellation prevented the worker from ever starting.
        await self._stop()

    async def close(self) -> None:
        self._closed = True
        try:
            await self.stop()
        except asyncio.CancelledError:
            # stop() shields its reserved operation. Let that bounded operation
            # settle before disconnecting, including after repeated cancellation.
            assert self._stop_task is not None
            settled = asyncio.gather(self._stop_task, return_exceptions=True)
            await _drain_cleanup(settled)
            raise
        finally:
            async with asyncio.timeout(IO_TIMEOUT):
                await self.transport.disconnect()
