"""Native HA controls and exclusive BLE ownership with synthetic motion feedback."""

import asyncio
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.motion import (
    CONTROL_UUID,
    TARGET_UUID,
    STOP,
    MotionError,
)
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID
from test_client import FakeBleak

ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE = BLEDevice(ADDRESS, "Test desk", {})
OPTIONS = {"enable_control": True, "minimum_height": 70.0, "maximum_height": 125.0}


class MotionBleak(FakeBleak):
    def __init__(self):
        super().__init__()
        self.position = 1438
        self.target_written = asyncio.Event()
        self.fail_stop = False
        self.stall = False
        self.responses = []
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: SimpleNamespace(
                properties=["read"]
                if uuid == HEIGHT_UUID
                else ["write-without-response"]
            )
        )

    async def read_gatt_char(self, uuid):
        return struct.pack("<HH", self.position, 0)

    async def write_gatt_char(self, uuid, data, response):
        self.responses.append((uuid, response))
        if uuid == DPG_UUID:
            await super().write_gatt_char(uuid, data, response)
            return
        assert not response
        self.writes.append((uuid, bytes(data)))
        if uuid == TARGET_UUID:
            self.target_written.set()
            if not self.stall:
                self.position = struct.unpack("<H", data)[0]
        elif data == STOP and self.fail_stop:
            raise ConnectionError("private backend details")


async def connected_desk(fake=None):
    fake = fake or MotionBleak()
    desk = DeskClient(DEVICE, lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    return desk, fake


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_height": None},
        {"minimum_height": True},
        {"maximum_height": float("nan")},
        {"maximum_height": 65},
        {"maximum_height": 1000},
    ],
)
def test_control_bounds_reject_invalid_values(changes):
    options = OPTIONS | changes
    with pytest.raises(ValueError):
        ControlSettings.from_options(options)


async def test_move_publishes_actual_feedback_and_prevents_polling():
    desk, fake = await connected_desk()
    settings = ControlSettings.from_options(OPTIONS)
    operation = asyncio.create_task(desk.move_to_cm(83, settings))
    await fake.target_written.wait()
    queries = len([uuid for uuid, _ in fake.writes if uuid == DPG_UUID])
    assert await desk.refresh() is desk.state
    assert len([uuid for uuid, _ in fake.writes if uuid == DPG_UUID]) == queries
    with pytest.raises(MotionError):
        await desk.move_to_cm(84, settings)
    await operation
    assert desk.state.height_cm == 83
    assert fake.writes[-1] == (CONTROL_UUID, STOP)
    assert desk.last_control_result == "completed"
    assert desk.connected
    await desk.disconnect()


async def test_stop_interrupts_active_move_before_disconnect():
    desk, fake = await connected_desk()
    fake.stall = True
    settings = ControlSettings.from_options(OPTIONS)
    operation = asyncio.create_task(desk.move_to_cm(83, settings))
    await fake.target_written.wait()
    await desk.stop()
    with pytest.raises(MotionError):
        await operation
    assert fake.writes[-1] == (CONTROL_UUID, STOP)
    assert not fake.is_connected
    assert not desk.control_busy


async def test_idle_stop_does_not_wake_or_request_a_target():
    desk, fake = await connected_desk()
    fake.writes.clear()
    await desk.stop()
    assert fake.writes == [(CONTROL_UUID, STOP)]
    await desk.disconnect()


async def test_memory_requeries_the_selected_slot():
    desk, fake = await connected_desk()
    # Stale local cache must not choose the destination.
    desk.state.memories[1] = desk.state.memories[3]
    settings = ControlSettings.from_options(OPTIONS)
    await desk.move_to_memory(1, settings)
    assert any(
        uuid == DPG_UUID and payload == b"\x7f\x8a\x00" for uuid, payload in fake.writes
    )
    assert not any(uuid == TARGET_UUID for uuid, _ in fake.writes)
    assert desk.state.height_cm == 82.38
    await desk.disconnect()


async def test_stop_failure_is_visible_and_discards_connection():
    desk, fake = await connected_desk()
    fake.fail_stop = True
    with pytest.raises(MotionError):
        await desk.stop()
    assert not desk.connected
    assert desk.last_control_result == "stop_failed"


async def test_shutdown_during_motion_sends_stop_and_cannot_resume():
    desk, fake = await connected_desk()
    fake.stall = True
    settings = ControlSettings.from_options(OPTIONS)
    operation = asyncio.create_task(desk.move_to_cm(83, settings))
    await fake.target_written.wait()
    await desk.disconnect()
    with pytest.raises(MotionError):
        await operation
    writes = list(fake.writes)
    with pytest.raises(MotionError):
        await desk.move_to_cm(83, settings)
    assert fake.writes == writes
    assert fake.writes[-1] == (CONTROL_UUID, STOP)


async def setup_entry(hass, options=None):
    fake = MotionBleak()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Desk",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS},
        options=options or {},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection", return_value=fake
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, fake


async def test_ha_controls_require_options_and_never_move_on_setup(hass):
    entry, fake = await setup_entry(hass)
    assert not hass.states.async_all("number")
    assert not hass.states.async_all("button")
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_native_number_buttons_and_service_errors(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    numbers = hass.states.async_all("number")
    assert len(numbers) == 1
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    target = numbers[0]
    assert target.state == "unknown"
    assert target.attributes["unit_of_measurement"] == "cm"
    assert target.attributes["mode"] == "box"
    assert target.attributes["min"] == 70
    assert target.attributes["max"] == 125
    assert len(hass.states.async_all("button")) == 5
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": target.entity_id, "value": 83},
        blocking=True,
    )
    assert hass.states.get(target.entity_id).state == "83.0"
    assert entry.runtime_data.data.height_cm == 83
    stop = next(
        s for s in hass.states.async_all("button") if s.entity_id.endswith("_stop")
    )
    fake.fail_stop = True
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": stop.entity_id}, blocking=True
        )
    assert not fake.is_connected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_flow_validates_limits_and_requires_confirmation(hass):
    entry, fake = await setup_entry(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], OPTIONS | {"minimum_height": 90}
        )
        assert result["errors"] == {"base": "invalid_limits"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], OPTIONS
        )
        assert result["step_id"] == "confirm"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm_control": False}
        )
        assert result["errors"] == {"base": "confirmation_required"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm_control": True}
        )
        assert result["type"] == "create_entry"
        assert entry.options == OPTIONS
        assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_bad_properties_and_offline_commands_never_write():
    desk, fake = await connected_desk()
    fake.writes.clear()
    fake.services = SimpleNamespace(get_characteristic=lambda _: None)
    settings = ControlSettings.from_options(OPTIONS)
    with pytest.raises(MotionError):
        await desk.move_to_cm(83, settings)
    assert not fake.writes
    await desk.disconnect()
    with pytest.raises(MotionError):
        await desk.move_to_cm(83, settings)
    assert not fake.writes


async def test_stop_failure_during_move_is_not_reported_as_success():
    desk, fake = await connected_desk()
    fake.stall = True
    settings = ControlSettings.from_options(OPTIONS)
    operation = asyncio.create_task(desk.move_to_cm(83, settings))
    await fake.target_written.wait()
    fake.fail_stop = True
    with pytest.raises(MotionError):
        await desk.stop()
    with pytest.raises(MotionError):
        await operation
    assert not desk.connected
    assert desk.last_control_result == "stop_failed"


async def test_cancelled_action_stops_before_releasing_ownership():
    desk, fake = await connected_desk()
    fake.stall = True
    settings = ControlSettings.from_options(OPTIONS)
    operation = asyncio.create_task(desk.move_to_cm(83, settings))
    await fake.target_written.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert fake.writes[-1] == (CONTROL_UUID, STOP)
    assert not desk.connected
    assert not desk.control_busy


async def test_empty_or_out_of_bounds_memory_does_not_move():
    desk, fake = await connected_desk()
    settings = ControlSettings.from_options(OPTIONS)
    with pytest.raises(MotionError):
        await desk.move_to_memory(4, settings)
    settings = ControlSettings(70, 100)
    with pytest.raises(ValueError):
        await desk.move_to_memory(3, settings)
    assert not any(uuid in (CONTROL_UUID, TARGET_UUID) for uuid, _ in fake.writes)
    assert not desk.connected


async def test_coordinator_poll_does_not_disconnect_active_movement(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    operation = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
    await fake.target_written.wait()
    with patch(
        "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await entry.runtime_data.async_refresh()
    assert fake.is_connected
    await entry.runtime_data.async_stop()
    with pytest.raises(HomeAssistantError):
        await operation
    await hass.config_entries.async_unload(entry.entry_id)


async def test_disabled_actions_are_rejected_by_coordinator(hass):
    entry, fake = await setup_entry(hass)
    fake.writes.clear()
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_move_to_cm(83)
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_stop()
    assert not fake.writes
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_disable_works_without_connection(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.is_connected = False
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"enable_control": False}
        )
        assert result["type"] == "create_entry"
        assert entry.options == OPTIONS | {"enable_control": False}
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_reject_enabling_when_offline(hass):
    entry, fake = await setup_entry(hass)
    fake.is_connected = False
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], OPTIONS
    )
    assert result["errors"] == {"base": "invalid_limits"}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_native_memory_button_uses_common_controller(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    memory = next(
        s
        for s in hass.states.async_all("button")
        if s.entity_id.endswith("_position_1")
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": memory.entity_id}, blocking=True
    )
    assert entry.runtime_data.data.height_cm == 80.04
    assert fake.writes[-1] == (CONTROL_UUID, STOP)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_memory_button_defensively_rejects_missing_data(hass):
    from custom_components.ha_linak.button import LinakMemory
    from custom_components.ha_linak.protocol import StoredPosition

    entry, fake = await setup_entry(hass, OPTIONS)
    button = LinakMemory(entry.runtime_data, 0)
    entry.runtime_data.data.memories[0] = StoredPosition(None, 0)
    assert not button.available
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    entry.runtime_data.data.memories = []
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_empty_memory_readback_rejects_before_motion():
    from custom_components.ha_linak.protocol import StoredPosition

    desk, fake = await connected_desk()
    settings = ControlSettings.from_options(OPTIONS)
    with patch(
        "custom_components.ha_linak.client.decode_stored_position",
        return_value=StoredPosition(None, 0),
    ):
        with pytest.raises(MotionError):
            await desk.move_to_memory(0, settings)
    assert not any(uuid == TARGET_UUID for uuid, _ in fake.writes)
    assert not desk.connected


async def test_invalid_offset_readback_rejects_before_motion():
    desk, fake = await connected_desk()
    settings = ControlSettings.from_options(OPTIONS)
    with patch("custom_components.ha_linak.client.decode_offset", return_value=None):
        with pytest.raises(ValueError):
            await desk.move_to_cm(83, settings)
    assert not any(uuid in (TARGET_UUID, CONTROL_UUID) for uuid, _ in fake.writes)
    assert not desk.connected


async def test_stop_before_motion_preparation_completes_is_not_silent():
    desk, fake = await connected_desk()
    prepared = asyncio.Event()

    async def pending(*_args):
        prepared.set()
        await asyncio.Future()

    settings = ControlSettings.from_options(OPTIONS)
    with patch.object(desk, "_query", side_effect=pending):
        operation = asyncio.create_task(desk.move_to_cm(83, settings))
        await prepared.wait()
        with pytest.raises(MotionError):
            await desk.stop()
        with pytest.raises(MotionError):
            await operation
    assert not any(uuid == TARGET_UUID for uuid, _ in fake.writes)


async def test_stop_caller_cancellation_keeps_reservation_until_write_finishes():
    desk, fake = await connected_desk()
    entered, release = asyncio.Event(), asyncio.Event()
    original = fake.write_gatt_char

    async def paused(uuid, data, response):
        if uuid == CONTROL_UUID and data == STOP:
            entered.set()
            await release.wait()
        await original(uuid, data, response)

    with patch.object(fake, "write_gatt_char", side_effect=paused):
        first = asyncio.create_task(desk.stop())
        await entered.wait()
        second = asyncio.create_task(desk.stop())
        first.cancel()
        await asyncio.sleep(0)
        assert desk.control_busy
        settings = ControlSettings.from_options(OPTIONS)
        with pytest.raises(MotionError):
            await desk.move_to_cm(83, settings)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second
    assert fake.writes[-1] == (CONTROL_UUID, STOP)
    await desk.disconnect()


async def test_ha_unload_during_move_stops_before_disconnect(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    operation = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
    await fake.target_written.wait()
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(HomeAssistantError):
        await operation
    assert fake.writes[-1] == (CONTROL_UUID, STOP)
    assert not fake.is_connected


async def test_real_options_reload_creates_controls_without_moving(hass):
    entry, first = await setup_entry(hass)
    second = MotionBleak()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            return_value=second,
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], OPTIONS
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm_control": True}
        )
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert not first.is_connected
        assert len(hass.states.async_all("number")) == 1
        assert len(hass.states.async_all("button")) == 5
        assert all(uuid == DPG_UUID for uuid, _ in second.writes)
        assert await hass.config_entries.async_unload(entry.entry_id)
