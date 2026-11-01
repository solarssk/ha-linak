"""Explicit host-side movement bounds; never programs firmware settings."""

from dataclasses import dataclass
import math
from typing import Any

from .motion import TravelLimits, DISPLAY_HALF_STEP_RAW

MINIMUM_HEIGHT = "minimum_height"
MAXIMUM_HEIGHT = "maximum_height"


@dataclass(frozen=True)
class ControlSettings:
    minimum_cm: float
    maximum_cm: float

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> ControlSettings | None:
        if MINIMUM_HEIGHT not in options and MAXIMUM_HEIGHT not in options:
            return None
        minimum = _height(options.get(MINIMUM_HEIGHT))
        maximum = _height(options.get(MAXIMUM_HEIGHT))
        if not 0 <= minimum < maximum or maximum - minimum > 655.34:
            raise ValueError("Measured height bounds are invalid")
        return cls(float(minimum), float(maximum))

    def limits(self, offset_raw: int) -> TravelLimits:
        minimum = round(self.minimum_cm * 100) - offset_raw
        # A 1 mm UI value can round just below the zero wire position after
        # calibration. This is display rounding, not an inferred travel limit.
        if -DISPLAY_HALF_STEP_RAW <= minimum < 0:
            minimum = 0
        return TravelLimits(
            minimum,
            round(self.maximum_cm * 100) - offset_raw,
        )


def _height(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("Finite measured height bounds are required")
    return float(value)
