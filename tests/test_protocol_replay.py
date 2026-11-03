"""Replay duplicate, late and lost DPG replies against the serialized client.

Memory replies carry no slot number, so correlation relies on request order, the
response type and discarding any session whose assignment became ambiguous. These
cases fix which stale-frame arrivals that design absorbs and which it cannot, using
synthetic frames only. See docs/protocol.md, "Correlate replies and reject ambiguity".
"""

import asyncio
from contextlib import nullcontext
from dataclasses import replace
from unittest.mock import patch

import pytest

from custom_components.ha_linak.client import DeskLinkLost
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID
from replay_transport import (
    REFRESH,
    SLOTS_A,
    SLOTS_B,
    Position,
    ReplayBleak,
    capabilities_frame,
    connections,
    decoded,
    default_replies,
    expect_failure,
    new_desk,
    offset_frame,
    sent_commands,
)

BURST = 24
RESPONSE_TYPES = {0x80: 2, 0x81: 3, 0x88: 11, 0x89: 7, 0x8A: 7, 0x8B: 7, 0x8C: 7}
S1, S2, S3, S4 = SLOTS_A
CAPABILITIES = capabilities_frame()
OFFSET = offset_frame()
REQUESTS = [position for position in Position if position != Position.POSITION_READ]
STALE_HEIGHT = bytearray(b"\x00\x00\x00\x00")
OLD = default_replies(SLOTS_A)
NEW = default_replies(SLOTS_B, offset=7000, references=2, sitting=30)


def position_id(position):
    return position.name.lower()


def snapshot(desk):
    return replace(desk.state, memories=list(desk.state.memories))


def assert_refreshed(desk, fake):
    assert sent_commands(fake) == list(REFRESH)
    assert desk.state == fake.expected_state()
    assert desk.connected
    assert all(health.valid for health in desk.settings_health.values())


async def test_refresh_never_sends_consecutive_requests_with_one_response_type():
    fake = ReplayBleak()
    desk = new_desk()
    with connections(fake):
        await desk.refresh()
    sent = sent_commands(fake)
    types = [RESPONSE_TYPES[command] for command in sent]
    assert sent == list(REFRESH)
    assert all(left != right for left, right in zip(types, types[1:]))
    await desk.disconnect()


@pytest.mark.parametrize("arrival", ["right_after_reply", "during_next_request"])
@pytest.mark.parametrize("position", REQUESTS, ids=position_id)
async def test_copies_of_any_reply_never_complete_another_query(position, arrival):
    fake = ReplayBleak()
    copies = [fake.replies[REFRESH[position]]] * BURST
    if arrival == "right_after_reply":
        fake.script(after={position: copies})
    else:
        fake.script(before={position + 1: copies})
    desk = new_desk()
    with connections(fake):
        await desk.refresh()
    assert_refreshed(desk, fake)
    await desk.disconnect()


DEFENDED = {
    "older_slot_copies_while_a_barrier_is_pending": {
        "before": {Position.BARRIER2: [S1] * 3 + [S2] * 3}
    },
    "older_slot_copies_after_the_next_slot_reply": {
        "after": {Position.SLOT3: [S1] * 3 + [S2] * 3}
    },
    "slot_copies_while_reminders_are_pending": {
        "before": {Position.REMINDERS: [S1, S2, S3, S4]}
    },
    "slot_copies_during_the_height_read": {
        "before": {Position.POSITION_READ: [S1, S2, S3, S4]}
    },
    "barrier_copies_while_a_slot_is_pending": {
        "before": {
            Position.SLOT2: [CAPABILITIES] * 3,
            Position.SLOT3: [CAPABILITIES] * 3,
            Position.SLOT4: [CAPABILITIES] * 3,
        }
    },
    "offset_and_barrier_copies_while_the_first_slot_is_pending": {
        "before": {Position.SLOT1: [OFFSET, CAPABILITIES]}
    },
}


@pytest.mark.parametrize("script", DEFENDED.values(), ids=list(DEFENDED))
async def test_stale_frames_without_a_matching_pending_request_are_ignored(script):
    fake = ReplayBleak()
    fake.script(**script)
    desk = new_desk()
    with connections(fake):
        await desk.refresh()
    assert_refreshed(desk, fake)
    await desk.disconnect()


async def test_known_limit_late_slot_copy_is_accepted_for_the_next_slot():
    """Characterizes a protocol limit, not a defence.

    A type 07 frame that arrives while a slot request is pending looks exactly like
    that slot's own reply. The genuine reply is then dropped and nothing on the wire
    reveals the mix-up. If a mitigation lands, change this test with docs/protocol.md.
    """
    fake = ReplayBleak()
    fake.script(before={Position.SLOT2: [S1]})
    desk = new_desk()
    with connections(fake):
        state = await desk.refresh()
    assert sent_commands(fake) == list(REFRESH)
    assert state.memories == decoded([S1, S1, S3, S4])
    assert desk.connected
    await desk.disconnect()


async def test_known_limit_late_slot_copy_can_populate_an_empty_slot():
    """Same limit with a 9-byte stale frame answering an empty slot's 7-byte reply."""
    fake = ReplayBleak()
    fake.script(before={Position.SLOT3: [S2]})
    desk = new_desk()
    with connections(fake):
        state = await desk.refresh()
    assert state.memories == decoded([S1, S2, S2, S4])
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize("position", REQUESTS, ids=position_id)
async def test_old_generation_frames_cannot_complete_the_new_generations_query(
    position,
):
    old, new = ReplayBleak(OLD), ReplayBleak(NEW)
    changes = []
    desk = new_desk(changes)
    with connections(old, new):
        await desk.refresh()
        previous = snapshot(desk)
        stale_dpg = old.callbacks[DPG_UUID]
        stale_height = old.callbacks[HEIGHT_UUID]
        await desk.disconnect()
        published = len(changes)
        new.script(failures={position: "silent"})
        refresh = asyncio.create_task(desk.refresh())
        try:
            async with asyncio.timeout(2):
                await new.stalled.wait()
            stale_dpg(None, bytearray(OLD[REFRESH[position]]))
            stale_height(None, STALE_HEIGHT)
            assert desk.state == previous
            new.release()
            await refresh
        finally:
            refresh.cancel()
            await asyncio.gather(refresh, return_exceptions=True)
    assert desk.state == new.expected_state()
    assert len(changes) == published
    await desk.disconnect()


async def test_old_disconnect_callback_cannot_tear_down_the_new_session():
    old, new = ReplayBleak(OLD), ReplayBleak(NEW)
    changes = []
    desk = new_desk(changes)
    with connections(old, new):
        await desk.refresh()
        await desk.disconnect()
        await desk.refresh()
        published = len(changes)
        old.disconnected_callback(old)
        await asyncio.sleep(0)
    assert desk.connected
    assert len(changes) == published
    assert all(health.valid for health in desk.settings_health.values())
    assert desk.state == new.expected_state()
    await desk.disconnect()


FAILURES = {
    "link_loss": ("link_loss", DeskLinkLost),
    "reply_then_loss": ("reply_then_loss", DeskLinkLost),
    "timeout": ("silent", TimeoutError),
}


@pytest.mark.parametrize(
    "ready_link", [False, True], ids=["first_connection", "ready_link"]
)
@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("position", list(Position), ids=position_id)
async def test_failure_at_any_position_discards_the_session_and_promotes_nothing(
    position, failure, ready_link
):
    mode, error = FAILURES[failure]
    changes = []
    desk = new_desk(changes)
    failing = ReplayBleak(OLD)
    recovered = ReplayBleak(default_replies(SLOTS_B, sitting=30))
    short_timeouts = (
        patch.multiple(
            "custom_components.ha_linak.client", QUERY_TIMEOUT=0.05, IO_TIMEOUT=0.05
        )
        if failure == "timeout"
        else nullcontext()
    )
    with connections(failing, recovered):
        if ready_link:
            await desk.refresh()
        previous = snapshot(desk)
        original = desk.state
        failing.script(failures={position: mode})
        with short_timeouts:
            await expect_failure(desk.refresh(allow_partial_settings=ready_link), error)
        assert failing.failure_fired
        assert desk.client is None
        assert not desk.connected
        assert not any(health.valid for health in desk.settings_health.values())
        assert desk.state is original
        assert desk.state == previous
        published = len(changes)
        late = failing.replies[REFRESH[min(position, Position.REMINDERS)]]
        failing.callbacks[DPG_UUID](None, bytearray(late))
        failing.callbacks[HEIGHT_UUID](None, STALE_HEIGHT)
        assert desk.state == previous
        assert len(changes) == published

        state = await desk.refresh(allow_partial_settings=True, settings_interval=300)
        assert sent_commands(recovered) == list(REFRESH)
        assert state is desk.state
        assert state == recovered.expected_state()
        assert desk.connected
        assert all(health.valid for health in desk.settings_health.values())
        failing.callbacks[DPG_UUID](None, bytearray(late))
        failing.callbacks[HEIGHT_UUID](None, STALE_HEIGHT)
        assert desk.state == recovered.expected_state()
    await desk.disconnect()


@pytest.mark.parametrize(
    "position",
    [
        Position.SLOT2,
        Position.SLOT3,
        Position.SLOT4,
        Position.REMINDERS,
        Position.POSITION_READ,
    ],
    ids=position_id,
)
async def test_in_flight_refresh_publishes_nothing_until_it_completes(position):
    first, second = ReplayBleak(OLD), ReplayBleak(NEW)
    changes = []
    desk = new_desk(changes)
    with connections(first, second):
        await desk.refresh()
        previous = snapshot(desk)
        await desk.disconnect()
        published = len(changes)
        second.script(failures={position: "silent"})
        refresh = asyncio.create_task(desk.refresh())
        try:
            async with asyncio.timeout(2):
                await second.stalled.wait()
            assert desk.state == previous
            assert not desk.connected
            assert not any(health.valid for health in desk.settings_health.values())
            assert len(changes) == published
            second.release()
            state = await refresh
        finally:
            refresh.cancel()
            await asyncio.gather(refresh, return_exceptions=True)
    assert state is desk.state
    assert state == second.expected_state()
    assert desk.connected
    assert all(health.valid for health in desk.settings_health.values())
    await desk.disconnect()


@pytest.mark.parametrize(
    "position", [Position.SLOT2, Position.REMINDERS], ids=position_id
)
async def test_in_flight_refresh_on_a_ready_link_updates_only_the_height(position):
    fake = ReplayBleak(OLD)
    changes = []
    desk = new_desk(changes)
    with connections(fake):
        await desk.refresh()
        previous = snapshot(desk)
        published = len(changes)
        fake.script(failures={position: "silent"})
        refresh = asyncio.create_task(desk.refresh(allow_partial_settings=True))
        try:
            async with asyncio.timeout(2):
                await fake.stalled.wait()
            fake.callbacks[HEIGHT_UUID](None, bytearray.fromhex("e8030000"))
            assert len(changes) == published + 1
            assert desk.state.position.position_raw == 1000
            assert replace(desk.state, position=previous.position) == previous
            assert desk.connected
            assert all(health.valid for health in desk.settings_health.values())
            fake.release()
            await refresh
        finally:
            refresh.cancel()
            await asyncio.gather(refresh, return_exceptions=True)
    assert desk.state == fake.expected_state()
    await desk.disconnect()


REQUIRED_POSITIONS = [
    Position.CAPABILITIES,
    Position.OFFSET,
    Position.BARRIER1,
    Position.BARRIER2,
    Position.BARRIER3,
]
OPTIONAL_GROUPS = {
    Position.SLOT1: "memories",
    Position.SLOT2: "memories",
    Position.SLOT3: "memories",
    Position.SLOT4: "memories",
    Position.REMINDERS: "reminders",
}
MEMORY_REREAD = [0x89, 0x80, 0x8A, 0x80, 0x8B, 0x80, 0x8C]


def truncated(fake, position):
    return fake.replies[REFRESH[position]][:-1]


@pytest.mark.parametrize(
    "ready_link", [False, True], ids=["first_connection", "ready_link"]
)
@pytest.mark.parametrize("position", REQUIRED_POSITIONS, ids=position_id)
async def test_malformed_required_reply_discards_the_session_in_every_mode(
    position, ready_link
):
    fake = ReplayBleak(OLD)
    desk = new_desk()
    with connections(fake):
        if ready_link:
            await desk.refresh()
        previous = snapshot(desk)
        fake.script(replace={position: truncated(fake, position)})
        await expect_failure(
            desk.refresh(allow_partial_settings=ready_link), ValueError
        )
    assert desk.client is None
    assert not desk.connected
    assert not any(health.valid for health in desk.settings_health.values())
    assert desk.state == previous
    await desk.disconnect()


@pytest.mark.parametrize("position", list(OPTIONAL_GROUPS), ids=position_id)
async def test_strict_refresh_rejects_a_malformed_optional_reply(position):
    fake = ReplayBleak(OLD)
    fake.script(replace={position: truncated(fake, position)})
    desk = new_desk()
    previous = snapshot(desk)
    with connections(fake):
        await expect_failure(desk.refresh(), ValueError)
    assert desk.client is None
    assert not desk.connected
    assert not any(health.valid for health in desk.settings_health.values())
    assert desk.state == previous
    await desk.disconnect()


@pytest.mark.parametrize("position", list(OPTIONAL_GROUPS), ids=position_id)
async def test_runtime_refresh_isolates_a_malformed_optional_group(position):
    group = OPTIONAL_GROUPS[position]
    healthy = "reminders" if group == "memories" else "memories"
    fake = ReplayBleak(OLD)
    desk = new_desk()
    with connections(fake):
        await desk.refresh()
        cached = snapshot(desk)
        fake.replies = default_replies(SLOTS_B, sitting=30)
        fake.script(replace={position: truncated(fake, position)})
        fake.writes.clear()
        state = await desk.refresh(allow_partial_settings=True)
        fresh = fake.expected_state()
        assert sent_commands(fake) == list(REFRESH)
        assert desk.connected
        assert not desk.settings_health[group].valid
        assert desk.settings_health[group].error == "invalid_response"
        assert desk.settings_health[healthy].valid
        assert getattr(state, group) == getattr(cached, group)
        assert getattr(state, healthy) == getattr(fresh, healthy)
        assert (state.position, state.offset_raw, state.capabilities) == (
            fresh.position,
            fresh.offset_raw,
            fresh.capabilities,
        )

        fake.script()
        fake.writes.clear()
        await desk.refresh(allow_partial_settings=True, settings_interval=300)
        reread = MEMORY_REREAD if group == "memories" else [0x88]
        assert sent_commands(fake) == [0x80, 0x81, *reread]
        assert desk.state == fresh
        assert all(health.valid for health in desk.settings_health.values())
    await desk.disconnect()
