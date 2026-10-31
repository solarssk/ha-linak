"""Choose a readable desk name; HA reports the address when none is advertised."""

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
