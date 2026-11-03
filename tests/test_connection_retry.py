"""Exercise the installed retry connector without real Bluetooth or delays."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakNotFoundError

from custom_components.ha_linak.client import DeskClient
from tests.test_client import FakeBleak


@pytest.fixture
def retry_transport():
    """Keep the real connector loop, replacing only its radio and OS helpers."""

    class Transport(FakeBleak):
        attempts = 0
        failures = 2
        block = False
        instance = None

        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.is_connected = False
            type(self).instance = self

        async def connect(self, **_kwargs):
            type(self).attempts += 1
            if self.block:
                await asyncio.Event().wait()
            if self.attempts <= self.failures:
                raise TimeoutError
            self.is_connected = True

    with (
        patch(
            "custom_components.ha_linak.client.BleakClientWithServiceCache", Transport
        ),
        patch("bleak_retry_connector.IS_LINUX", False),
        patch(
            "bleak_retry_connector._has_valid_services_in_cache",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("bleak_retry_connector.wait_for_disconnect", new_callable=AsyncMock),
    ):
        yield Transport


async def test_refresh_reaches_third_connection_attempt(retry_transport):
    """Two failed paths must not end setup before HA can select another path."""
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    try:
        state = await desk.refresh()
        assert retry_transport.attempts == 3
        assert desk.connected
        assert state.height_cm == 82.38
        assert len(state.memories) == 4
    finally:
        await desk.disconnect()


async def test_exhausted_connector_does_not_publish_readings(retry_transport):
    """Repeated connection failures still end without GATT reads or controls."""
    retry_transport.failures = 100
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with pytest.raises(BleakNotFoundError):
        await desk.refresh()
    assert not desk.connected
    assert desk.state.height_cm is None
    assert retry_transport.instance.writes == []


async def test_connection_retries_keep_the_outer_refresh_deadline(retry_transport):
    """The connector's retry policy cannot extend the owning refresh budget."""
    retry_transport.block = True
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with (
        patch("custom_components.ha_linak.client.REFRESH_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await desk.refresh()
    assert retry_transport.attempts == 1
    assert not desk.connected
    assert desk.state.height_cm is None
    assert retry_transport.instance.writes == []
