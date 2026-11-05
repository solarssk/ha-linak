"""Native HA controls and exclusive BLE ownership with synthetic motion feedback."""

import asyncio
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.const import DOMAIN
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.motion import (
    CONTROL_UUID,
    TARGET_UUID,
    STOP,
    REFERENCE_STOP,
    MotionError,
)
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID
from test_client import FakeBleak
from test_integration import guide_to_range

ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE = BLEDevice(ADDRESS, "Test desk", {})
OPTIONS = {"minimum_height": 70.0, "maximum_height": 125.0}


class MotionBleak(FakeBleak):
    def __init__(self):
        super().__init__()
        self.position = 1438
        self.target_written = asyncio.Event()
        self.fail_stop = False
        self.stall = False
        self.activation = 1
        self.identity = bytes(range(16))
        self.reject_activation = False
        self.responses = []
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: SimpleNamespace(
                properties=["read"]
                if uuid == HEIGHT_UUID
                else (["write"] if uuid == DPG_UUID else ["write-without-response"])
            )
        )

    async def read_gatt_char(self, uuid):
        return struct.pack("<HH", self.position, 0)

    async def write_gatt_char(self, uuid, data, response):
        self.responses.append((uuid, response))
        if uuid == DPG_UUID and data[:2] == b"\x7f\x86":
            self.writes.append((uuid, bytes(data)))
            if data[2] == 0:
                reply = b"\x01\x11" + bytes([self.activation]) + self.identity
            elif self.reject_activation:
                reply = b"\x0b\x00"
            else:
                assert data[4:] == self.identity
                self.activation = 1
                reply = b"\x01\x00"
            self.callbacks[DPG_UUID](None, bytearray(reply))
            return
        if uuid == DPG_UUID:
            await super().write_gatt_char(uuid, data, response)
            return
        assert not response
        self.writes.append((uuid, bytes(data)))
        if uuid == TARGET_UUID and data != REFERENCE_STOP:
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
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert desk.last_control_result == "completed"
    assert desk.connected
    await desk.disconnect()


async def test_stop_interrupts_active_move_and_keeps_ready_link():
    desk, fake = await connected_desk()
    fake.stall = True
    settings = ControlSettings.from_options(OPTIONS)
    operation = asyncio.create_task(desk.move_to_cm(83, settings))
    await fake.target_written.wait()
    await desk.stop()
    with pytest.raises(MotionError):
        await operation
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert fake.is_connected
    assert not desk.control_busy

    fake.stall = False
    await desk.move_to_memory(1, settings)
    assert desk.connected
    await desk.disconnect()


async def test_idle_stop_does_not_wake_or_request_a_target():
    desk, fake = await connected_desk()
    fake.writes.clear()
    await desk.stop()
    assert fake.writes == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
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
    assert not any(
        uuid == TARGET_UUID and payload != REFERENCE_STOP
        for uuid, payload in fake.writes
    )
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
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]


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


async def test_existing_entry_gets_controls_and_stop_without_motion(hass):
    entry, fake = await setup_entry(hass)
    assert len(hass.states.async_all("number")) == 1
    assert hass.states.async_all("number")[0].state == "unavailable"
    assert len(hass.states.async_all("button")) == 5
    stop = next(
        s for s in hass.states.async_all("button") if s.entity_id.endswith("_stop")
    )
    assert stop.state != "unavailable"
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_native_number_buttons_and_service_errors(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    numbers = hass.states.async_all("number")
    assert len(numbers) == 1
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    target = numbers[0]
    assert target.state == "82"
    assert target.attributes["unit_of_measurement"] == "cm"
    assert target.attributes["mode"] == "slider"
    assert target.attributes["min"] == 70
    assert target.attributes["max"] == 125
    assert len(hass.states.async_all("button")) == 5
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": target.entity_id, "value": 83},
        blocking=True,
    )
    assert hass.states.get(target.entity_id).state == "83"
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


async def test_options_flow_updates_height_range_without_switches(hass):
    entry, fake = await setup_entry(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "range"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], OPTIONS | {"minimum_height": 90}
        )
        assert result["errors"] == {"base": "invalid_limits"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], OPTIONS
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
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
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
    await operation
    await hass.config_entries.async_unload(entry.entry_id)


async def test_missing_range_blocks_targets_but_keeps_stop_available(hass):
    entry, fake = await setup_entry(hass)
    fake.writes.clear()
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_move_to_cm(83)
    await entry.runtime_data.async_stop()
    assert fake.writes == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_reject_range_when_current_height_is_unavailable(hass):
    entry, fake = await setup_entry(hass)
    entry.runtime_data.last_update_success = False
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "range"}
    )
    assert result["description_placeholders"]["height"] == "?"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], OPTIONS
    )
    assert result["errors"] == {"base": "connection_unavailable"}
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
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
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
    assert not any(
        uuid == TARGET_UUID and payload != REFERENCE_STOP
        for uuid, payload in fake.writes
    )
    assert not desk.connected


async def test_invalid_offset_readback_rejects_before_motion():
    desk, fake = await connected_desk()
    settings = ControlSettings.from_options(OPTIONS)
    with patch("custom_components.ha_linak.client.decode_offset", return_value=None):
        with pytest.raises(ValueError):
            await desk.move_to_cm(83, settings)
    assert not any(uuid in (TARGET_UUID, CONTROL_UUID) for uuid, _ in fake.writes)
    assert not desk.connected


async def test_stop_before_motion_preparation_completes_sends_stop():
    desk, fake = await connected_desk()
    prepared = asyncio.Event()

    async def pending(*_args):
        prepared.set()
        await asyncio.Future()

    settings = ControlSettings.from_options(OPTIONS)
    with patch.object(desk, "_query", side_effect=pending):
        operation = asyncio.create_task(desk.move_to_cm(83, settings))
        await prepared.wait()
        await desk.stop()
        with pytest.raises(MotionError):
            await operation
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert not any(
        uuid == TARGET_UUID and payload != REFERENCE_STOP
        for uuid, payload in fake.writes
    )
    assert desk.last_control_result == "stop_sent"
    assert not desk.connected


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
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    await desk.disconnect()


async def test_ha_unload_during_move_stops_before_disconnect(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    operation = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
    await fake.target_written.wait()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await operation
    assert fake.writes[-2:] == [(CONTROL_UUID, STOP), (TARGET_UUID, REFERENCE_STOP)]
    assert not fake.is_connected


async def test_real_options_reload_sets_range_without_moving(hass):
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
            result["flow_id"], {"next_step_id": "range"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], OPTIONS
        )
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert not first.is_connected
        assert all(uuid == DPG_UUID for uuid, _ in first.writes)
        assert len(hass.states.async_all("number")) == 1
        assert len(hass.states.async_all("button")) == 5
        assert all(uuid == DPG_UUID for uuid, _ in second.writes)
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_slider_follows_only_settled_physical_height(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    target_id = hass.states.async_all("number")[0].entity_id
    fake.callbacks[HEIGHT_UUID](None, bytearray(struct.pack("<HH", 1600, 0)))
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == "82"
    from pytest_homeassistant.common import async_fire_time_changed
    from homeassistant.util import dt as dt_util
    from datetime import timedelta

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == "84"
    assert hass.states.get(target_id).attributes["mode"] == "slider"
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_onboarding_collects_range_before_creating_entry(hass):
    fake = MotionBleak()
    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=["99fa0001-338a-1024-8a49-009c0215f78a"],
        connectable=True,
    )
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
        patch("custom_components.ha_linak.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        result = await guide_to_range(hass, result)
        assert result["step_id"] == "finish"
        assert not hass.config_entries.async_entries(DOMAIN)
        initial_writes = list(fake.writes)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], OPTIONS | {"minimum_height": 130}
        )
        assert result["errors"] == {"base": "invalid_limits"}
        assert fake.writes == initial_writes
        # The desk moved while the range form was open. Initial cached height
        # fits OPTIONS, but the fresh 128 cm reading must reject that range.
        fake.position = 6000
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], OPTIONS
        )
        assert result["type"] == "progress"
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        result = await guide_to_range(hass, result)
        assert result["errors"] == {"base": "invalid_limits"}
        assert not hass.config_entries.async_entries(DOMAIN)
        updated_range = OPTIONS | {"maximum_height": 130}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], updated_range
        )
        assert result["type"] == "progress"
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        result = await guide_to_range(hass, result)
        assert result["type"] == "create_entry"
        assert result["options"] == updated_range
        assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
        await hass.async_block_till_done()


async def test_stalled_move_preserves_measured_sensor_and_slider_height(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    target_id = hass.states.async_all("number")[0].entity_id
    before = entry.runtime_data.data.height_cm
    operation = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
    await fake.target_written.wait()
    assert entry.runtime_data.data.height_cm == before
    assert float(hass.states.get(target_id).state) == round(before)
    await entry.runtime_data.async_stop()
    await operation
    await hass.config_entries.async_unload(entry.entry_id)


async def test_poll_during_disconnected_control_does_not_restore_availability(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    operation = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
    await fake.target_written.wait()
    fake.is_connected = False
    entry.runtime_data.desk._disconnected(fake)
    assert entry.runtime_data.desk.control_busy
    with pytest.raises(UpdateFailed):
        await entry.runtime_data._async_update_data()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not entry.runtime_data.last_update_success
    assert all(s.state == "unavailable" for s in hass.states.async_all("number"))
    with pytest.raises(HomeAssistantError):
        await operation
    await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_fresh_range_read_does_not_create_entry(hass):
    fake = MotionBleak()
    info = SimpleNamespace(
        address=ADDRESS,
        name="Desk",
        device=DEVICE,
        service_uuids=["99fa0001-338a-1024-8a49-009c0215f78a"],
        connectable=True,
    )
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ),
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        result = await guide_to_range(hass, result)
        assert result["step_id"] == "finish"
        fake.fail_command = 0x80
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], OPTIONS
        )
        assert result["type"] == "progress"
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        result = await guide_to_range(hass, result)
        assert result["step_id"] == "finish"
        assert result["errors"] == {"base": "cannot_connect"}
        assert not hass.config_entries.async_entries(DOMAIN)
        assert not fake.is_connected
        assert all(uuid == DPG_UUID for uuid, _ in fake.writes)


@pytest.mark.parametrize("memory", [False, True])
async def test_inactive_client_is_prepared_before_explicit_motion(memory):
    fake = MotionBleak()
    fake.activation = 0
    desk, _ = await connected_desk(fake)
    assert fake.activation == 0
    assert not any(data[2:3] == b"\x80" for uuid, data in fake.writes)
    identity = fake.identity
    if memory:
        await desk.move_to_memory(0, ControlSettings(70, 125))
    else:
        await desk.move_to_cm(83, ControlSettings(70, 125))
    activation = (DPG_UUID, b"\x7f\x86\x80\x01" + identity)
    assert fake.writes.count(activation) == 1
    first_target = next(
        i
        for i, (uuid, payload) in enumerate(fake.writes)
        if uuid == TARGET_UUID and payload != REFERENCE_STOP
    )
    assert fake.writes.index(activation) < first_target
    assert fake.identity == identity
    assert desk.connected
    await desk.move_to_cm(84, ControlSettings(70, 125))
    assert fake.writes.count(activation) == 1
    await desk.disconnect()


async def test_rejected_activation_never_sends_movement_commands():
    fake = MotionBleak()
    fake.activation = 0
    fake.reject_activation = True
    desk, _ = await connected_desk(fake)
    from custom_components.ha_linak.calibration import SettingRejected

    settings = ControlSettings(70, 125)
    with pytest.raises(SettingRejected):
        await desk.move_to_cm(83, settings)
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert not desk.connected
    assert fake.activation == 0


async def test_new_connection_rechecks_inactive_identity_before_motion():
    fake = MotionBleak()
    desk, _ = await connected_desk(fake)
    await desk.move_to_cm(83, ControlSettings(70, 125))
    await desk.disconnect()
    fake.activation = 0
    with patch(
        "custom_components.ha_linak.client.establish_connection",
        side_effect=fake.reconnect,
    ):
        await desk.refresh()
    assert fake.activation == 0
    await desk.stop()
    assert fake.activation == 0
    await desk.move_to_cm(84, ControlSettings(70, 125))
    assert fake.activation == 1
    assert sum(data[:4] == b"\x7f\x86\x80\x01" for _, data in fake.writes) == 1
    await desk.disconnect()


async def test_cancelled_activation_never_reaches_target_or_replays():
    fake = MotionBleak()
    fake.activation = 0
    desk, _ = await connected_desk(fake)
    started = asyncio.Event()
    original = fake.write_gatt_char

    async def hang_activation(uuid, data, response):
        if data[:4] == b"\x7f\x86\x80\x01":
            started.set()
            await asyncio.Event().wait()
        await original(uuid, data, response)

    with patch.object(fake, "write_gatt_char", side_effect=hang_activation):
        task = asyncio.create_task(desk.move_to_cm(83, ControlSettings(70, 125)))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert not desk.connected
    assert fake.activation == 0


@pytest.mark.parametrize(
    "phase", ["offset", "memory", "status", "barrier", "activation", "verification"]
)
@pytest.mark.parametrize("failed_stop", [False, True])
async def test_stop_during_preparation_writes_before_disconnect(phase, failed_stop):
    fake = MotionBleak()
    fake.activation = 0
    desk, _ = await connected_desk(fake)
    entered = asyncio.Event()
    events = []
    original_write = fake.write_gatt_char
    original_disconnect = fake.disconnect
    query = {
        "offset": b"\x7f\x81\x00",
        "memory": b"\x7f\x89\x00",
        "status": b"\x7f\x86\x00",
        "barrier": b"\x7f\x80\x00",
        "activation": b"\x7f\x86\x80\x01" + fake.identity,
        "verification": b"\x7f\x86\x00",
    }[phase]

    async def paused_write(uuid, data, response):
        verification = phase != "verification" or fake.activation == 1
        if uuid == DPG_UUID and data == query and verification:
            entered.set()
            await asyncio.Event().wait()
        await original_write(uuid, data, response)
        if uuid == CONTROL_UUID and data == STOP:
            events.append("stop")

    async def record_disconnect():
        events.append("disconnect")
        await original_disconnect()

    fake.fail_stop = failed_stop
    with (
        patch.object(fake, "write_gatt_char", side_effect=paused_write),
        patch.object(fake, "disconnect", side_effect=record_disconnect),
    ):
        operation = asyncio.create_task(
            desk.move_to_memory(0, ControlSettings(70, 125))
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        if failed_stop:
            with pytest.raises(MotionError):
                await desk.stop()
        else:
            await desk.stop()
        with pytest.raises((MotionError, ConnectionError)):
            await operation
    assert events == (["disconnect"] if failed_stop else ["stop", "disconnect"])
    assert sum(uuid == CONTROL_UUID and data == STOP for uuid, data in fake.writes) == 1
    assert fake.writes.count((TARGET_UUID, REFERENCE_STOP)) == 1
    assert not any(
        uuid == TARGET_UUID and payload != REFERENCE_STOP
        for uuid, payload in fake.writes
    )
    assert not any(uuid == CONTROL_UUID and data != STOP for uuid, data in fake.writes)
    assert not desk.connected
    assert not desk.control_busy
    assert desk.last_control_result == ("stop_failed" if failed_stop else "stop_sent")


async def test_repeated_stop_caller_cancellation_during_preparation_drains_once():
    desk, fake = await connected_desk()
    preparation, stop_entered, release = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    original = fake.write_gatt_char
    settings = ControlSettings(70, 125)

    async def paused_write(uuid, data, response):
        if uuid == DPG_UUID and data == b"\x7f\x86\x00":
            preparation.set()
            await asyncio.Event().wait()
        if uuid == CONTROL_UUID and data == STOP:
            stop_entered.set()
            await release.wait()
        await original(uuid, data, response)

    with patch.object(fake, "write_gatt_char", side_effect=paused_write):
        operation = asyncio.create_task(desk.move_to_cm(83, settings))
        await asyncio.wait_for(preparation.wait(), timeout=1)
        first = asyncio.create_task(desk.stop())
        await asyncio.wait_for(stop_entered.wait(), timeout=1)
        second = asyncio.create_task(desk.stop())
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        await asyncio.sleep(0)
        assert desk.control_busy
        assert fake.is_connected
        with pytest.raises(MotionError):
            await desk.move_to_cm(84, settings)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second
        with pytest.raises(MotionError):
            await operation
    assert sum(uuid == CONTROL_UUID and data == STOP for uuid, data in fake.writes) == 1
    assert not any(
        uuid == TARGET_UUID and payload != REFERENCE_STOP
        for uuid, payload in fake.writes
    )
    assert not fake.is_connected
    assert not desk.control_busy


async def test_preparation_stop_timeout_is_bounded_and_reported():
    desk, fake = await connected_desk()
    preparation = asyncio.Event()
    original = fake.write_gatt_char
    settings = ControlSettings(70, 125)

    async def paused_write(uuid, data, response):
        if uuid == DPG_UUID and data == b"\x7f\x86\x00":
            preparation.set()
            await asyncio.Event().wait()
        if uuid == CONTROL_UUID and data == STOP:
            await asyncio.Event().wait()
        await original(uuid, data, response)

    with (
        patch.object(fake, "write_gatt_char", side_effect=paused_write),
        patch("custom_components.ha_linak.client.MOTION_IO_TIMEOUT", 0.01),
    ):
        operation = asyncio.create_task(desk.move_to_cm(83, settings))
        await asyncio.wait_for(preparation.wait(), timeout=1)
        with pytest.raises(MotionError):
            await desk.stop()
        with pytest.raises(TimeoutError):
            await operation
    assert desk.last_control_result == "stop_failed"
    assert not desk.connected
    assert not desk.control_busy
    assert not any(
        uuid == TARGET_UUID and payload != REFERENCE_STOP
        for uuid, payload in fake.writes
    )


async def test_position_notification_and_read_do_not_publish_identical_samples():
    from unittest.mock import Mock
    from custom_components.ha_linak.client import _LiveMotionTransport

    desk, fake = await connected_desk()
    desk.changed = Mock()
    data = bytearray(struct.pack("<HH", fake.position, 0))
    for _ in range(5):
        fake.callbacks[HEIGHT_UUID](None, data)
    assert await _LiveMotionTransport(desk).read_position() == desk.state.position
    desk.changed.assert_not_called()
    fake.position += 1
    data = bytearray(struct.pack("<HH", fake.position, 0))
    for _ in range(5):
        fake.callbacks[HEIGHT_UUID](None, data)
    await _LiveMotionTransport(desk).read_position()
    desk.changed.assert_called_once()
    await desk.disconnect()


async def test_slider_history_omits_intermediate_heights_and_keeps_live_sensor(hass):
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant.common import async_fire_time_changed

    entry, fake = await setup_entry(hass, OPTIONS)
    target_id = hass.states.async_all("number")[0].entity_id
    for position in (1500, 1600, 1700):
        fake.callbacks[HEIGHT_UUID](None, bytearray(struct.pack("<HH", position, 100)))
        await hass.async_block_till_done()
        assert hass.states.get(target_id).state == "82"
        assert entry.runtime_data.data.position.position_raw == position
    fake.callbacks[HEIGHT_UUID](None, bytearray(struct.pack("<HH", 1800, 0)))
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == "82"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == "86"
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("interrupt", ["movement", "disconnect", "unload"])
async def test_slider_cancels_pending_settlement_when_state_changes(hass, interrupt):
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant.common import async_fire_time_changed

    entry, fake = await setup_entry(hass, OPTIONS)
    target_id = hass.states.async_all("number")[0].entity_id
    fake.callbacks[HEIGHT_UUID](None, bytearray(struct.pack("<HH", 1600, 0)))
    await hass.async_block_till_done()
    if interrupt == "movement":
        fake.callbacks[HEIGHT_UUID](None, bytearray(struct.pack("<HH", 1700, 100)))
    elif interrupt == "disconnect":
        fake.is_connected = False
        entry.runtime_data.desk._disconnected(fake)
    else:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    state = hass.states.get(target_id)
    assert state is None or state.state != "84"
    if interrupt != "unload":
        await hass.config_entries.async_unload(entry.entry_id)


async def test_stop_reports_link_loss_before_worker_cleanup_without_retry():
    desk, fake = await connected_desk()
    fake.writes.clear()
    desk._motion_task = asyncio.create_task(asyncio.Event().wait())
    fake.is_connected = False
    with pytest.raises(MotionError, match="not delivered"):
        await desk.stop()
    assert desk.last_control_result == "stop_failed"
    assert fake.writes == []
    desk._motion_task = None
    await desk.disconnect()


async def test_slider_without_an_initial_measurement_has_no_invented_height(hass):
    from custom_components.ha_linak.client import DeskState
    from custom_components.ha_linak.number import LinakTargetHeight

    entry, _ = await setup_entry(hass, OPTIONS)
    entry.runtime_data.data = DeskState()
    number = LinakTargetHeight(entry.runtime_data)
    assert number.native_value is None
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("first_action", ["target", "memory"])
async def test_mixed_control_burst_is_rejected_without_queued_writes(
    hass, first_action
):
    entry, fake = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    fake.stall = True
    original_write = fake.write_gatt_char
    stop_entered, release_stop = asyncio.Event(), asyncio.Event()

    async def hold_stop(uuid, data, **kwargs):
        if uuid == CONTROL_UUID and data == STOP and fake.target_written.is_set():
            stop_entered.set()
            await release_stop.wait()
        await original_write(uuid, data, **kwargs)

    fake.write_gatt_char = hold_stop
    with patch("custom_components.ha_linak.motion.COMMAND_INTERVAL", 60):
        first = asyncio.create_task(
            coordinator.async_move_to_cm(83)
            if first_action == "target"
            else coordinator.async_move_to_memory(0)
        )
        await asyncio.wait_for(fake.target_written.wait(), 1)
        before = list(fake.writes)
        results = await asyncio.gather(
            *(coordinator.async_move_to_cm(84) for _ in range(12)),
            *(coordinator.async_move_to_memory(i % 4) for i in range(12)),
            return_exceptions=True,
        )
        assert all(isinstance(result, ServiceValidationError) for result in results)
        assert all(result.translation_key == "control_busy" for result in results)
        assert fake.writes == before
        stops = [asyncio.create_task(coordinator.async_stop()) for _ in range(12)]
        await asyncio.wait_for(stop_entered.wait(), 1)
        with pytest.raises(ServiceValidationError) as error:
            await coordinator.async_move_to_cm(84)
        assert error.value.translation_key == "control_busy"
        assert coordinator.desk.control_busy
        release_stop.set()
        await asyncio.gather(first, *stops)
    assert fake.writes[len(before) :] == [
        (CONTROL_UUID, STOP),
        (TARGET_UUID, REFERENCE_STOP),
    ]
    assert coordinator.desk.connected
    assert not coordinator.desk.control_busy
    # A new explicit request is accepted only after cleanup; rejected goals never run.
    fake.stall = False
    await coordinator.async_move_to_cm(83)
    assert coordinator.desk.last_control_result == "completed"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_native_stop_interrupts_service_without_false_action_error(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    target = hass.states.async_all("number")[0]
    stop = next(
        s for s in hass.states.async_all("button") if s.entity_id.endswith("_stop")
    )
    with patch("custom_components.ha_linak.motion.COMMAND_INTERVAL", 60):
        movement = asyncio.create_task(
            hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": target.entity_id, "value": 83},
                blocking=True,
            )
        )
        await asyncio.wait_for(fake.target_written.wait(), 1)
        await hass.services.async_call(
            "button", "press", {"entity_id": stop.entity_id}, blocking=True
        )
        await movement
    assert entry.runtime_data.desk.connected
    assert entry.runtime_data.desk.last_control_result in {"interrupted", "stop_sent"}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_stop_still_fails_both_ha_actions(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    with patch("custom_components.ha_linak.motion.COMMAND_INTERVAL", 60):
        movement = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        fake.fail_stop = True
        with pytest.raises(HomeAssistantError) as stop_error:
            await entry.runtime_data.async_stop()
        assert stop_error.value.translation_key == "stop_failed"
        with pytest.raises(HomeAssistantError) as movement_error:
            await movement
        assert movement_error.value.translation_key == "movement_failed"
    assert not fake.is_connected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unrequested_worker_cancellation_remains_a_ha_error(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    fake.stall = True
    with patch("custom_components.ha_linak.motion.COMMAND_INTERVAL", 60):
        movement = asyncio.create_task(entry.runtime_data.async_move_to_cm(83))
        await asyncio.wait_for(fake.target_written.wait(), 1)
        entry.runtime_data.desk._motion_task.cancel()
        with pytest.raises(HomeAssistantError) as error:
            await movement
        assert error.value.translation_key == "movement_failed"
    assert not fake.is_connected
    await hass.config_entries.async_unload(entry.entry_id)
