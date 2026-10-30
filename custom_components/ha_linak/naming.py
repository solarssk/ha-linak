"""Choose a readable desk name; HA reports the address when none is advertised."""

DEFAULT_NAME = "LINAK"


def desk_name(address: str, *names: str | None) -> str:
    for name in names:
        if name and name.upper() != address.upper():
            return name
    return DEFAULT_NAME
