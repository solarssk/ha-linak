"""Device identity and driver selection, independent of HA and BLE operations."""

from dataclasses import asdict, dataclass
from enum import StrEnum
import re

MODEL_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID = "00002a26-0000-1000-8000-00805f9b34fb"


class Family(StrEnum):
    UNKNOWN = "unknown"
    DPG = "dpg"
    DPI = "dpi"
    OTHER = "other"


class UnsupportedFamily(ValueError):
    """An identified product has no implemented driver in this integration."""


def metadata_text(raw: bytes) -> str | None:
    """Decode bounded standard metadata without trusting arbitrary BLE strings."""
    if len(raw) > 64:
        return None
    try:
        value = raw.decode("utf-8").strip("\x00 \t\r\n")
    except UnicodeDecodeError:
        return None
    return value if value and value.isprintable() else None


@dataclass(frozen=True)
class DeviceIdentity:
    """Retain only recognized product models and version-shaped firmware."""

    family: Family = Family.UNKNOWN
    model: str | None = None
    firmware: str | None = None

    @classmethod
    def from_metadata(cls, model: bytes, firmware: bytes) -> "DeviceIdentity":
        text = metadata_text(model)
        family = Family.UNKNOWN
        recognized = None
        if text is not None:
            candidate = text.upper()
            match = re.fullmatch(
                r"(DP[GI](?:[1-9][A-Z])?)(?:-?[0-9][A-Z0-9-]*)?", candidate
            )
            if match:
                # A numeric ordering suffix is not part of the model exposed to HA.
                recognized = match[1]
                family = Family.DPG if candidate.startswith("DPG") else Family.DPI
            else:
                family = Family.OTHER
        version = metadata_text(firmware)
        if version is not None and not re.fullmatch(
            r"[vV]?\d{1,5}(?:[._-]\d{1,5}){1,4}", version
        ):
            version = None
        return cls(family, recognized, version)

    def require_driver(self) -> None:
        """Missing identity may use protocol probing; another family may not."""
        if self.family in (Family.DPI, Family.OTHER):
            raise UnsupportedFamily("No driver for the identified product family")

    def diagnostics(self, protocol_validated: bool) -> dict[str, object]:
        return {
            **asdict(self),
            "identity_source": "device_information"
            if self.family is not Family.UNKNOWN
            else "not_available",
            "driver": "dpg" if protocol_validated else None,
            "protocol_validated": protocol_validated,
            "hardware_validation": "not_inferred",
        }
