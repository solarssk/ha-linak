"""Deterministic DPG reply scheduling for synthetic desk sessions.

ReplayBleak answers each extended read by its position in the request sequence and
injects extra frames at the two points where the client can observe them: while a
request is pending and right after its genuine reply. No await separates one query's
cleanup from the next query's reservation, so the client has no other observable state.
"""

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from enum import IntEnum
import struct
from unittest.mock import patch

from bleak.backends.device import BLEDevice
import pytest

from custom_components.ha_linak.client import DeskClient, DeskState
from custom_components.ha_linak.protocol import (
    DPG_UUID,
    StoredPosition,
    decode_capabilities,
    decode_offset,
    decode_position,
    decode_reminders,
    decode_stored_position,
)
from test_client import FakeBleak

REFRESH = (0x80, 0x81, 0x89, 0x80, 0x8A, 0x80, 0x8B, 0x80, 0x8C, 0x88)
HEIGHT_FRAME = bytes.fromhex("9e050000")


class Position(IntEnum):
    """Index of a request in a complete refresh, plus its final height read."""

    CAPABILITIES = 0
    OFFSET = 1
    SLOT1 = 2
    BARRIER1 = 3
    SLOT2 = 4
    BARRIER2 = 5
    SLOT3 = 6
    BARRIER3 = 7
    SLOT4 = 8
    REMINDERS = 9
    POSITION_READ = 10


def capabilities_frame(references: int = 1) -> bytes:
    return bytes((1, 2, 0xFC, references))


def offset_frame(raw: int = 6800) -> bytes:
    return b"\x01\x03\x01" + struct.pack("<H", raw)


def memory_frame(position_raw: int | None, counter: int) -> bytes:
    if position_raw is None:
        return b"\x01\x07\x00" + struct.pack("<I", counter)
    return b"\x01\x07\x01" + struct.pack("<HI", position_raw, counter)


def reminders_frame(sitting: int = 55) -> bytes:
    return bytes((1, 11, 0x3B, sitting, 50, 10, 45, 15, 235)) + struct.pack("<I", 4352)


SLOTS_A = (
    memory_frame(1100, 11),
    memory_frame(1200, 22),
    memory_frame(None, 33),
    memory_frame(1400, 44),
)
SLOTS_B = (
    memory_frame(1150, 55),
    memory_frame(1250, 66),
    memory_frame(1350, 77),
    memory_frame(None, 88),
)


def default_replies(
    slots: Sequence[bytes] = SLOTS_A,
    *,
    offset: int = 6800,
    references: int = 1,
    sitting: int = 55,
) -> dict[int, bytes]:
    replies = {
        0x80: capabilities_frame(references),
        0x81: offset_frame(offset),
        0x88: reminders_frame(sitting),
    }
    replies.update(zip(range(0x89, 0x8D), slots, strict=True))
    return replies


class ReplayBleak(FakeBleak):
    """Answer extended reads by request position and inject scripted frames.

    A script can inject frames before or after the genuine reply at a position,
    replace that reply, or fail it. Failures: "silent" never answers, "link_loss"
    loses the link while the request is outstanding, and "reply_then_loss" delivers
    the reply and the link loss in the same loop turn.
    """

    def __init__(self, replies: Mapping[int, bytes] | None = None) -> None:
        super().__init__()
        self.replies = dict(default_replies() if replies is None else replies)
        self.disconnected_callback = None
        self.stalled = asyncio.Event()
        self.stalled_reply: bytes | None = None
        self.read_gate = asyncio.Event()
        self.link_lost = False
        self.script()

    def script(
        self,
        *,
        before: Mapping[int, Sequence[bytes]] | None = None,
        after: Mapping[int, Sequence[bytes]] | None = None,
        replace: Mapping[int, bytes] | None = None,
        failures: Mapping[int, str] | None = None,
    ) -> None:
        """Start a request sequence; positions count from the next request."""
        self.before = before or {}
        self.after = after or {}
        self.replace = replace or {}
        self.failures = failures or {}
        self.position = 0

    def deliver(self, frames: Iterable[bytes]) -> None:
        for frame in frames:
            self.callbacks[DPG_UUID](None, bytearray(frame))

    def lose_link(self) -> None:
        self.link_lost = True
        self.is_connected = False
        assert self.disconnected_callback is not None
        self.disconnected_callback(self)

    def lose_link_soon(self) -> None:
        asyncio.get_running_loop().call_soon(self.lose_link)

    @property
    def failure_fired(self) -> bool:
        """True once a scripted stall or link loss actually happened."""
        return self.stalled.is_set() or self.link_lost

    def release(self) -> None:
        """Answer the request or read that a silent failure left waiting."""
        if self.stalled_reply is not None:
            self.deliver((self.stalled_reply,))
        self.read_gate.set()

    def expected_state(self) -> DeskState:
        return DeskState(
            position=decode_position(HEIGHT_FRAME),
            offset_raw=decode_offset(self.replies[0x81]),
            capabilities=decode_capabilities(self.replies[0x80]),
            memories=[
                decode_stored_position(self.replies[c]) for c in range(0x89, 0x8D)
            ],
            reminders=decode_reminders(self.replies[0x88]),
        )

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == DPG_UUID and data[0] == 0x7F and data[2] == 0
        position = self.position
        self.position += 1
        self.writes.append((uuid, bytes(data)))
        self.deliver(self.before.get(position, ()))
        reply = self.replace.get(position, self.replies[data[1]])
        failure = self.failures.get(position)
        if failure == "silent":
            self.stalled_reply = reply
            self.stalled.set()
            return
        if failure == "link_loss":
            self.lose_link_soon()
            return
        self.deliver((reply,))
        self.deliver(self.after.get(position, ()))
        if failure == "reply_then_loss":
            self.lose_link_soon()

    async def read_gatt_char(self, uuid):
        self.deliver(self.before.get(Position.POSITION_READ, ()))
        failure = self.failures.get(Position.POSITION_READ)
        if failure == "silent":
            self.stalled.set()
        elif failure == "link_loss":
            self.lose_link_soon()
        if failure in ("silent", "link_loss"):
            await self.read_gate.wait()
        value = await super().read_gatt_char(uuid)
        if failure == "reply_then_loss":
            self.lose_link_soon()
        return value


@contextmanager
def connections(*fakes: ReplayBleak):
    """Hand out each fake once and expose the disconnect callback it was given."""
    queue = list(fakes)

    async def connect(*_args, **kwargs):
        fake = queue.pop(0)
        fake.disconnected_callback = kwargs["disconnected_callback"]
        return fake

    with patch(
        "custom_components.ha_linak.client.establish_connection", side_effect=connect
    ):
        yield


def new_desk(changes: list[bool] | None = None) -> DeskClient:
    sink = [] if changes is None else changes
    return DeskClient(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: sink.append(True)
    )


def sent_commands(fake: FakeBleak) -> list[int]:
    return [data[1] for uuid, data in fake.writes if uuid == DPG_UUID]


def decoded(frames: Iterable[bytes]) -> list[StoredPosition]:
    return [decode_stored_position(frame) for frame in frames]


async def expect_failure(call, error: type[BaseException], seconds: float = 2.0):
    """Require the client's own failure; a watchdog expiry is not a pass."""
    with pytest.raises(error):
        async with asyncio.timeout(seconds) as watchdog:
            await call
    assert not watchdog.expired(), "client waited instead of failing"
