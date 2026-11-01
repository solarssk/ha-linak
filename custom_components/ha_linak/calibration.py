"""Measured-height calibration planning, separate from firmware transport."""

from dataclasses import dataclass
import math
import struct

from .protocol import DISPLAY_HALF_STEP_RAW, PositionSample

MEASURED_HEIGHT = "measured_height"


class InvalidMeasurement(ValueError):
    """The measurement cannot calibrate the current stationary snapshot."""


@dataclass(frozen=True)
class HeightCalibration:
    old_offset_raw: int
    position_raw: int
    new_offset_raw: int

    def __post_init__(self) -> None:
        for value in (self.old_offset_raw, self.position_raw, self.new_offset_raw):
            if type(value) is not int or not 0 <= value < 0xFFFF:
                raise ValueError("Calibration requires valid unsigned position words")

    @classmethod
    def prepare(
        cls, position: PositionSample | None, offset_raw: int | None, measured_cm: float
    ) -> HeightCalibration:
        if (
            position is None
            or position.speed_raw != 0
            or offset_raw is None
            or isinstance(measured_cm, bool)
            or not isinstance(measured_cm, (int, float))
            or not math.isfinite(measured_cm)
            or measured_cm <= 0
        ):
            raise InvalidMeasurement(
                "Measure a stationary desk with a valid current reading"
            )
        if measured_cm > (0xFFFE + position.position_raw) / 100:
            raise InvalidMeasurement("Measurement is outside the reference encoding")
        reference = round(measured_cm * 100) - position.position_raw
        if abs(reference - offset_raw) <= DISPLAY_HALF_STEP_RAW:
            reference = offset_raw
        try:
            return cls(offset_raw, position.position_raw, reference)
        except ValueError as err:
            raise InvalidMeasurement(
                "Measurement is outside the reference encoding"
            ) from err

    @property
    def changed(self) -> bool:
        return self.old_offset_raw != self.new_offset_raw

    @property
    def measured_cm(self) -> float:
        return (self.position_raw + self.new_offset_raw) / 100

    def write_request(self) -> bytes:
        """Only the DPG offset setting: command 81, validity byte 1, LE uint16."""
        return b"\x7f\x81\x80\x01" + struct.pack("<H", self.new_offset_raw)
