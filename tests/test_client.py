"""Exercise the asynchronous transport against real captured responses."""

import json
import asyncio
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
    backend_id = "bleak_esphome"

    def __init__(self):
        self.is_connected = True
        self.callbacks = {}
        self.writes = []
        self.fail_command = None
        self.paired = False
        self.disconnected = asyncio.Event()

    async def pair(self):
        self.paired = True

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
        self.disconnected.set()


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
    "phase",
    ["connection", "notify_dpg", "notify_height", "position_read", "extended_reads"],
)
async def test_each_hanging_phase_is_bounded_and_discards_session(phase):
    import asyncio

    class HangingBleak(FakeBleak):
        async def start_notify(self, uuid, callback):
            if (phase == "notify_dpg" and uuid == DPG_UUID) or (
                phase == "notify_height" and uuid == HEIGHT_UUID
            ):
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


async def test_stage_logs_identify_subscription_and_link_loss_without_identifiers(
    caplog,
):
    import logging
    from unittest.mock import AsyncMock

    fake = FakeBleak()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Private desk", {}), lambda: None)
    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.ha_linak.client"),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
    ):
        await desk.refresh()
        desk._disconnected(fake)
    assert "entering notify_dpg" in caplog.text
    assert "entering notify_height" in caplog.text
    assert "BLE link lost during ready after" in caplog.text
    assert "AA:BB:CC:DD:EE:FF" not in caplog.text
    assert "Private desk" not in caplog.text
    await desk.disconnect()


@pytest.mark.parametrize("backend", ["bluez_dbus", "bleak_esphome"])
async def test_pairing_precedes_notifications_for_local_and_proxy_backends(backend):
    from unittest.mock import AsyncMock

    class AuthenticatedBleak(FakeBleak):
        async def start_notify(self, uuid, callback):
            assert self.paired
            await super().start_notify(uuid, callback)

    fake = AuthenticatedBleak()
    fake.backend_id = backend
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)

    async def pair_local(address):
        assert address == desk.device.address
        await fake.pair()

    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch(
            "custom_components.ha_linak.client.pair_bluez", side_effect=pair_local
        ) as local,
    ):
        await desk.refresh()
        await desk.refresh()
    assert local.await_count == (1 if backend == "bluez_dbus" else 0)
    assert fake.paired
    assert desk.connected
    await desk.disconnect()


async def test_corebluetooth_uses_automatic_authentication():
    from unittest.mock import AsyncMock

    fake = FakeBleak()
    fake.backend_id = "core_bluetooth"
    fake.pair = AsyncMock(side_effect=NotImplementedError)
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    fake.pair.assert_not_awaited()
    await desk.disconnect()


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("rejected", "DeskAuthenticationError"),
        ("unsupported", "DeskPairingUnsupported"),
        ("timeout", "DeskPairingTimeout"),
    ],
)
async def test_pairing_failures_release_session_before_any_gatt_writes(
    failure, expected
):
    from unittest.mock import AsyncMock
    from bleak.exc import BleakError
    from custom_components.ha_linak import client as module

    fake = FakeBleak()

    async def pair():
        if failure == "timeout":
            await asyncio.Future()
        if failure == "unsupported":
            raise NotImplementedError("Private proxy name")
        raise BleakError("Private address")

    fake.pair = pair
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch("custom_components.ha_linak.client.PAIR_TIMEOUT", 0.01),
        pytest.raises(getattr(module, expected)),
    ):
        await desk.refresh()
    assert not fake.is_connected
    assert not fake.callbacks
    assert not fake.writes


@pytest.mark.parametrize(
    "phase", ["pairing", "notify_dpg", "notify_height", "position_read"]
)
async def test_link_loss_interrupts_pending_operation_without_waiting_for_timeout(
    phase,
):
    from unittest.mock import AsyncMock
    from custom_components.ha_linak.client import DeskLinkLost

    started = asyncio.Event()
    cancelled = asyncio.Event()
    fake = FakeBleak()

    async def hang(*args):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    if phase == "pairing":
        fake.pair = hang
    elif phase == "position_read":
        fake.read_gatt_char = hang
    else:
        original = fake.start_notify

        async def subscribe(uuid, callback):
            if uuid == (DPG_UUID if phase == "notify_dpg" else HEIGHT_UUID):
                await hang()
            await original(uuid, callback)

        fake.start_notify = subscribe
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    connect = AsyncMock(return_value=fake)
    with patch("custom_components.ha_linak.client.establish_connection", connect):
        task = asyncio.create_task(desk.refresh())
        await asyncio.wait_for(started.wait(), 1)
        fake.is_connected = False
        connect.call_args.kwargs["disconnected_callback"](fake)
        with pytest.raises(DeskLinkLost):
            await asyncio.wait_for(task, 1)
    assert cancelled.is_set()
    assert desk.stage == phase
    assert desk.client is None
    assert desk._operation is None


async def test_repeated_cancellation_drains_cleanup_and_preserves_cancellation():
    from unittest.mock import AsyncMock

    started = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()
    fake = FakeBleak()

    async def pair():
        started.set()
        await asyncio.Future()

    async def disconnect():
        closing.set()
        await release.wait()
        fake.is_connected = False

    fake.pair = pair
    fake.disconnect = disconnect
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        task = asyncio.create_task(desk.refresh())
        await started.wait()
        task.cancel()
        await closing.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not fake.is_connected
    assert desk.client is None


@pytest.mark.parametrize(
    "mode", ["already_lost", "silent_loss", "error_after_callback"]
)
async def test_connection_loss_races_never_publish_a_ready_session(mode):
    from unittest.mock import AsyncMock
    from bleak.exc import BleakError
    from custom_components.ha_linak.client import DeskLinkLost

    fake = FakeBleak()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    if mode == "already_lost":
        fake.is_connected = False

    async def pair():
        fake.is_connected = False
        if mode == "error_after_callback":
            desk._disconnected(fake)
            raise BleakError("Private transport details")

    fake.pair = pair
    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        pytest.raises(DeskLinkLost),
    ):
        await desk.refresh()
    assert desk.client is None
    assert not desk.connected
    assert not fake.writes
    assert not fake.callbacks


async def test_cleanup_failure_preserves_original_authentication_error_and_redacts_logs(
    caplog,
):
    import logging
    from unittest.mock import AsyncMock
    from bleak.exc import BleakError
    from custom_components.ha_linak.client import DeskAuthenticationError

    fake = FakeBleak()
    fake.pair = AsyncMock(side_effect=BleakError("Private authentication payload"))
    fake.disconnect = AsyncMock(side_effect=BleakError("Private cleanup address"))
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Private desk", {}), lambda: None)
    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.ha_linak.client"),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        pytest.raises(DeskAuthenticationError),
    ):
        await desk.refresh()
    assert desk.client is None
    assert "BLE cleanup failed: BleakError" in caplog.text
    assert "Private" not in caplog.text
    assert "AA:BB:CC:DD:EE:FF" not in caplog.text


async def test_initial_height_notification_does_not_publish_incomplete_state():
    from unittest.mock import AsyncMock

    changes = []

    class EarlyPosition(FakeBleak):
        async def start_notify(self, uuid, callback):
            await super().start_notify(uuid, callback)
            if uuid == HEIGHT_UUID:
                callback(None, bytearray.fromhex("9e050000"))

    desk = DeskClient(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}),
        lambda: changes.append(desk.connected),
    )
    fake = EarlyPosition()
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        AsyncMock(return_value=fake),
    ):
        await desk.refresh()
    assert desk.connected
    assert changes == []
    fake.callbacks[HEIGHT_UUID](None, bytearray.fromhex("e8030000"))
    assert changes == [True]
    fake.callbacks[HEIGHT_UUID](None, bytearray(b"\x00"))
    assert changes == [True, False]
    await desk.disconnect()


async def test_bluez_agent_failure_is_distinct_and_releases_transport():
    from unittest.mock import AsyncMock
    from custom_components.ha_linak.client import DeskPairingAgentError
    from custom_components.ha_linak.pairing import BlueZAgentUnavailable

    fake = FakeBleak()
    fake.backend_id = "bluez_dbus"
    fake.pair = AsyncMock()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with (
        patch(
            "custom_components.ha_linak.client.establish_connection",
            AsyncMock(return_value=fake),
        ),
        patch(
            "custom_components.ha_linak.client.pair_bluez",
            AsyncMock(side_effect=BlueZAgentUnavailable("private address")),
        ),
        pytest.raises(DeskPairingAgentError) as error,
    ):
        await desk.refresh()
    assert "private" not in str(error.value)
    assert desk.stage == "pairing"
    assert not fake.is_connected
    assert fake.writes == []
    fake.pair.assert_not_awaited()
