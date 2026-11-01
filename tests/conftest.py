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
