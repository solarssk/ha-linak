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
