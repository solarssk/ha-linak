"""Identity is metadata, protocol compatibility is observed, neither is a MAC."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak.exc import BleakError

from custom_components.ha_linak.client import DeskClient
from custom_components.ha_linak.device_profile import (
    DeviceIdentity,
    Family,
    FIRMWARE_UUID,
    MODEL_UUID,
    UnsupportedFamily,
    metadata_text,
)
from custom_components.ha_linak.protocol import DPG_UUID, HEIGHT_UUID
from test_client import FakeBleak
from test_integration import DEVICE


class IdentityBleak(FakeBleak):
    def __init__(self, model=b"DPG1C", firmware=b"1.2.3"):
        super().__init__()
        self.metadata = {MODEL_UUID: model, FIRMWARE_UUID: firmware}
        self.reads = []
        self.services = SimpleNamespace(
            get_characteristic=lambda uuid: (
                SimpleNamespace(properties=["read"])
                if uuid in (DPG_UUID, HEIGHT_UUID, *self.metadata)
                else None
            )
        )

    async def read_gatt_char(self, uuid):
        self.reads.append(uuid)
        if uuid in self.metadata:
            value = self.metadata[uuid]
            if isinstance(value, Exception):
                raise value
            return value
        return await super().read_gatt_char(uuid)


@pytest.mark.parametrize(
    "raw,family,model",
    [
        (b"DPG", Family.DPG, "DPG"),
        (b"dpg1c\x00", Family.DPG, "DPG1C"),
        (b"DPG1M", Family.DPG, "DPG1M"),
        (b"DPG1C32-000016", Family.DPG, "DPG1C"),
        (b"DPI1C", Family.DPI, "DPI1C"),
        (b"", Family.UNKNOWN, None),
        (b"\xff", Family.UNKNOWN, None),
        (b"Private product SERIAL123", Family.OTHER, None),
    ],
)
def test_model_identity_uses_standard_field_only(raw, family, model):
    identity = DeviceIdentity.from_metadata(raw, b"1.2.3")
    assert identity.family is family
    assert identity.model == model
    assert identity.firmware == "1.2.3"
    assert "Private" not in json.dumps(identity.diagnostics(False))


@pytest.mark.parametrize("raw", [b"x" * 65, b"\xff", b"bad\x00inside", b"\n"])
def test_invalid_metadata_is_not_published(raw):
    assert metadata_text(raw) is None


def test_firmware_does_not_export_free_text_or_identifiers():
    identity = DeviceIdentity.from_metadata(b"DPG", b"Private desk AA:BB:CC:DD:EE:FF")
    assert identity.firmware is None
    assert identity.diagnostics(True)["hardware_validation"] == "not_inferred"


async def refresh(fake):
    desk = DeskClient(DEVICE, lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    return desk


async def test_identity_is_read_once_per_session_without_changing_query_sequence():
    fake = IdentityBleak()
    desk = await refresh(fake)
    assert desk.identity.model == "DPG1C"
    assert desk.protocol_validated
    assert len(fake.writes) == 10
    assert fake.reads.count(MODEL_UUID) == 1
    await desk.refresh()
    assert fake.reads.count(MODEL_UUID) == 1
    await desk.disconnect()
    fake.reconnect()
    fake.metadata[MODEL_UUID] = b"DPG1B"
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        await desk.refresh()
    assert desk.identity.model == "DPG1B"
    assert fake.reads.count(MODEL_UUID) == 2
    await desk.disconnect()


@pytest.mark.parametrize("model", [b"DPI1C", b"TD3", b"OTHER PRODUCT"])
async def test_identified_unsupported_family_never_receives_dpg_commands(model):
    fake = IdentityBleak(model)
    desk = DeskClient(DEVICE, lambda: None)
    with patch(
        "custom_components.ha_linak.client.establish_connection", return_value=fake
    ):
        with pytest.raises(UnsupportedFamily):
            await desk.refresh()
    assert not fake.writes
    assert fake.reads == [MODEL_UUID]
    assert not fake.callbacks
    assert not fake.is_connected
    assert not desk.protocol_validated
    assert desk.identity.family in (Family.DPI, Family.OTHER)


async def test_missing_dis_preserves_existing_protocol_probe_without_inventing_model():
    fake = FakeBleak()
    desk = await refresh(fake)
    assert desk.identity.family is Family.UNKNOWN
    assert desk.identity.model is None
    assert desk.protocol_validated
    await desk.disconnect()


async def test_denied_metadata_is_optional_but_transport_timeout_is_not():
    denied = IdentityBleak(model=BleakError("Private failure"))
    desk = await refresh(denied)
    assert desk.identity.family is Family.UNKNOWN
    await desk.disconnect()

    class StalledIdentity(IdentityBleak):
        async def read_gatt_char(self, uuid):
            await asyncio.Event().wait()

    fake = StalledIdentity()
    with patch("custom_components.ha_linak.client.IO_TIMEOUT", 0.001):
        with pytest.raises(TimeoutError):
            await refresh(fake)
    assert not fake.is_connected
    assert not fake.writes


def test_unsupported_family_has_a_distinct_setup_error():
    from custom_components.ha_linak.config_flow import _validation_error

    assert (
        _validation_error(UnsupportedFamily(), "device_identity")
        == "unsupported_family"
    )


async def test_ha_uses_reported_model_and_redacted_profile_diagnostics(hass):
    from custom_components.ha_linak.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    from custom_components.ha_linak.sensor import LinakSensor
    from test_native_controls import OPTIONS
    from pytest_homeassistant.common import MockConfigEntry
    from homeassistant.helpers import device_registry as dr

    fake = IdentityBleak()
    entry = MockConfigEntry(
        domain="ha_linak",
        title="Desk",
        unique_id=DEVICE.address,
        data={"address": DEVICE.address},
        options=OPTIONS,
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
    coordinator = entry.runtime_data
    sensor = LinakSensor(coordinator, "height")
    assert sensor.device_info["model"] == "DPG1C"
    assert sensor.device_info["sw_version"] == "1.2.3"
    device = next(
        item
        for item in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        if ("ha_linak", DEVICE.address) in item.identifiers
    )
    assert device.model == "DPG1C"
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["device_profile"]["driver"] == "dpg"
    assert result["device_profile"]["family"] == "dpg"
    assert result["device_profile"]["hardware_validation"] == "not_inferred"
    assert DEVICE.address not in json.dumps(result)
    await coordinator.desk.disconnect()
    fake.reconnect()
    fake.metadata[MODEL_UUID] = b"DPG1B"
    with (
        patch(
            "custom_components.ha_linak.coordinator.bluetooth.async_ble_device_from_address",
            return_value=DEVICE,
        ),
        patch(
            "custom_components.ha_linak.client.establish_connection", return_value=fake
        ),
    ):
        await coordinator.async_refresh()
    assert dr.async_get(hass).async_get(device.id).model == "DPG1B"
    assert sensor.device_info["model"] == "DPG1B"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_identity_registry_update_leaves_other_devices_and_owner_name_alone(hass):
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry
    from custom_components.ha_linak.coordinator import LinakCoordinator

    entry = MockConfigEntry(domain="ha_linak", data={"address": DEVICE.address})
    entry.add_to_hass(hass)
    coordinator = LinakCoordinator(hass, entry)
    coordinator._update_device_identity()
    desk = DeskClient(DEVICE, lambda: None)
    desk.identity = DeviceIdentity.from_metadata(b"DPG1C", b"1.2.3")
    coordinator.desk = desk
    registry = dr.async_get(hass)
    own = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("ha_linak", DEVICE.address)},
        model="DPG",
    )
    registry.async_update_device(own.id, name_by_user="My desk")
    other = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("ha_linak", "OTHER")},
        model="Other model",
    )
    coordinator._update_device_identity()
    assert registry.async_get(own.id).model == "DPG1C"
    assert registry.async_get(own.id).name_by_user == "My desk"
    assert registry.async_get(other.id).model == "Other model"
    await coordinator.async_close()
