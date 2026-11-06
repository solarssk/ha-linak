"""A dropped Bluetooth client is closed, and an unreachable desk explains itself."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from bleak.backends.device import BLEDevice
import pytest

from custom_components.ha_linak.client import DeskClient, _close_dropped_client
from custom_components.ha_linak.coordinator import (
    _UNREACHABLE_WARNED,
    LinakCoordinator,
)

from test_client import FakeBleak


async def connected_desk():
    fake = FakeBleak()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)

    async def connect(*args, **kwargs):
        return fake

    with patch(
        "custom_components.ha_linak.client.establish_connection", side_effect=connect
    ):
        await desk.refresh()
    return desk, fake


def count_disconnects(fake):
    calls = []
    original = fake.disconnect

    async def disconnect():
        calls.append(fake.is_connected)
        await original()

    fake.disconnect = disconnect
    return calls


@pytest.mark.asyncio
async def test_a_client_the_desk_dropped_is_closed_at_once():
    desk, fake = await connected_desk()
    calls = count_disconnects(fake)
    fake.is_connected = False
    desk._disconnected(fake)
    await asyncio.gather(*desk._cleanup_tasks)
    assert calls == [False]
    assert not desk._cleanup_tasks


@pytest.mark.asyncio
async def test_a_dropped_client_is_closed_when_the_link_is_discarded():
    desk, fake = await connected_desk()
    calls = count_disconnects(fake)
    fake.is_connected = False
    await desk._disconnect_link()
    assert calls == [False]
    assert desk.client is None


@pytest.mark.asyncio
async def test_a_live_client_is_still_disconnected_once():
    desk, fake = await connected_desk()
    calls = count_disconnects(fake)
    await desk._disconnect_link()
    assert calls == [True]


@pytest.mark.asyncio
async def test_a_failing_cleanup_never_blocks_a_reconnect():
    desk, fake = await connected_desk()

    async def broken():
        raise RuntimeError("bus already closed")

    fake.disconnect = broken
    fake.is_connected = False
    await _close_dropped_client(fake)
    await desk._disconnect_link()
    assert desk.client is None


@pytest.mark.asyncio
async def test_a_hung_cleanup_is_bounded():
    desk, fake = await connected_desk()
    gate = asyncio.Event()

    async def hung():
        await gate.wait()

    fake.disconnect = hung
    fake.is_connected = False
    with patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01):
        await asyncio.wait_for(_close_dropped_client(fake), 1)


@pytest.mark.asyncio
async def test_a_disconnect_from_another_client_is_ignored():
    desk, fake = await connected_desk()
    calls = count_disconnects(fake)
    desk._disconnected(SimpleNamespace(is_connected=False))
    assert not desk._cleanup_tasks
    assert calls == []


def test_a_disconnect_outside_a_loop_does_not_raise():
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    fake = FakeBleak()
    desk.client = fake
    desk._disconnected(fake)
    assert not desk._cleanup_tasks


def coordinator_stub():
    return SimpleNamespace(hass=SimpleNamespace(data={}), address="CA:C6:27:40:EA:93")


def test_reachability_hint_names_a_missing_connectable_scanner():
    stub = coordinator_stub()
    with patch(
        "custom_components.ha_linak.coordinator.bluetooth.async_scanner_count",
        return_value=0,
    ):
        hint = LinakCoordinator.reachability_hint(stub)
    assert "No connectable Bluetooth adapter or proxy" in hint


def test_reachability_hint_uses_the_home_assistant_diagnostics():
    stub = coordinator_stub()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_scanner_count",
            return_value=1,
        ),
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_address_reachability_diagnostics",
            return_value="seen by 2 scanner(s) but none with a connectable path",
        ) as diagnostics,
    ):
        hint = LinakCoordinator.reachability_hint(stub)
    assert hint == "seen by 2 scanner(s) but none with a connectable path"
    assert diagnostics.call_args.args[1] == "CA:C6:27:40:EA:93"


def test_reachability_hint_never_raises():
    stub = coordinator_stub()
    with patch(
        "custom_components.ha_linak.coordinator.bluetooth.async_scanner_count",
        side_effect=RuntimeError("boom"),
    ):
        assert (
            LinakCoordinator.reachability_hint(stub)
            == "Reachability diagnostics are unavailable"
        )


def test_an_outage_is_explained_once(caplog):
    stub = coordinator_stub()
    stub.reachability_hint = lambda: "all scanners busy"
    with caplog.at_level("WARNING"):
        LinakCoordinator._warn_unreachable_once(stub)
        LinakCoordinator._warn_unreachable_once(stub)
    assert caplog.text.count("all scanners busy") == 1
    assert stub.address in stub.hass.data[_UNREACHABLE_WARNED]


def test_the_explanation_survives_a_new_coordinator_for_a_setup_retry(caplog):
    first = coordinator_stub()
    first.reachability_hint = lambda: "adapter busy"
    retry = SimpleNamespace(
        hass=first.hass,
        address=first.address,
        reachability_hint=first.reachability_hint,
    )
    with caplog.at_level("WARNING"):
        LinakCoordinator._warn_unreachable_once(first)
        LinakCoordinator._warn_unreachable_once(retry)
    assert caplog.text.count("adapter busy") == 1


async def test_an_unreachable_desk_is_explained_once_and_rearmed_on_recovery(
    hass, caplog
):
    from test_native_controls import DEVICE, setup_entry

    entry, fake = await setup_entry(hass)
    coordinator = entry.runtime_data
    coordinator.reachability_hint = lambda: "no connectable path"
    with (
        caplog.at_level("WARNING"),
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ),
    ):
        await coordinator.async_refresh()
        await coordinator.async_refresh()
    assert caplog.text.count("no connectable path") == 1
    assert coordinator.address in hass.data[_UNREACHABLE_WARNED]
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            return_value=fake.reconnect(),
        ),
    ):
        await coordinator.async_refresh()
    assert coordinator.address not in hass.data[_UNREACHABLE_WARNED]
    await hass.config_entries.async_unload(entry.entry_id)
