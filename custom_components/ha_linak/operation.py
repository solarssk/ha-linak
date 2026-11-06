"""Status of the explicit desk operation, without Home Assistant or Bluetooth imports."""

import asyncio
from collections.abc import Callable
import time
from dataclasses import dataclass
from enum import StrEnum
import logging

_LOGGER = logging.getLogger(__name__)

# Seconds a settled result stays visible before the status returns to idle. The
# result itself is kept as the last result, so only the live phase resets.
OPERATION_RESET_DELAY = 10
# Seconds a reported desk fault keeps holding back panel observation when the
# desk's own "fault cleared" frame never arrives.
FAULT_HOLD_MAX = 30.0


class Phase(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    MOVING = "moving"
    STOPPING = "stopping"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class Reason(StrEnum):
    LINK_LOST = "link_lost"
    TIMEOUT = "timeout"
    NO_PROGRESS = "no_progress"
    REVERSE_MOTION = "reverse_motion"
    DESK_ERROR = "desk_error"
    OVERSHOOT = "overshoot"
    OUTSIDE_LIMITS = "outside_limits"
    STOP_FAILED = "stop_failed"
    PREPARATION_FAILED = "preparation_failed"
    UNKNOWN = "unknown"


class Source(StrEnum):
    """Who asked for the movement; a panel movement is only observed, never requested."""

    HOME_ASSISTANT = "home_assistant"
    PANEL = "panel"


ACTIVE = frozenset({Phase.PREPARING, Phase.MOVING, Phase.STOPPING})
SETTLED = frozenset({Phase.COMPLETED, Phase.INTERRUPTED, Phase.FAILED})


@dataclass(frozen=True)
class OperationStatus:
    """The latest operation; the height is what was requested, never a measurement."""

    phase: Phase = Phase.IDLE
    requested_height_cm: float | None = None
    reason: Reason | None = None
    source: Source = Source.HOME_ASSISTANT
    # The desk's own error frame, hex, never interpreted.
    error_code: str | None = None

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE

    @property
    def settled(self) -> bool:
        return self.phase in SETTLED

    def advanced(self, phase: Phase, reason: Reason | None = None) -> OperationStatus:
        """The same request in another phase; only a failure carries a reason."""
        return OperationStatus(phase, self.requested_height_cm, reason, self.source)

    def aimed_at(self, requested_height_cm: float) -> OperationStatus:
        return OperationStatus(
            self.phase, requested_height_cm, self.reason, self.source
        )


class OperationTracker:
    """Allowed phase changes for one explicit operation at a time.

    A change that is not allowed from the current phase is ignored, so repeated or
    late callers cannot rewrite a settled result. Rejected requests never reach the
    tracker: a refusal leaves the active operation and the last result untouched.
    """

    def __init__(
        self,
        changed: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._changed = changed
        self._clock = clock
        self._origin = Phase.IDLE
        self._fault_hold = False
        self._fault_cleared = False
        self._fault_at = 0.0
        self.status = OperationStatus()
        # The latest settled result, kept after the live phase returns to idle.
        self.last: OperationStatus | None = None

    @property
    def origin(self) -> Phase:
        """The phase the operation was in before its final Stop began.

        Cleanup announces `stopping` on every exit, so a failure raised while
        travelling must still be read as a travel failure, not a Stop failure.
        """
        if self.status.phase is Phase.STOPPING:
            return self._origin
        return self.status.phase

    def _publish(self, status: OperationStatus) -> None:
        if status != self.status:
            self.status = status
            if status.settled:
                self.last = status
            try:
                self._changed()
            except Exception:
                # Reporting must never alter a movement or its Stop.
                _LOGGER.debug("Operation status listener failed", exc_info=True)

    def reset(self) -> None:
        """Return a settled result to idle; the result stays as the last one."""
        if self.status.settled:
            # The fault hold is independent of this timer: a retreat that resumes
            # after the reset must still not replace the retained fault result.
            self._publish(OperationStatus())

    def begin(self, requested_height_cm: float | None = None) -> None:
        self._fault_hold = False
        self._fault_cleared = False
        # An explicit request outranks a movement that was only observed.
        if not self.status.active or self.status.source is Source.PANEL:
            self._publish(OperationStatus(Phase.PREPARING, requested_height_cm))

    def begin_panel(self) -> bool:
        """Observe a movement nobody requested here; never displaces a request."""
        if self.status.active:
            return False
        if self._fault_held():
            return False
        self._publish(OperationStatus(Phase.MOVING, source=Source.PANEL))
        return True

    def _fault_held(self) -> bool:
        """The desk backs away by itself after a fault, in several short runs.

        Its retreat must not replace the reported fault. The desk's "fault cleared"
        frame followed by stationary feedback ends the hold; a lost frame is
        recovered by a time limit.
        """
        if self._fault_hold and self._clock() - self._fault_at > FAULT_HOLD_MAX:
            self._fault_hold = False
            self._fault_cleared = False
        return self._fault_hold

    def request(self, requested_height_cm: float) -> None:
        """Record a goal that is only known after preparation reads it."""
        if self.status.active:
            self._publish(self.status.aimed_at(requested_height_cm))

    def moving(self) -> None:
        if self.status.phase is Phase.PREPARING:
            self._publish(self.status.advanced(Phase.MOVING))

    def stopping(self) -> None:
        if self.status.phase in (Phase.PREPARING, Phase.MOVING):
            self._origin = self.status.phase
            self._publish(self.status.advanced(Phase.STOPPING))

    def complete(self) -> None:
        self._settle(Phase.COMPLETED)

    def interrupt(self) -> None:
        self._settle(Phase.INTERRUPTED)

    def fail(self, reason: Reason) -> None:
        if self.status.active:
            self._publish(self.status.advanced(Phase.FAILED, reason))

    def desk_error(self, frame_hex: str) -> None:
        """The desk reported a fault frame itself, which is stronger than inference.

        The frame is kept as received; its meaning is not decoded. An explicit
        request keeps its own outcome and is never rewritten from here.
        """
        self._fault_hold = True
        self._fault_cleared = False
        self._fault_at = self._clock()
        if self.status.active and self.status.source is Source.HOME_ASSISTANT:
            return
        self._publish(
            OperationStatus(
                Phase.FAILED,
                None,
                Reason.DESK_ERROR,
                Source.PANEL,
                frame_hex,
            )
        )

    def fault_cleared(self) -> None:
        """The desk reported the fault over. Its retreat may still be running."""
        self._fault_cleared = True

    def stationary(self) -> None:
        """Feedback is stationary: a cleared fault no longer holds back movement."""
        if self._fault_hold and self._fault_cleared:
            self._fault_hold = False
            self._fault_cleared = False

    def drop_observed(self) -> None:
        """Forget a movement we only watched; it has no outcome of ours to report."""
        if self.status.active and self.status.source is Source.PANEL:
            self._publish(OperationStatus())

    def link_lost(self) -> None:
        if self.status.active and self.status.source is Source.PANEL:
            self.drop_observed()
            return
        self.fail(Reason.LINK_LOST)

    def stop_failed_while_idle(self) -> None:
        """Record a Stop that failed when no operation was active to carry the failure."""
        if not self.status.active or self.status.source is Source.PANEL:
            self._publish(OperationStatus(Phase.FAILED, None, Reason.STOP_FAILED))

    def _settle(self, phase: Phase) -> None:
        if self.status.active:
            self._publish(self.status.advanced(phase))


# Seconds of zero speed that settle a movement observed from the panel. A single
# stationary sample is not enough: the speed word is uninterpreted and a pause inside
# one movement has not been ruled out on hardware.
PANEL_SETTLE_DELAY = 1.0
# 1 mm in raw 0.1 mm units, matching the movement controller's tolerance.
PANEL_TOLERANCE_RAW = 10


class PanelMovementWatcher:
    """Follow a movement started on the desk panel and report it as an operation.

    Only measured position and the presence of speed are used. The direction is the
    one the position first travelled; the speed word's own direction and flags are
    uninterpreted. A turn back against that direction is reported as
    `reverse_motion`, which can be the desk's own anti-collision reversal but is
    inferred, never read from a panel error code.
    """

    def __init__(self, tracker: OperationTracker) -> None:
        self._tracker = tracker
        self._armed = False
        self._following = False
        self._start = 0
        self._best = 0
        self._direction = 0
        self._paused = False
        self._speed: int | None = None
        self._settle: asyncio.TimerHandle | None = None

    def observe(self, position_raw: int, speed_raw: int) -> None:
        self._speed = speed_raw
        if self._yields_to_request():
            return
        if speed_raw == 0:
            self._on_stationary(position_raw)
            return
        self._cancel_settle()
        if self._following:
            self._follow(position_raw, speed_raw)
        else:
            self._try_start(position_raw, speed_raw)

    def seed(self, speed_raw: int) -> None:
        """Start from a stationary reading taken before notifications were trusted."""
        status = self._tracker.status
        if speed_raw == 0 and not (status.active and status.source is not Source.PANEL):
            self._armed = True

    def _yields_to_request(self) -> bool:
        status = self._tracker.status
        observed = status.active and status.source is Source.PANEL
        if status.active and not observed:
            # An explicit request owns the desk; its residual speed is not a new move.
            self._drop(armed=False)
            return True
        if self._following and not observed:
            self._drop(armed=False)
        return False

    def _on_stationary(self, position_raw: int) -> None:
        self._tracker.stationary()
        self._armed = True
        if self._following:
            _LOGGER.debug("Panel movement stationary sample: position=%s", position_raw)
            self._paused = True
            self._schedule_settle()

    def _try_start(self, position_raw: int, speed_raw: int) -> None:
        if not (self._armed and self._tracker.begin_panel()):
            return
        _LOGGER.debug(
            "Panel movement started: position=%s speed=%s", position_raw, speed_raw
        )
        self._following = True
        self._paused = False
        self._start = self._best = position_raw
        self._direction = 0

    def _follow(self, position_raw: int, speed_raw: int) -> None:
        _LOGGER.debug(
            "Panel movement sample: position=%s speed=%s", position_raw, speed_raw
        )
        if self._paused:
            # Feedback went stationary and then moved again. The user may have
            # released the panel button and pressed the other direction, so the
            # direction is learned afresh rather than read as a turn back.
            self._paused = False
            self._start = self._best = position_raw
            self._direction = 0
        delta = position_raw - self._best
        if self._direction == 0:
            self._learn_direction(position_raw)
        elif delta * self._direction < -PANEL_TOLERANCE_RAW:
            self._reversed(position_raw)
        elif delta * self._direction > 0:
            self._best = position_raw

    def _learn_direction(self, position_raw: int) -> None:
        if abs(position_raw - self._start) > PANEL_TOLERANCE_RAW:
            self._direction = 1 if position_raw > self._start else -1
            self._best = position_raw

    def _reversed(self, position_raw: int) -> None:
        _LOGGER.debug(
            "Panel movement reversed: position=%s best=%s direction=%s",
            position_raw,
            self._best,
            self._direction,
        )
        self._tracker.fail(Reason.REVERSE_MOTION)
        self._drop(armed=False)

    def _schedule_settle(self) -> None:
        if self._settle is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._settle = loop.call_later(PANEL_SETTLE_DELAY, self._settled)

    def _settled(self) -> None:
        self._settle = None
        if not self._following:
            return
        status = self._tracker.status
        if status.active and status.source is Source.PANEL:
            _LOGGER.debug("Panel movement settled after stationary feedback")
            self._tracker.complete()
            self._drop(armed=True)
        else:
            # An explicit request took the operation over while the timer ran.
            self._drop(armed=False)

    def _cancel_settle(self) -> None:
        if self._settle is not None:
            self._settle.cancel()
            self._settle = None

    def _drop(self, *, armed: bool) -> None:
        self._cancel_settle()
        self._following = False
        self._paused = False
        self._armed = armed

    def fault_cleared(self) -> None:
        """The desk reported the fault over; hold on until its retreat has stopped."""
        self._tracker.fault_cleared()
        if self._speed == 0:
            self._tracker.stationary()

    def faulted(self) -> None:
        """The desk reported a fault: its own retreat is not a new movement.

        A fresh stationary sample is needed before another movement is followed,
        so the retreat cannot overwrite the reported fault.
        """
        self._drop(armed=False)

    def close(self) -> None:
        """Stop watching and forget an observed movement, whatever ended the session."""
        self._drop(armed=False)
        self._tracker.drop_observed()
