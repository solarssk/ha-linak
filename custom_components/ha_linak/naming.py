"""Choose a readable desk name; HA reports the address when none is advertised."""

import asyncio
import sys

import bluetooth_adapters
from bluetooth_data_tools import human_readable_name

DEFAULT_NAME = "LINAK"


def desk_name(address: str, *names: str | None) -> str:
    for name in names:
        candidate = name.strip() if name else ""
        if candidate and candidate.upper() not in (address.upper(), DEFAULT_NAME):
            return candidate
    return DEFAULT_NAME


def discovery_title(address: str, *names: str | None) -> str:
    """Use the same device-name/short-address presentation as HA Idasen."""
    return human_readable_name(None, desk_name(address, *names), address)


async def cached_bluez_names() -> dict[str, str]:
    """Read local system metadata without connecting, scanning or changing aliases."""
    if sys.platform != "linux":
        return {}
    try:
        async with asyncio.timeout(2):
            objects = bluetooth_adapters.BlueZDBusObjects()
            await objects.load()
            names = {}
            for address, history in objects.history.items():
                name = desk_name(address, history.advertisement_data.local_name)
                if name != DEFAULT_NAME and name.isprintable():
                    names[address.upper()] = name
            return names
    except Exception:
        # Optional metadata must not prevent proxy-only or non-BlueZ discovery.
        # External cancellation remains cancellation, not an empty name cache.
        return {}
