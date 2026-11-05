"""The slider follows the measured height after the integration's own movement."""

import struct
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from test_native_controls import OPTIONS, setup_entry


async def test_slider_follows_a_stored_position_move_that_ends_with_residual_speed(
    hass,
):
    entry, fake = await setup_entry(hass, OPTIONS)
    target_id = hass.states.async_all("number")[0].entity_id
    memory = next(
        s
        for s in hass.states.async_all("button")
        if s.entity_id.endswith("_position_1")
    )

    async def read_with_residual_speed(_uuid):
        return struct.pack("<HH", fake.position, 3)

    fake.read_gatt_char = read_with_residual_speed
    assert hass.states.get(target_id).state == "82"
    await hass.services.async_call(
        "button", "press", {"entity_id": memory.entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    assert entry.runtime_data.data.height_cm == 80.04
    assert hass.states.get(target_id).state == "80"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_slider_ignores_panel_movement_while_the_previous_result_is_shown(hass):
    entry, fake = await setup_entry(hass, OPTIONS)
    target_id = hass.states.async_all("number")[0].entity_id
    coordinator = entry.runtime_data
    await coordinator.async_move_to_cm(75)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    assert coordinator.desk.operation.status.settled
    before = hass.states.get(target_id).state
    fake.callbacks["99fa0021-338a-1024-8a49-009c0215f78a"](
        None, bytearray(struct.pack("<HH", 1700, 4))
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == before
    await hass.config_entries.async_unload(entry.entry_id)
