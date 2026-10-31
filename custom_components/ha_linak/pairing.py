"""Device-restricted BlueZ Just Works pairing on a temporary application bus."""

from contextlib import ExitStack
from typing import Any

from bleak.exc import BleakError
from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusError, DBusFastError
from dbus_fast.service import ServiceInterface, method

AGENT_PATH = "/org/ha_linak/pairing"
BLUEZ = "org.bluez"
DEVICE = "org.bluez.Device1"


class BlueZAgentUnavailable(BleakError):
    """The host cannot prepare a scoped pairing agent for this connection."""


class DeskAgent(ServiceInterface):
    """Accept Just Works only for the device selected for this pairing attempt."""

    def __init__(self, device_path: str) -> None:
        super().__init__("org.bluez.Agent1")
        self.device_path = device_path

    def _check(self, device: str) -> None:
        if device != self.device_path:
            raise DBusError("org.bluez.Error.Rejected", "Unexpected pairing device")

    @method()
    def RequestAuthorization(self, device: "o") -> None:  # type: ignore[name-defined]  # noqa: F821, N802
        self._check(device)

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u") -> None:  # type: ignore[name-defined]  # noqa: F821, N802
        # NoInputNoOutput advertises no numeric-comparison capability.
        self._check(device)

    @method()
    def Cancel(self) -> None:  # noqa: N802
        """BlueZ cancelled the pending authentication interaction."""

    @method()
    def Release(self) -> None:  # noqa: N802
        """BlueZ released this application's agent."""


async def _call(
    bus: MessageBus, path: str, interface: str, member: str, **kwargs: Any
) -> list[Any]:
    reply = await bus.call(
        Message(
            destination=BLUEZ, path=path, interface=interface, member=member, **kwargs
        )
    )
    if reply is None or reply.message_type == MessageType.ERROR:
        # Never propagate BlueZ messages containing device identifiers.
        error = BleakError if member == "Pair" else BlueZAgentUnavailable
        raise error("BlueZ pairing operation failed")
    return reply.body


async def pair_bluez(address: str) -> None:
    """Pair the connected local device on the same bus as its temporary agent.

    HA still owns connection and adapter selection. Resolve the connected device
    from BlueZ rather than assuming hci0 or reading private Bleak backend fields.
    Ambiguous paths fail closed. Closing our private bus unregisters the agent;
    RequestDefaultAgent is deliberately never used. BlueZ may make its first
    registered agent a temporary fallback; other device paths are rejected.
    """
    try:
        with ExitStack() as cleanup:
            bus = MessageBus(bus_type=BusType.SYSTEM)
            cleanup.callback(bus.disconnect)
            await bus.connect()
            objects = (
                await _call(
                    bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"
                )
            )[0]
            candidates = [
                (path, interfaces[DEVICE])
                for path, interfaces in objects.items()
                if DEVICE in interfaces
                and interfaces[DEVICE].get("Address") is not None
                and interfaces[DEVICE]["Address"].value.upper() == address.upper()
                and interfaces[DEVICE].get("Connected") is not None
                and interfaces[DEVICE]["Connected"].value
            ]
            if len(candidates) != 1:
                raise BlueZAgentUnavailable("Cannot identify one connected BlueZ desk")
            path, properties = candidates[0]
            if properties.get("Paired") is not None and properties["Paired"].value:
                return
            bus.export(AGENT_PATH, DeskAgent(path))
            await _call(
                bus,
                "/org/bluez",
                "org.bluez.AgentManager1",
                "RegisterAgent",
                signature="os",
                body=[AGENT_PATH, "NoInputNoOutput"],
            )
            await _call(bus, path, DEVICE, "Pair")
    except OSError, DBusFastError:
        raise BlueZAgentUnavailable("BlueZ pairing service unavailable") from None
