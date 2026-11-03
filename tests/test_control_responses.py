"""Exercise HA's frontend action handler without opening a WebSocket socket."""

import asyncio
from inspect import unwrap
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from homeassistant.components.websocket_api.commands import handle_call_service
from homeassistant.core import Context

from test_native_controls import OPTIONS, setup_entry


def connection():
    return SimpleNamespace(
        context=Mock(return_value=Context()),
        logger=logging.getLogger("test.linak.frontend"),
        send_error=Mock(),
        send_result=Mock(),
    )


@pytest.mark.parametrize("request_domain", ["number", "button"])
async def test_busy_frontend_request_is_validation_not_device_failure(
    hass, caplog, request_domain
):
    entry, fake = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    fake.stall = True
    frontend = connection()
    number = hass.states.async_all("number")[0].entity_id
    memory = next(
        state.entity_id
        for state in hass.states.async_all("button")
        if state.entity_id.endswith("_position_1")
    )
    message = {
        "id": 1,
        "type": "call_service",
        "domain": request_domain,
        "service": "set_value" if request_domain == "number" else "press",
        "service_data": {"entity_id": number, "value": 84}
        if request_domain == "number"
        else {"entity_id": memory},
        "return_response": False,
    }
    with patch("custom_components.ha_linak.motion.COMMAND_INTERVAL", 60):
        movement = asyncio.create_task(coordinator.async_move_to_cm(83))
        try:
            await asyncio.wait_for(fake.target_written.wait(), 1)
            before = list(fake.writes)
            await unwrap(handle_call_service)(hass, frontend, message)
            args, kwargs = frontend.send_error.call_args
            assert args[0] == 1
            assert args[1] == "service_validation_error"
            assert kwargs["translation_domain"] == "ha_linak"
            assert kwargs["translation_key"] == "control_busy"
            frontend.send_result.assert_not_called()
            assert fake.writes == before
            assert coordinator.desk.connected
            assert coordinator.desk.control_busy
            assert coordinator.desk.last_control_result == "moving"
            assert "Error during service call" not in caplog.text
            assert "LINAK memory failed" not in caplog.text
            assert "LINAK target failed" not in caplog.text
        finally:
            await coordinator.async_stop()
            await movement
            await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_stop_remains_a_frontend_device_error(hass, caplog):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.fail_stop = True
    frontend = connection()
    stop = next(
        state.entity_id
        for state in hass.states.async_all("button")
        if state.entity_id.endswith("_stop")
    )
    await unwrap(handle_call_service)(
        hass,
        frontend,
        {
            "id": 1,
            "type": "call_service",
            "domain": "button",
            "service": "press",
            "service_data": {"entity_id": stop},
            "return_response": False,
        },
    )
    args, kwargs = frontend.send_error.call_args
    assert args[1] == "home_assistant_error"
    assert kwargs["translation_key"] == "stop_failed"
    frontend.send_result.assert_not_called()
    assert "Error during service call to button.press" in caplog.text
    assert not entry.runtime_data.desk.connected
    await hass.config_entries.async_unload(entry.entry_id)
