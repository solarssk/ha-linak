"""Pure protocol helpers; no Bluetooth operations or movement commands."""

from dataclasses import dataclass
from enum import IntEnum
import struct

SERVICE_UUID = "99fa0001-338a-1024-8a49-009c0215f78a"
DPG_UUID = "99fa0011-338a-1024-8a49-009c0215f78a"
HEIGHT_UUID = "99fa0021-338a-1024-8a49-009c0215f78a"


class ReadCommand(IntEnum):
    """Extended read commands verified on the initial DPG1C."""

    CAPABILITIES = 0x80
    OFFSET = 0x81
    REMINDERS = 0x88
    MEMORY_1 = 0x89
    MEMORY_2 = 0x8A
    MEMORY_3 = 0x8B
    MEMORY_4 = 0x8C


def read_request(command: ReadCommand) -> bytes:
    """Encode only an allowlisted query; this still needs a GATT write."""
    if not isinstance(command, ReadCommand):
        raise ValueError("Only documented research read commands are allowed")
    return bytes((0x7F, command.value, 0x00))


@dataclass(frozen=True)
class PositionSample:
    """Raw words, preserving flags until their interpretation is verified."""

    position_raw: int
    speed_raw: int

    def height_m(self, base_height_m: float) -> float:
        """Convert relative 0.1 mm position using an explicitly supplied datum."""
        return base_height_m + self.position_raw / 10_000


def decode_position(payload: bytes) -> PositionSample:
    """Reject malformed frames instead of publishing misleading readings."""
    if len(payload) != 4:
        raise ValueError("Position sample must contain exactly four bytes")
    return PositionSample(*struct.unpack("<HH", payload))


def _frame(payload: bytes, response_type: int, length: int) -> None:
    if len(payload) != length or payload[:2] != bytes((1, response_type)):
        raise ValueError("Unexpected DPG response type or length")


@dataclass(frozen=True)
class Capabilities:
    memory_slots: int
    automatic_up: bool
    automatic_down: bool
    bluetooth: bool
    display: bool
    light: bool
    references_raw: int
    flags_raw: int


def decode_capabilities(payload: bytes) -> Capabilities:
    _frame(payload, 2, 4)
    flags, references = payload[2:]
    return Capabilities(
        flags & 7,
        bool(flags & 8),
        bool(flags & 16),
        bool(flags & 32),
        bool(flags & 64),
        bool(flags & 128),
        references,
        flags,
    )


@dataclass(frozen=True)
class StoredPosition:
    position_raw: int | None
    counter_raw: int


def decode_stored_position(payload: bytes) -> StoredPosition:
    if len(payload) < 3 or payload[:2] != b"\x01\x07":
        raise ValueError("Unexpected memory response")
    if payload[2] == 1:
        _frame(payload, 7, 9)
        position, counter = struct.unpack("<HI", payload[3:])
        return StoredPosition(position, counter)
    if payload[2] == 0:
        _frame(payload, 7, 7)
        return StoredPosition(None, struct.unpack("<I", payload[3:])[0])
    raise ValueError("Unknown memory validity flag")


def decode_offset(payload: bytes) -> int | None:
    _frame(payload, 3, 5)
    if payload[2] not in (0, 1):
        raise ValueError("Unknown offset validity flag")
    return struct.unpack("<H", payload[3:])[0] if payload[2] else None


@dataclass(frozen=True)
class ReminderSettings:
    flags_raw: int
    profiles_raw: tuple[tuple[int, int], ...]
    counter_raw: int

    @property
    def selected_profile(self) -> int:
        return self.flags_raw & 3


def decode_reminders(payload: bytes) -> ReminderSettings:
    _frame(payload, 11, 13)
    return ReminderSettings(
        payload[2],
        tuple((payload[i], payload[i + 1]) for i in (3, 5, 7)),
        struct.unpack("<I", payload[9:13])[0],
    )
