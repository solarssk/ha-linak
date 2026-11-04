"""Reference polling and settings ages use separate read schedules."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID
from test_native_controls import connected_desk, setup_entry, OPTIONS
from test_settings_freshness import GroupReplies


def queries(fake):
    return [data[1] for uuid, data in fake.writes if uuid == DPG_UUID]


# A whole second beyond the interval: monotonic times are floats, so an age of
# exactly 300 can compute as 299.99999999999994 on a freshly booted runner.
@pytest.mark.parametrize("elapsed,settings_due", [(299, False), (301, True)])
async def test_only_due_settings_are_read_and_skipped_reads_keep_age(
    elapsed, settings_due
):
    desk, fake = await connected_desk()
    before = {
        name: health.last_success for name, health in desk.settings_health.items()
    }
    fake.writes.clear()
    with patch(
        "custom_components.ha_linak.client.monotonic",
        return_value=max(before.values()) + elapsed,
    ):
        await desk.refresh(allow_partial_settings=True, settings_interval=300)
        ages = desk.settings_diagnostics()
    assert queries(fake) == (
        [0x80, 0x81, 0x89, 0x80, 0x8A, 0x80, 0x8B, 0x80, 0x8C, 0x88]
        if settings_due
        else [0x80, 0x81]
    )
    for group, health in desk.settings_health.items():
        assert health.valid
        if settings_due:
            assert health.last_success > before[group]
        else:
            assert health.last_success == before[group]
            assert ages[group]["age_seconds"] >= elapsed
    await desk.disconnect()


async def test_one_invalid_group_retries_without_rereading_other_settings():
    desk, fake = await connected_desk()
    desk.settings_health["reminders"].valid = False
    memories_at = desk.settings_health["memories"].last_success
    fake.writes.clear()
    await desk.refresh(allow_partial_settings=True, settings_interval=300)
    assert queries(fake) == [0x80, 0x81, 0x88]
    assert desk.settings_health["reminders"].valid
    assert desk.settings_health["memories"].last_success == memories_at
    await desk.disconnect()


async def test_reconnect_reads_all_settings_even_before_interval():
    desk, fake = await connected_desk()
    await desk.disconnect()
    fake.reconnect()
    fake.writes.clear()
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh(allow_partial_settings=True, settings_interval=300)
    assert len(queries(fake)) == 10
    assert all(health.valid for health in desk.settings_health.values())
    await desk.disconnect()


async def test_strict_foreground_read_does_not_skip_settings():
    desk, fake = await connected_desk()
    fake.writes.clear()
    await desk.refresh(settings_interval=300)
    assert len(queries(fake)) == 10
    await desk.disconnect()


async def test_due_settings_timeout_recovers_height_and_preserves_last_success():
    fake = GroupReplies()
    desk, _ = await connected_desk(fake)
    last = desk.settings_health["reminders"].last_success
    desk.settings_health["reminders"].valid = False
    fake.silent = 0x88
    replacement = GroupReplies()
    with (
        patch("custom_components.ha_linak.client.QUERY_TIMEOUT", 0.01),
        patch(
            "custom_components.ha_linak.client.establish_connection",
            return_value=replacement,
        ),
    ):
        await desk.refresh(allow_partial_settings=True, settings_interval=300)
    assert desk.connected
    assert fake.disconnected.is_set()
    assert desk.settings_health["reminders"].last_success == last
    assert not desk.settings_health["reminders"].valid
    assert desk.settings_health["memories"].valid
    await desk.disconnect()


async def test_notifications_do_not_postpone_scheduled_reference_read(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    desk = entry.runtime_data.desk
    with patch(
        "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
        return_value=desk.device,
    ):
        now = dt_util.utcnow()
        async_fire_time_changed(hass, now + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)
        fake.callbacks[HEIGHT_UUID](None, bytearray.fromhex("e8030000"))
        fake.writes.clear()
        async_fire_time_changed(hass, now + timedelta(seconds=61))
        await hass.async_block_till_done(wait_background_tasks=True)
        assert queries(fake) == [0x80, 0x81]
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("command", [0x80, 0x81])
async def test_changed_reference_or_capabilities_forces_settings_read(command):
    class ChangedReference(GroupReplies):
        async def write_gatt_char(self, uuid, data, response):
            if uuid == DPG_UUID and data[1] == command:
                self.writes.append((uuid, bytes(data)))
                payload = "0102fa01" if command == 0x80 else "010301f419"
                self.callbacks[DPG_UUID](None, bytearray.fromhex(payload))
                return
            await super().write_gatt_char(uuid, data, response)

    desk, _ = await connected_desk()
    await desk.disconnect()
    fake = ChangedReference()
    # Reuse a ready generation to exercise a change rather than reconnect forcing.
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    if command == 0x80:
        from custom_components.ha_linak.protocol import decode_capabilities

        desk.state.capabilities = decode_capabilities(bytes.fromhex("0102fc01"))
    else:
        desk.state.offset_raw += 100
    fake.writes.clear()
    await desk.refresh(allow_partial_settings=True, settings_interval=300)
    assert 0x89 in queries(fake)
    assert 0x88 in queries(fake)
    await desk.disconnect()


@pytest.mark.parametrize("missing_data", [False, True])
async def test_notification_can_restore_coordinator_after_error_or_missing_data(
    hass, missing_data
):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    entry, _ = await setup_entry(hass, OPTIONS)
    coordinator = entry.runtime_data
    if missing_data:
        coordinator.data = None
    else:
        coordinator.async_set_update_error(UpdateFailed("test refresh failure"))
    coordinator._changed()
    assert coordinator.last_update_success
    assert coordinator.data is coordinator.desk.state
    await hass.config_entries.async_unload(entry.entry_id)
