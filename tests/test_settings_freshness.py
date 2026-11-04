"""Optional group validity without hiding transport or reference failures."""

import struct
from unittest.mock import patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.protocol import DPG_UUID
from custom_components.ha_linak.motion import TARGET_UUID, REFERENCE_STOP
from test_client import FakeBleak, CAPTURE
from test_native_controls import MotionBleak, OPTIONS, setup_entry


class GroupReplies(MotionBleak):
    corrupt = None
    silent = None

    async def write_gatt_char(self, uuid, data, response):
        if uuid == DPG_UUID and data[1] in (self.corrupt, self.silent):
            self.writes.append((uuid, bytes(data)))
            if data[1] != self.silent:
                response_type = 11 if data[1] == 0x88 else 7
                self.callbacks[DPG_UUID](None, bytearray((1, response_type, 255)))
            return
        await super().write_gatt_char(uuid, data, response)


@pytest.mark.parametrize("slots", [0, 1, 2, 4])
async def test_only_reported_memory_slots_are_queried(slots):
    class SlotReplies(FakeBleak):
        async def write_gatt_char(self, uuid, data, response):
            if data[1] == 0x80:
                self.writes.append((uuid, bytes(data)))
                reply = bytearray.fromhex(CAPTURE["80"])
                reply[2] = (reply[2] & ~7) | slots
                self.callbacks[DPG_UUID](None, reply)
            else:
                await super().write_gatt_char(uuid, data, response)

    fake = SlotReplies()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        state = await desk.refresh()
    assert len(state.memories) == slots
    assert [data[1] for _, data in fake.writes if 0x89 <= data[1] <= 0x8C] == list(
        range(0x89, 0x89 + slots)
    )
    assert desk.settings_health["memories"].valid
    await desk.disconnect()


@pytest.mark.parametrize(
    "command,group,entity_suffix",
    [
        (0x88, "reminders", "_active_reminder_profile"),
        (0x8A, "memories", "_stored_height_1"),
    ],
)
async def test_bad_optional_group_does_not_hide_height_or_other_group(
    hass, command, group, entity_suffix
):
    fake = GroupReplies()
    # setup_entry constructs its own fake; substitute only the transport class.
    with patch("test_native_controls.MotionBleak", return_value=fake):
        entry, _ = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    desk = coordinator.desk
    desk.settings_health[group].last_success -= 301
    last_success = desk.settings_health[group].last_success
    old_memories = list(desk.state.memories)
    old_reminders = desk.state.reminders
    fake.corrupt = command
    fake.position = 1500
    with patch(
        "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
        return_value=desk.device,
    ):
        await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert desk.connected
    assert desk.state.height_cm == 83
    assert not desk.settings_health[group].valid
    assert desk.settings_health[group].last_success == last_success
    assert desk.settings_health[group].error == "invalid_response"
    assert desk.settings_health[
        "reminders" if group == "memories" else "memories"
    ].valid
    affected = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith(entity_suffix)
    )
    height = next(
        s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_height")
    )
    assert affected.state == "unavailable"
    assert height.state == "83"
    if group == "memories":
        assert desk.state.memories == old_memories
    else:
        assert desk.state.reminders == old_reminders
    # A later validated reply restores only the affected group's validity.
    fake.corrupt = None
    with patch(
        "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
        return_value=desk.device,
    ):
        await coordinator.async_refresh()
    assert desk.settings_health[group].valid
    assert desk.settings_health[group].error is None
    assert hass.states.get(affected.entity_id).state != "unavailable"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_memory_travel_never_uses_invalid_cached_slot(hass):
    fake = GroupReplies()
    with patch("test_native_controls.MotionBleak", return_value=fake):
        entry, _ = await setup_entry(hass, OPTIONS)
    fake.corrupt = 0x89
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_move_to_memory(0)
    assert not any(
        uuid == TARGET_UUID and data != REFERENCE_STOP for uuid, data in fake.writes
    )
    assert not fake.is_connected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_strict_refresh_rejects_malformed_optional_group():
    fake = GroupReplies()
    fake.corrupt = 0x88
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with (
        patch(
            "custom_components.ha_linak.client.establish_connection", return_value=fake
        ),
        pytest.raises(ValueError),
    ):
        await desk.refresh()
    assert not desk.connected
    assert desk.state.offset_raw is None


async def test_settings_age_and_link_loss_validity():
    fake = GroupReplies()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    assert desk.settings_diagnostics()["reminders"] == {
        "valid": False,
        "age_seconds": None,
        "error": None,
    }
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    read_at = desk.settings_health["reminders"].last_success
    with patch(
        "custom_components.ha_linak.client.monotonic", return_value=read_at + 30
    ):
        assert desk.settings_diagnostics()["reminders"]["age_seconds"] == 30
    desk._disconnected(fake)
    assert not desk.settings_diagnostics()["reminders"]["valid"]
    await desk.disconnect()


@pytest.mark.parametrize(
    "command,payload",
    [
        (0x80, b"\x01\x02\xff\x01"),
        (0x81, b"\x01\x03\x00\x00\x00"),
    ],
)
@pytest.mark.parametrize("with_baseline", [False, True])
async def test_partial_policy_cannot_hide_invalid_required_data(
    command, payload, with_baseline
):
    class BadBaseline(FakeBleak):
        invalid = False

        async def write_gatt_char(self, uuid, data, response):
            if self.invalid and data[1] == command:
                self.callbacks[DPG_UUID](None, bytearray(payload))
            else:
                await super().write_gatt_char(uuid, data, response)

    fake = BadBaseline()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        if with_baseline:
            await desk.refresh()
            assert desk.state.offset_raw is not None
        baseline = desk.state
        fake.invalid = True
        with pytest.raises(ValueError):
            await desk.refresh(allow_partial_settings=True)
    assert not desk.connected
    assert desk.state is baseline
    if not with_baseline:
        assert desk.state.offset_raw is None


async def test_failed_reduced_slot_snapshot_never_keeps_removed_slots():
    class ShrinkingSlots(GroupReplies):
        slots = 4

        async def write_gatt_char(self, uuid, data, response):
            if uuid == DPG_UUID and data[1] == 0x80:
                reply = bytearray.fromhex(CAPTURE["80"])
                reply[2] = (reply[2] & ~7) | self.slots
                self.callbacks[DPG_UUID](None, reply)
            else:
                await super().write_gatt_char(uuid, data, response)

    fake = ShrinkingSlots()
    desk = DeskClient(BLEDevice("AA:BB:CC:DD:EE:FF", "Desk", {}), lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
        fake.slots = 2
        fake.corrupt = 0x89
        await desk.refresh(allow_partial_settings=True)
    assert desk.state.capabilities.memory_slots == 2
    assert len(desk.state.memories) == 2
    assert not desk.settings_health["memories"].valid
    await desk.disconnect()


async def test_memory_move_requires_group_recovery_then_reads_changed_slot(hass):
    class ChangedMemory(GroupReplies):
        fresh_slot = None

        async def write_gatt_char(self, uuid, data, response):
            if uuid == DPG_UUID and data[1] == 0x89 and self.fresh_slot is not None:
                self.writes.append((uuid, bytes(data)))
                payload = b"\x01\x07\x01" + struct.pack("<HI", self.fresh_slot, 1)
                self.callbacks[DPG_UUID](None, bytearray(payload))
                return
            await super().write_gatt_char(uuid, data, response)

    fake = ChangedMemory()
    with patch("test_native_controls.MotionBleak", return_value=fake):
        entry, _ = await setup_entry(hass, OPTIONS)
    desk = entry.runtime_data.desk
    cached = desk.state.memories[0].position_raw
    fake.corrupt = 0x89
    await desk.refresh(allow_partial_settings=True)
    assert not desk.settings_health["memories"].valid
    assert desk.state.memories[0].position_raw == cached
    fake.corrupt = None
    fake.fresh_slot = 1600
    assert fake.fresh_slot != cached
    fake.writes.clear()
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_move_to_memory(0)
    assert not fake.writes
    await desk.refresh(allow_partial_settings=True)
    await entry.runtime_data.async_move_to_memory(0)
    targets = [
        data
        for uuid, data in fake.writes
        if uuid == TARGET_UUID and data != REFERENCE_STOP
    ]
    assert targets
    assert all(data == struct.pack("<H", fake.fresh_slot) for data in targets)
    assert desk.state.memories[0].position_raw == fake.fresh_slot
    await hass.config_entries.async_unload(entry.entry_id)
