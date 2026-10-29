# Changelog

## Unreleased

- **Predictable validation:** CI uses hashed dependency files and checks that updates keep the Home Assistant test stack consistent.
- **Reviewed maintenance:** Dependency proposals respect HA-owned versions, and workflow/documentation checks protect future changes.

## 0.1.0a1 — unpublished local alpha

- Add native Home Assistant UI configuration and Bluetooth discovery.
- Validate extended reads before creating a config entry.
- Add actual height in centimeters, offset, stored positions and reminder profiles.
- Share one asynchronous BLE connection, serialize queries and reconnect after failed reads.
- Add English/Polish translations and diagnostics omitting device identifiers.
- Add captured DPG1C protocol fixtures and real Home Assistant tests with simulated Bluetooth.

Hardware movement, setting changes, Raspberry Pi operation and HACS publication are not yet validated.
