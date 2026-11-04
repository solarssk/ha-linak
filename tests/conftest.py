"""Enable real Home Assistant test fixtures for the custom integration."""

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    return enable_custom_integrations


@pytest.fixture(autouse=True)
def bluetooth_history(mock_bluetooth):
    from unittest.mock import PropertyMock, patch

    with patch(
        "bluetooth_adapters.systems.linux.LinuxAdapters.history",
        new_callable=PropertyMock,
        return_value={},
    ):
        yield


@pytest.fixture(autouse=True)
def cached_system_names():
    from unittest.mock import AsyncMock, patch

    with patch(
        "custom_components.ha_linak.config_flow.cached_bluez_names",
        new_callable=AsyncMock,
        return_value={},
    ):
        yield


@pytest.fixture(autouse=True)
def operation_reset_timers():
    """A desk built without a config entry is never unloaded; cancel its timer."""
    from custom_components.ha_linak import client

    desks = []
    original = client.DeskClient.__init__

    def tracking(self, *args, **kwargs):
        original(self, *args, **kwargs)
        desks.append(self)

    client.DeskClient.__init__ = tracking
    try:
        yield
    finally:
        client.DeskClient.__init__ = original
        for desk in desks:
            desk.cancel_operation_reset()
