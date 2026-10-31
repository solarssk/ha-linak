"""BlueZ pairing uses a private application agent and the selected peer only."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak.exc import BleakError
from dbus_fast import Message, Variant
from dbus_fast.errors import DBusError
from custom_components.ha_linak.pairing import AGENT_PATH, DEVICE, DeskAgent, pair_bluez

ADDRESS = "AA:BB:CC:DD:EE:FF"
PATH = "/org/bluez/hci2/dev_AA_BB_CC_DD_EE_FF"


def device(*, paired=False, connected=True, address=ADDRESS):
    return {
        DEVICE: {
            "Address": Variant("s", address),
            "Connected": Variant("b", connected),
            "Paired": Variant("b", paired),
        }
    }


@pytest.fixture
def bus():
    bus = Mock()
    bus.connect = AsyncMock()
    objects = {PATH: device()}

    async def call(message):
        if message.member == "GetManagedObjects":
            return Message.new_method_return(message, "a{oa{sa{sv}}}", [objects])
        return Message.new_method_return(message)

    bus.call = AsyncMock(side_effect=call)
    # D-Bus assigns serials before replies; the fake must do the same.
    original = bus.call.side_effect

    async def numbered(message):
        message.serial = 1
        return await original(message)

    bus.call.side_effect = numbered
    with patch("custom_components.ha_linak.pairing.MessageBus", return_value=bus):
        yield bus, objects


async def test_pair_uses_same_bus_agent_without_becoming_default(bus):
    transport, objects = bus
    objects["/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"] = device(connected=False)
    await pair_bluez(ADDRESS.lower())
    calls = [args.args[0] for args in transport.call.await_args_list]
    assert [c.member for c in calls] == ["GetManagedObjects", "RegisterAgent", "Pair"]
    assert calls[1].body == [AGENT_PATH, "NoInputNoOutput"]
    assert calls[2].path == PATH
    assert transport.export.call_args.args[1].device_path == PATH
    transport.disconnect.assert_called_once()


async def test_existing_bond_is_not_replaced(bus):
    transport, objects = bus
    objects[PATH] = device(paired=True)
    await pair_bluez(ADDRESS)
    transport.export.assert_not_called()
    assert transport.call.await_count == 1
    transport.disconnect.assert_called_once()


@pytest.mark.parametrize(
    "objects",
    [
        {},
        {PATH: device(connected=False)},
        {PATH: device(address="11:22:33:44:55:66")},
        {PATH: device(), "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF": device()},
    ],
)
async def test_missing_or_ambiguous_device_never_registers_agent(bus, objects):
    transport, current = bus
    current.clear()
    current.update(objects)
    with pytest.raises(BleakError, match="one connected"):
        await pair_bluez(ADDRESS)
    transport.export.assert_not_called()
    transport.disconnect.assert_called_once()


@pytest.mark.parametrize("phase", ["GetManagedObjects", "RegisterAgent", "Pair"])
async def test_private_dbus_errors_are_sanitized_and_agent_released(bus, phase):
    transport, _ = bus
    original = transport.call.side_effect

    async def call(message):
        if message.member == phase:
            message.serial = 1
            return Message.new_error(
                message, "org.bluez.Error.Failed", "Private desk " + ADDRESS
            )
        return await original(message)

    transport.call.side_effect = call
    with pytest.raises(BleakError, match="BlueZ pairing operation failed") as error:
        await pair_bluez(ADDRESS)
    assert ADDRESS not in str(error.value)
    transport.disconnect.assert_called_once()


@pytest.mark.parametrize("phase", ["connect", "RegisterAgent", "Pair"])
async def test_cancellation_closes_bus_and_removes_application_agent(bus, phase):
    transport, _ = bus
    started = asyncio.Event()
    original = transport.call.side_effect

    async def hang():
        started.set()
        await asyncio.Future()

    async def call(message):
        if message.member == phase:
            await hang()
        return await original(message)

    if phase == "connect":
        transport.connect.side_effect = hang
    else:
        transport.call.side_effect = call
    task = asyncio.create_task(pair_bluez(ADDRESS))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    transport.disconnect.assert_called_once()


async def test_bus_failure_is_sanitized(bus):
    transport, _ = bus
    transport.connect.side_effect = OSError("private " + ADDRESS)
    with pytest.raises(BleakError, match="service unavailable"):
        await pair_bluez(ADDRESS)
    transport.disconnect.assert_called_once()


def test_agent_rejects_other_devices_and_exposes_no_pin_or_service_authorization():
    agent = DeskAgent(PATH)
    agent.RequestConfirmation(PATH, 123456)
    agent.RequestAuthorization(PATH)
    agent.Cancel()
    agent.Release()
    for callback, args in [
        (agent.RequestConfirmation, (PATH + "1", 123456)),
        (agent.RequestAuthorization, (PATH + "1",)),
    ]:
        with pytest.raises(DBusError, match="Unexpected pairing device"):
            callback(*args)
    methods = {m.name for m in agent.introspect().methods}
    assert methods == {
        "RequestConfirmation",
        "RequestAuthorization",
        "Cancel",
        "Release",
    }


async def test_bus_construction_failure_is_sanitized():
    with patch(
        "custom_components.ha_linak.pairing.MessageBus",
        side_effect=OSError("Private host"),
    ):
        with pytest.raises(BleakError, match="service unavailable"):
            await pair_bluez(ADDRESS)


async def test_timeout_closes_pairing_bus(bus):
    transport, _ = bus
    original = transport.call.side_effect

    async def call(message):
        if message.member == "Pair":
            await asyncio.Future()
        return await original(message)

    transport.call.side_effect = call
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await pair_bluez(ADDRESS)
    transport.disconnect.assert_called_once()


async def test_dbus_authentication_failure_is_agent_unavailable(bus):
    from dbus_fast.errors import AuthError
    from custom_components.ha_linak.pairing import BlueZAgentUnavailable

    transport, _ = bus
    transport.connect.side_effect = AuthError("Private host identity")
    with pytest.raises(BlueZAgentUnavailable, match="service unavailable"):
        await pair_bluez(ADDRESS)
    transport.disconnect.assert_called_once()
