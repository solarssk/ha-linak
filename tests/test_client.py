"""Exercise the asynchronous transport against real captured responses."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest
from bleak.backends.device import BLEDevice
from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID

CAPTURE = json.loads(
    (Path(__file__).parent / "fixtures/dpg1c_read_queries.json").read_text()
)["responses"]


class FakeBleak:
    def __init__(self):
        self.is_connected = True
        self.callbacks = {}
        self.writes = []
        self.fail_command = None

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def write_gatt_char(self, uuid, data, response):
        self.writes.append((uuid, bytes(data)))
        assert data[0] == 0x7F and data[2] == 0
        if data[1] == self.fail_command:
            raise ConnectionError("simulated link loss")
        self.callbacks[DPG_UUID](None, bytearray.fromhex(CAPTURE[f"{data[1]:02x}"]))

    async def read_gatt_char(self, uuid):
        assert uuid == HEIGHT_UUID
        return bytearray.fromhex("9e050000")

    async def disconnect(self):
        self.is_connected = False


@pytest.mark.asyncio
async def test_complete_refresh_and_physical_height_update():
    fake = FakeBleak()
    changes = []
    desk = DeskClient(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: changes.append(True)
    )

    async def connect(*args, **kwargs):
        return fake

    with patch(
        "custom_components.ha_linak.client.establish_connection", side_effect=connect
    ):
        state = await desk.refresh()
    assert desk.connected
    assert state.height_cm == 82.38
    assert len(state.memories) == 4
    assert len(fake.writes) == 7
    fake.callbacks[HEIGHT_UUID](None, bytearray.fromhex("e8030000"))
    assert desk.state.height_cm == 78
    assert changes
    await desk.disconnect()
    assert not fake.is_connected


@pytest.mark.asyncio
async def test_query_failure_disconnects_and_does_not_publish_partial_data():
    fake = FakeBleak()
    fake.fail_command = 0x8A
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)

    async def connect(*args, **kwargs):
        return fake

    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=connect,
        ),
        pytest.raises(ConnectionError),
    ):
        await desk.refresh()
    assert not fake.is_connected
    assert not desk.connected
    assert desk.state.height_cm is None


@pytest.mark.asyncio
async def test_old_connection_notifications_are_ignored():
    fake = FakeBleak()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)

    async def connect(*args, **kwargs):
        return fake

    with patch(
        "custom_components.ha_linak.client.establish_connection", side_effect=connect
    ):
        await desk.refresh()
    callback = fake.callbacks[HEIGHT_UUID]
    await desk.disconnect()
    callback(None, bytearray.fromhex("00000000"))
    assert desk.state.height_cm == 82.38


@pytest.mark.parametrize(
    "phase", ["connection", "notifications", "position_read", "extended_reads"]
)
async def test_each_hanging_phase_is_bounded_and_discards_session(phase):
    import asyncio

    class HangingBleak(FakeBleak):
        async def start_notify(self, uuid, callback):
            if phase == "notifications":
                await asyncio.Future()
            await super().start_notify(uuid, callback)

        async def read_gatt_char(self, uuid):
            if phase == "position_read":
                await asyncio.Future()
            return await super().read_gatt_char(uuid)

        async def write_gatt_char(self, uuid, data, response):
            if phase == "extended_reads":
                await asyncio.Future()
            await super().write_gatt_char(uuid, data, response)

    fake = HangingBleak()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)

    async def connect(*args, **kwargs):
        if phase == "connection":
            await asyncio.Future()
        return fake

    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=connect,
        ),
        patch("custom_components.ha_linak.client.REFRESH_TIMEOUT", 0.04),
        patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01),
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await desk.refresh()
    assert desk.stage == phase
    assert desk.client is None
    assert not desk.connected
    if phase != "connection":
        assert not fake.is_connected


async def test_disconnect_during_query_fails_promptly_and_notifies():
    import asyncio
    from unittest.mock import AsyncMock

    waiting = asyncio.Event()
    fake = FakeBleak()
    changed = []
    desk = DeskClient(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: changed.append(True)
    )

    async def write(*args, **kwargs):
        waiting.set()

    fake.write_gatt_char = write
    connect = AsyncMock(return_value=fake)
    with patch("custom_components.ha_linak.client.establish_connection", connect):
        task = asyncio.create_task(desk.refresh())
        await waiting.wait()
        fake.is_connected = False
        connect.call_args.kwargs["disconnected_callback"](fake)
        with pytest.raises(ConnectionError, match="disconnected"):
            await task
    assert changed
    assert desk.client is None
    assert not desk.connected
    # A late disconnect callback from the old transport cannot affect a new session.
    changed.clear()
    connect.call_args.kwargs["disconnected_callback"](fake)
    assert not changed


async def test_unrelated_notifications_are_ignored_and_bad_position_invalidates_state():
    from unittest.mock import AsyncMock

    class NoisyBleak(FakeBleak):
        async def write_gatt_char(self, uuid, data, response):
            self.callbacks[DPG_UUID](None, bytearray(b"\x01"))
            self.callbacks[DPG_UUID](None, bytearray(b"\x00\x02"))
            self.callbacks[DPG_UUID](None, bytearray(b"\x01\xff"))
            await super().write_gatt_char(uuid, data, response)

    fake = NoisyBleak()
    changed = []
    desk = DeskClient(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: changed.append(True)
    )
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    assert desk.connected
    fake.callbacks[DPG_UUID](None, bytearray.fromhex(CAPTURE["80"]))
    fake.callbacks[HEIGHT_UUID](None, bytearray(b"\x00"))
    assert not desk.connected
    assert changed
    await desk.disconnect()


@pytest.mark.parametrize(
    "command,payload,reason",
    [("81", "010300901a", "offset"), ("80", "0102fd01", "slots")],
)
async def test_unsupported_panel_read_layout_is_rejected_and_disconnected(
    command, payload, reason
):
    from unittest.mock import AsyncMock

    fake = FakeBleak()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with (
        patch.dict(CAPTURE, {command: payload}),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        pytest.raises(ValueError, match=reason),
    ):
        await desk.refresh()
    assert not fake.is_connected
    assert not desk.connected
