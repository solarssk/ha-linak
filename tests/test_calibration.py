"""Explicit calibration writes, confirmation snapshots and verified readback."""

import asyncio
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak.backends.device import BLEDevice

from custom_components.ha_linak.calibration import HeightCalibration, MEASURED_HEIGHT
from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.control_settings import ControlSettings
from custom_components.ha_linak.motion import MotionError
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID, PositionSample
from test_client import FakeBleak
from test_integration import prepare_setup

ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE = BLEDevice(ADDRESS, "Test desk", {})
BOUNDS = {"minimum_height": 61.2, "maximum_height": 126.2}


class CalibrationBleak(FakeBleak):
    def __init__(self):
        super().__init__()
        self.position = 1438
        self.speed = 0
        self.offset = 6800
        self.activation = 1
        self.identity = bytes(range(16))
        self.reject_setting = False
        self.ignore_write = False
        self.echo_write = False
        self.move_after_write = False
        self.hang_write = False
        self.write_started = asyncio.Event()
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: (
                SimpleNamespace(properties=["read", "write"])
                if uuid in (DPG_UUID, HEIGHT_UUID)
                else None
            )
        )

    async def read_gatt_char(self, uuid):
        assert uuid == HEIGHT_UUID
        return struct.pack("<HH", self.position, self.speed)

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == DPG_UUID
        assert response
        if data[1] == 0x86:
            self.writes.append((uuid, bytes(data)))
            if data[2] == 0:
                reply = b"\x01\x11" + bytes([self.activation]) + self.identity
            else:
                assert data == b"\x7f\x86\x80\x01" + self.identity
                if not self.reject_setting:
                    self.activation = 1
                reply = b"\x0b\x00" if self.reject_setting else b"\x01\x00"
            self.callbacks[DPG_UUID](None, bytearray(reply))
        elif data[2] == 0x80:
            if self.reject_setting:
                self.writes.append((uuid, bytes(data)))
                self.callbacks[DPG_UUID](None, bytearray(b"\x0b\x00"))
                return
            assert bytes(data[:4]) == b"\x7f\x81\x80\x01"
            assert len(data) == 6
            self.writes.append((uuid, bytes(data)))
            self.write_started.set()
            if not self.ignore_write:
                self.offset = struct.unpack("<H", data[4:])[0]
            if self.hang_write:
                await asyncio.Future()
            self.callbacks[DPG_UUID](None, bytearray(b"\x01\x00"))
            if self.echo_write:
                self.callbacks[DPG_UUID](None, bytearray(b"\x01\x03\x01" + data[4:]))
            if self.move_after_write:
                self.position += 1
        elif data[1] == 0x81:
            self.writes.append((uuid, bytes(data)))
            self.callbacks[DPG_UUID](
                None, bytearray(b"\x01\x03\x01" + struct.pack("<H", self.offset))
            )
        else:
            await super().write_gatt_char(uuid, data, response)


async def ready(fake=None):
    fake = fake or CalibrationBleak()
    desk = DeskClient(DEVICE, lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    return desk, fake


def writes(fake):
    return [data for _, data in fake.writes if data[2] == 0x80]


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), True, -1, 0, "75", 1, 1000, 1e308]
)
def test_invalid_or_unrepresentable_measurements(value):
    position = PositionSample(1438, 0)
    with pytest.raises(ValueError):
        HeightCalibration.prepare(position, 6800, value)


def test_measurement_and_wire_encoding_are_independent_of_travel_bounds():
    proposal = HeightCalibration.prepare(PositionSample(1438, 0), 6800, 75.6)
    assert proposal.new_offset_raw == 6122
    assert proposal.write_request() == b"\x7f\x81\x80\x01\xea\x17"
    settings = ControlSettings.from_options(BOUNDS)
    limits = settings.limits(proposal.new_offset_raw)
    assert limits.minimum_raw == 0
    assert limits.target(61.2, proposal.new_offset_raw) == 0
    with pytest.raises(ValueError):
        limits.target(61.1, proposal.new_offset_raw)
    with pytest.raises(ValueError):
        settings.limits(6800)


@pytest.mark.parametrize(
    "position,offset",
    [(None, 6800), (PositionSample(1438, 1), 6800), (PositionSample(1438, 0), None)],
)
def test_calibration_requires_stationary_valid_snapshot(position, offset):
    with pytest.raises(ValueError):
        HeightCalibration.prepare(position, offset, 75.6)


async def test_calibration_writes_only_offset_and_refreshes_all_conversions():
    desk, fake = await ready()
    positions = [memory.position_raw for memory in desk.state.memories]
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    state = await desk.calibrate_height(proposal)
    assert state.offset_raw == 6122
    assert state.height_cm == 75.6
    assert [memory.position_raw for memory in state.memories] == positions
    assert writes(fake) == [proposal.write_request()]
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)
    assert desk.connected
    await desk.disconnect()


@pytest.mark.parametrize("change", ["position", "offset", "speed", "properties"])
async def test_changed_snapshot_or_missing_operation_never_writes(change):
    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    if change == "position":
        fake.position += 20
    elif change == "offset":
        fake.offset += 10
    elif change == "speed":
        fake.speed = 1
    else:
        fake.services.get_characteristic = lambda uuid: None
    with pytest.raises((ValueError, MotionError)):
        await desk.calibrate_height(proposal)
    assert not writes(fake)
    assert not desk.connected


async def test_unavailable_preflight_position_never_activates_or_calibrates():
    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    fake.position = 0xFFFF
    fake.activation = 0
    with pytest.raises(ValueError, match="position is unavailable"):
        await desk.calibrate_height(proposal, activate_client=True)
    assert not writes(fake)
    assert fake.activation == 0
    assert fake.offset == 6800
    assert not desk.connected


async def test_successful_write_without_matching_readback_is_not_success():
    desk, fake = await ready()
    fake.ignore_write = True
    fake.echo_write = True
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    with pytest.raises(ValueError, match="readback"):
        await desk.calibrate_height(proposal)
    assert len(writes(fake)) == 1
    assert not desk.connected


async def test_unchanged_height_has_no_firmware_write():
    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 82.38
    )
    await desk.calibrate_height(proposal)
    assert not writes(fake)
    await desk.disconnect()


async def test_disconnect_cancels_owned_calibration_without_motion_or_retry():
    desk, fake = await ready()
    fake.hang_write = True
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    task = asyncio.create_task(desk.calibrate_height(proposal))
    await fake.write_started.wait()
    assert desk.control_busy
    count = len(fake.writes)
    assert await desk.refresh() is desk.state
    assert len(fake.writes) == count
    settings = ControlSettings.from_options(BOUNDS)
    with pytest.raises(MotionError):
        await desk.move_to_cm(80, settings)
    with pytest.raises(MotionError):
        await desk.calibrate_height(proposal)
    await desk.disconnect()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not desk.control_busy
    assert fake.offset == proposal.new_offset_raw
    assert len(writes(fake)) == 1
    assert all(uuid == DPG_UUID for uuid, _ in fake.writes)


async def submit_range(hass, result, values, options=False):
    """Follow the focused screens without bypassing HA schema validation."""
    manager = hass.config_entries.options if options else hass.config_entries.flow
    bounds = {key: value for key, value in values.items() if key != MEASURED_HEIGHT}
    if result["type"] == "menu":
        step = "height" if MEASURED_HEIGHT in values else "range"
        result = await manager.async_configure(
            result["flow_id"], {"next_step_id": step}
        )
    if result.get("step_id") in ("finish", "range"):
        result = await manager.async_configure(result["flow_id"], bounds)
        if result["type"] == "progress":
            await hass.async_block_till_done()
            result = await manager.async_configure(result["flow_id"])
    if result.get("step_id") == "height":
        result = await manager.async_configure(
            result["flow_id"], {"height_correct": MEASURED_HEIGHT not in values}
        )
    if result.get("step_id") == "measure":
        result = await manager.async_configure(
            result["flow_id"], {MEASURED_HEIGHT: values[MEASURED_HEIGHT]}
        )
    for _ in range(3):
        if result["type"] != "progress":
            break
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
    return result


async def initial_form(hass, fake, *, guide=True):
    from homeassistant.const import CONF_ADDRESS
    from custom_components.ha_linak.const import DOMAIN

    info = SimpleNamespace(
        address=ADDRESS,
        name="Test desk",
        device=DEVICE,
        service_uuids=["99fa0001-338a-1024-8a49-009c0215f78a"],
        connectable=True,
    )
    with patch(
        "custom_components.ha_linak.config_flow.bluetooth.async_discovered_service_info",
        return_value=[info],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    return await prepare_setup(hass, result) if guide else result


async def test_onboarding_calibrates_before_validating_measured_bounds(hass):
    fake = CalibrationBleak()
    with (
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
        result = await initial_form(hass, fake)
        result = await submit_range(hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6})
        assert result["step_id"] == "calibration_confirm"
        assert result["description_placeholders"]["old_height"] == "82.4"
        assert not writes(fake)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == "progress"
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] == "create_entry"
        assert result["options"] == BOUNDS
        assert len(writes(fake)) == 1
        from custom_components.ha_linak.setup_session import take_session

        session = take_session(hass, ADDRESS)
        assert session is not None
        await session.disconnect()
        assert not fake.is_connected
        await hass.async_block_till_done()


async def test_aborting_calibration_confirmation_never_writes(hass):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        result = await initial_form(hass, fake)
        result = await submit_range(hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6})
        hass.config_entries.flow.async_abort(result["flow_id"])
    assert not writes(fake)


async def test_position_change_after_confirmation_preview_rejects_write(hass):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        result = await initial_form(hass, fake)
        result = await submit_range(hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6})
        fake.position += 50
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["errors"] == {"base": "calibration_snapshot_changed"}
        assert not writes(fake)
        assert not hass.config_entries.async_entries("ha_linak")
        hass.config_entries.flow.async_abort(result["flow_id"])


async def test_options_calibration_refreshes_reference_without_storing_write_input(
    hass,
):
    from pytest_homeassistant.common import MockConfigEntry
    from homeassistant.const import CONF_ADDRESS
    from custom_components.ha_linak.const import DOMAIN

    fake = CalibrationBleak()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: ADDRESS},
        unique_id=ADDRESS,
        options={"minimum_height": 70, "maximum_height": 125},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await submit_range(
            hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6}, options=True
        )
        assert result["step_id"] == "calibration_confirm"
        assert not writes(fake)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert dict(entry.options) == {"minimum_height": 70, "maximum_height": 125}
        assert entry.runtime_data.data.offset_raw == 6122
        assert len(writes(fake)) == 1
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_write_timeout_never_retries_or_restores_a_setting():
    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    fake.hang_write = True
    with patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.01):
        with pytest.raises(TimeoutError):
            await desk.calibrate_height(proposal)
    assert fake.offset == proposal.new_offset_raw
    assert len(writes(fake)) == 1
    assert not desk.connected


async def test_movement_during_position_check_prevents_calibration_write():
    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    original = fake.read_gatt_char
    calls = 0

    async def moving(uuid):
        nonlocal calls
        calls += 1
        if calls == 2:
            fake.position += 1
        return await original(uuid)

    fake.read_gatt_char = moving
    with pytest.raises(ValueError, match="position or reference changed"):
        await desk.calibrate_height(proposal)
    assert not writes(fake)


async def test_onboarding_rejects_bad_measurement_without_confirming_or_writing(hass):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        result = await initial_form(hass, fake)
        result = await submit_range(hass, result, BOUNDS | {MEASURED_HEIGHT: 1})
        assert result["errors"] == {"base": "invalid_measurement"}
        assert not writes(fake)
        hass.config_entries.flow.async_abort(result["flow_id"])


async def test_position_change_during_write_invalidates_readback():
    desk, fake = await ready()
    fake.move_after_write = True
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    with pytest.raises(ValueError, match="readback"):
        await desk.calibrate_height(proposal)
    assert len(writes(fake)) == 1
    assert not desk.connected


async def test_display_rounding_does_not_require_a_pointless_write(hass):
    fake = CalibrationBleak()
    with (
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
        result = await initial_form(hass, fake)
        result = await submit_range(
            hass,
            result,
            {"minimum_height": 70, "maximum_height": 125, MEASURED_HEIGHT: 82.4},
        )
        assert result["type"] == "create_entry"
        assert not writes(fake)
        assert MEASURED_HEIGHT not in result["options"]
        await hass.async_block_till_done()


async def setup_calibration_entry(hass, fake):
    from pytest_homeassistant.common import MockConfigEntry
    from homeassistant.const import CONF_ADDRESS
    from custom_components.ha_linak.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: ADDRESS},
        unique_id=ADDRESS,
        options={"minimum_height": 70, "maximum_height": 125},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_reports_measurement_error_and_failed_verification(hass):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        entry = await setup_calibration_entry(hass, fake)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await submit_range(
            hass, result, BOUNDS | {MEASURED_HEIGHT: 1}, options=True
        )
        assert result["errors"] == {"base": "invalid_measurement"}
        result = await submit_range(
            hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6}, options=True
        )
        fake.ignore_write = True
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        assert result["step_id"] == "height"
        assert result["errors"] == {"base": "calibration_failed"}
        assert len(writes(fake)) == 1
        assert entry.options["minimum_height"] == 70
        hass.config_entries.options.async_abort(result["flow_id"])
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_verified_calibration_does_not_save_invalid_range_or_repeat_write(hass):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        entry = await setup_calibration_entry(hass, fake)
        hass.config_entries.async_update_entry(
            entry, options={"minimum_height": 70, "maximum_height": 74}
        )
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await submit_range(
            hass,
            result,
            BOUNDS | {"maximum_height": 74, MEASURED_HEIGHT: 75.6},
            options=True,
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        assert result["errors"] == {"base": "invalid_limits"}
        assert entry.runtime_data.data.offset_raw == 6122
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], BOUNDS
        )
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert len(writes(fake)) == 1
        assert dict(entry.options) == BOUNDS
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_abort_drains_an_ambiguous_write_without_replay(hass):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        entry = await setup_calibration_entry(hass, fake)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await submit_range(
            hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6}, options=True
        )
        fake.hang_write = True
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        await fake.write_started.wait()
        again = await hass.config_entries.options.async_configure(result["flow_id"])
        assert again["type"] == "progress"
        hass.config_entries.options.async_abort(result["flow_id"])
        await asyncio.wait_for(fake.disconnected.wait(), timeout=1)
        await hass.async_block_till_done()
        assert not fake.is_connected
        assert len(writes(fake)) == 1
        assert fake.offset == 6122
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_changed_reference_disables_unrepresentable_bounds_but_keeps_sensors(
    hass,
):
    fake = CalibrationBleak()
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
    ):
        entry = await setup_calibration_entry(hass, fake)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await submit_range(
            hass, result, BOUNDS | {MEASURED_HEIGHT: 85.6}, options=True
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        assert result["errors"] == {"base": "invalid_limits"}
        assert entry.runtime_data.controls is None
        assert entry.runtime_data.last_update_success
        assert entry.runtime_data.data.height_cm == 85.6
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"minimum_height": 71.3, "maximum_height": 130}
        )
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.controls is not None
        assert len(writes(fake)) == 1
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "values",
    [
        (-1, 1438, 6122),
        (6800, 65535, 6122),
        (6800, 1438, 65535),
        (True, 1438, 6122),
        (6800, 1438, 61.2),
    ],
)
def test_calibration_plan_rejects_invalid_wire_words(values):
    with pytest.raises(ValueError):
        HeightCalibration(*values)


async def test_calibration_notifications_publish_only_verified_reference():
    desk, fake = await ready()
    published = []
    desk.changed = lambda: published.append(desk.state.height_cm)
    original = fake.write_gatt_char

    async def notify_during_write(uuid, data, response):
        await original(uuid, data, response)
        if data[2] == 0x80:
            desk._position(
                desk._generation, bytearray(struct.pack("<HH", fake.position, 0))
            )
            assert not published

    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.6
    )
    with patch.object(fake, "write_gatt_char", side_effect=notify_during_write):
        await desk.calibrate_height(proposal)
    assert published
    assert all(height == 75.6 for height in published)
    await desk.disconnect()


async def test_onboarding_recovers_after_delivered_write_without_replaying(hass):
    fake = CalibrationBleak()
    original = fake.write_gatt_char

    async def lose_confirmation(uuid, data, response):
        await original(uuid, data, response)
        if data[2] == 0x80:
            raise ConnectionError("Simulated acknowledgement loss")

    with (
        patch(
            "custom_components.ha_linak.config_flow.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            side_effect=fake.reconnect,
        ),
        patch.object(fake, "write_gatt_char", side_effect=lose_confirmation),
        patch("custom_components.ha_linak.async_setup_entry", return_value=True),
    ):
        result = await initial_form(hass, fake)
        result = await submit_range(hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] == "form"
        assert result["step_id"] == "height"
        assert result["errors"] == {"base": "calibration_failed"}
        assert result["description_placeholders"]["height"] == "76"
        assert len(writes(fake)) == 1
        result = await submit_range(hass, result, BOUNDS | {MEASURED_HEIGHT: 75.6})
        assert result["type"] == "create_entry"
        assert len(writes(fake)) == 1
        await hass.async_block_till_done()


@pytest.mark.parametrize("delta", [-2, -1, 1, 2])
async def test_preview_quantization_keeps_fresh_stationary_checks_strict(delta):
    desk, fake = await ready()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    fake.position += delta
    if abs(delta) == 1:
        state = await desk.calibrate_height(proposal)
        assert state.offset_raw == proposal.new_offset_raw
        assert state.height_cm == pytest.approx(75.5 + delta / 100)
        assert writes(fake) == [proposal.write_request()]
    else:
        with pytest.raises(ValueError):
            await desk.calibrate_height(proposal)
        assert not writes(fake)
    await desk.disconnect()


async def test_confirmed_guest_activation_preserves_identity_and_precedes_offset():
    desk, fake = await ready()
    fake.activation = 0
    before = fake.identity
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    state = await desk.calibrate_height(proposal)
    assert writes(fake) == [b"\x7f\x86\x80\x01" + before, proposal.write_request()]
    assert fake.identity == before
    assert fake.activation == 1
    assert state.height_cm == 75.5
    await desk.disconnect()


@pytest.mark.parametrize("active", [0, 1])
async def test_panel_rejection_discards_session_without_retry(active):
    from custom_components.ha_linak.calibration import SettingRejected

    desk, fake = await ready()
    fake.activation = active
    fake.reject_setting = True
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    with pytest.raises(SettingRejected, match="0b"):
        await desk.calibrate_height(proposal)
    assert len(writes(fake)) == 1
    assert fake.offset == 6800
    assert not desk.connected


async def test_activation_readback_must_preserve_identity():
    desk, fake = await ready()
    fake.activation = 0
    original = fake.write_gatt_char

    async def change_identity(uuid, data, response):
        await original(uuid, data, response)
        if data[:3] == b"\x7f\x86\x80":
            fake.identity = bytes(reversed(fake.identity))

    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    with patch.object(fake, "write_gatt_char", side_effect=change_identity):
        with pytest.raises(ValueError, match="activation was not verified"):
            await desk.calibrate_height(proposal)
    assert len(writes(fake)) == 1
    assert fake.offset == 6800
    assert not desk.connected


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x01\x11\x00" + bytes(16),
        b"\x01\x11\x02" + bytes(range(16)),
        b"\x01\x11\x00" + b"\xff" * 16,
    ],
)
def test_activation_rejects_unusable_identity(payload):
    from custom_components.ha_linak.protocol import activation_request

    with pytest.raises(ValueError):
        activation_request(payload)


async def test_refresh_and_unchanged_calibration_do_not_activate_guest():
    desk, fake = await ready()
    fake.activation = 0
    await desk.refresh()
    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, desk.state.height_cm
    )
    await desk.calibrate_height(proposal)
    assert not writes(fake)
    assert fake.activation == 0
    await desk.disconnect()


async def test_cancelled_activation_is_not_replayed_or_followed_by_offset():
    desk, fake = await ready()
    fake.activation = 0
    started = asyncio.Event()
    original = fake.write_gatt_char

    async def hang_after_activation(uuid, data, response):
        await original(uuid, data, response)
        if data[:3] == b"\x7f\x86\x80":
            started.set()
            await asyncio.Future()

    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    with patch.object(fake, "write_gatt_char", side_effect=hang_after_activation):
        task = asyncio.create_task(desk.calibrate_height(proposal))
        await started.wait()
        await desk.disconnect()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert fake.activation == 1
    assert fake.offset == 6800
    assert len(writes(fake)) == 1
    assert not desk.connected


async def test_position_change_during_activation_prevents_offset_write():
    desk, fake = await ready()
    fake.activation = 0
    original = fake.write_gatt_char

    async def move_after_activation(uuid, data, response):
        await original(uuid, data, response)
        if data[:3] == b"\x7f\x86\x80":
            fake.position += 1

    proposal = HeightCalibration.prepare(
        desk.state.position, desk.state.offset_raw, 75.5
    )
    with patch.object(fake, "write_gatt_char", side_effect=move_after_activation):
        with pytest.raises(ValueError, match="during activation"):
            await desk.calibrate_height(proposal)
    assert len(writes(fake)) == 1
    assert fake.offset == 6800
    assert not desk.connected


async def test_setting_transport_rejects_non_allowlisted_payload():
    desk, fake = await ready()
    before = len(fake.writes)
    with pytest.raises(ValueError, match="Unsupported setting"):
        await desk._write_setting(b"\x7f\x89\x80\x01\x00\x00")
    assert len(fake.writes) == before
    await desk.disconnect()
