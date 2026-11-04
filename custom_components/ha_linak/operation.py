"""Status of the explicit desk operation, without Home Assistant or Bluetooth imports."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import logging

_LOGGER = logging.getLogger(__name__)

# Seconds a settled result stays visible before the status returns to idle. The
# result itself is kept as the last result, so only the live phase resets.
OPERATION_RESET_DELAY = 10


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
    OVERSHOOT = "overshoot"
    OUTSIDE_LIMITS = "outside_limits"
    STOP_FAILED = "stop_failed"
    PREPARATION_FAILED = "preparation_failed"
    UNKNOWN = "unknown"


ACTIVE = frozenset({Phase.PREPARING, Phase.MOVING, Phase.STOPPING})
SETTLED = frozenset({Phase.COMPLETED, Phase.INTERRUPTED, Phase.FAILED})


@dataclass(frozen=True)
class OperationStatus:
    """The latest operation; the height is what was requested, never a measurement."""

    phase: Phase = Phase.IDLE
    requested_height_cm: float | None = None
    reason: Reason | None = None

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE

    @property
    def settled(self) -> bool:
        return self.phase in SETTLED

    def advanced(self, phase: Phase, reason: Reason | None = None) -> OperationStatus:
        """The same request in another phase; only a failure carries a reason."""
        return OperationStatus(phase, self.requested_height_cm, reason)

    def aimed_at(self, requested_height_cm: float) -> OperationStatus:
        return OperationStatus(self.phase, requested_height_cm, self.reason)


class OperationTracker:
    """Allowed phase changes for one explicit operation at a time.

    A change that is not allowed from the current phase is ignored, so repeated or
    late callers cannot rewrite a settled result. Rejected requests never reach the
    tracker: a refusal leaves the active operation and the last result untouched.
    """

    def __init__(self, changed: Callable[[], None]) -> None:
        self._changed = changed
        self._origin = Phase.IDLE
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
            self._publish(OperationStatus())

    def begin(self, requested_height_cm: float | None = None) -> None:
        if not self.status.active:
            self._publish(OperationStatus(Phase.PREPARING, requested_height_cm))

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

    def link_lost(self) -> None:
        self.fail(Reason.LINK_LOST)

    def stop_failed_while_idle(self) -> None:
        """Record a Stop that failed when no operation was active to carry the failure."""
        if not self.status.active:
            self._publish(OperationStatus(Phase.FAILED, None, Reason.STOP_FAILED))

    def _settle(self, phase: Phase) -> None:
        if self.status.active:
            self._publish(self.status.advanced(phase))
