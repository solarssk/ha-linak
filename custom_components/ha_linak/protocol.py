"""Pure protocol helpers; no Bluetooth operations or movement commands."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum
import struct

SERVICE_UUID = "99fa0001-338a-1024-8a49-009c0215f78a"
DPG_UUID = "99fa0011-338a-1024-8a49-009c0215f78a"
HEIGHT_UUID = "99fa0021-338a-1024-8a49-009c0215f78a"
DISPLAY_HALF_STEP_RAW = 5  # Half a 1 mm display step, in 0.1 mm wire units.
REFERENCE_INVENTORY_UUIDS = (
    HEIGHT_UUID,
    "99fa0029-338a-1024-8a49-009c0215f78a",
    "99fa002a-338a-1024-8a49-009c0215f78a",
) + tuple(f"99fa002{i}-338a-1024-8a49-009c0215f78a" for i in range(2, 9))
type ResearchValue = (
    dict[str, ResearchValue] | list[ResearchValue] | str | int | float | bool | None
)


class ResearchSection(StrEnum):
    """Fixed explicit reads, never arbitrary opcodes or setting writes."""

    REFERENCE_OUTPUTS = "reference_outputs"
    PRODUCT_INFO = "product_info"


def research_product_reply(payload: bytes) -> bytes | None:
    """Bound a raw research reply without assigning product/firmware semantics."""
    if not 2 <= len(payload) <= 512 or payload[0] != 1:
        raise ValueError("Invalid research response framing")
    if payload[:2] == b"\x01\x11":
        raise ValueError("Client identity is not a product research response")
    if len(payload) == 2:
        if payload != b"\x01\x00":
            raise ValueError("Unexpected research response status")
        return None
    return payload


class ReadCommand(IntEnum):
    """Extended read commands verified on the initial DPG1C."""

    CAPABILITIES = 0x80
    OFFSET = 0x81
    REMINDERS = 0x88
    MEMORY_1 = 0x89
    MEMORY_2 = 0x8A
    MEMORY_3 = 0x8B
    MEMORY_4 = 0x8C
    USER_ID = 0x86


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


class PositionUnavailable(ValueError):
    """The position word cannot be used as a height measurement."""


def decode_position(payload: bytes) -> PositionSample:
    """Reject malformed frames instead of publishing misleading readings."""
    if len(payload) != 4:
        raise ValueError("Position sample must contain exactly four bytes")
    position, speed = struct.unpack("<HH", payload)
    if position == 0xFFFF:
        raise PositionUnavailable("Desk position is unavailable")
    return PositionSample(position, speed)


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

    @property
    def inch_preference(self) -> bool:
        """Stored preference only; clear does not distinguish physical CM/MM."""
        return bool(self.flags_raw & 0x04)


def decode_reminders(payload: bytes) -> ReminderSettings:
    _frame(payload, 11, 13)
    return ReminderSettings(
        payload[2],
        tuple((payload[i], payload[i + 1]) for i in (3, 5, 7)),
        struct.unpack("<I", payload[9:13])[0],
    )


def reminder_request(settings: ReminderSettings) -> bytes:
    """Encode the complete seven-byte body, excluding the uninterpreted counter."""
    if len(settings.profiles_raw) != 3 or any(
        len(pair) != 2 for pair in settings.profiles_raw
    ):
        raise ValueError("Reminder settings require exactly three interval pairs")
    body = bytes((settings.flags_raw,)) + bytes(
        value for pair in settings.profiles_raw for value in pair
    )
    return b"\x7f\x88\x80" + body


def reminder_profile_request(settings: ReminderSettings, profile: int) -> bytes:
    """Assign the profile, preserving every unrelated flag and interval byte."""
    if type(profile) is not int or profile not in range(4):
        raise ValueError("Reminder profile must be 0, 1, 2 or 3")
    request = bytearray(reminder_request(settings))
    request[3] = (request[3] & ~3) | profile
    return bytes(request)


def reminder_sitting_request(settings: ReminderSettings, minutes: int) -> bytes:
    """Keep the original profile 1 sitting assignment."""
    return reminder_interval_request(settings, 1, False, minutes)


def reminder_interval_index(profile: int, standing: bool) -> int:
    """Validate a field address and return its zero-based duration byte index."""
    if type(profile) is not int or profile not in range(1, 4):
        raise ValueError("Reminder interval profile must be 1, 2 or 3")
    if type(standing) is not bool:
        raise ValueError("Reminder standing selector must be a boolean")
    return (profile - 1) * 2 + int(standing)


def reminder_interval_request(
    settings: ReminderSettings, profile: int, standing: bool, minutes: int
) -> bytes:
    """Replace one duration byte; host input policy is separate."""
    index = reminder_interval_index(profile, standing)
    if type(minutes) is not int or not 0 <= minutes <= 255:
        raise ValueError("Reminder duration must fit one byte")
    request = bytearray(reminder_request(settings))
    request[4 + index] = minutes
    return bytes(request)


def reminder_unit_request(settings: ReminderSettings, inch: bool) -> bytes:
    """Change only the evidenced inch flag, preserving the complete other body."""
    if type(inch) is not bool:
        raise ValueError("Panel inch preference must be a boolean")
    request = bytearray(reminder_request(settings))
    request[3] = (request[3] & ~0x04) | (0x04 if inch else 0)
    return bytes(request)


class ReminderClientInactive(ValueError):
    """Reminder writes require observed status 1; never activate implicitly."""


def activation_request(payload: bytes) -> bytes | None:
    """Activate the existing identity only; never generate or replace its bytes."""
    _frame(payload, 17, 19)
    if (
        payload[2] not in (0, 1)
        or not any(payload[3:])
        or all(b == 255 for b in payload[3:])
    ):
        raise ValueError("Unsupported client identity")
    if payload[2] == 1:
        return None
    return b"\x7f\x86\x80\x01" + payload[3:]
