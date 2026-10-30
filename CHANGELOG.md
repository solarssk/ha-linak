# Changelog

## Unreleased

- Add an unregistered movement research controller with explicit centimeter conversion, measured travel limits, bounded I/O, Stop on completion/cancellation, progress checks and simulated failure tests. Installed HA behavior remains read-only pending supervised hardware validation.
- Adopt the playbook Tier 2 maintenance baseline and document the native-control contract.
- Package the supplied LINAK icon and logo as local HA brand images, with provenance and trademark notices.

### Adopter action

- Update Home Assistant to 2026.10.4 or newer before installing this alpha.

- **Safer dependency downloads:** Update the lock generator and HA test stack to remove vulnerable uv certificate stores (GHSA-hq85-5cpj-mr62).

- **Visible test reports:** Codecov and Sonar receive integration coverage and test results separately from required CI checks.

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
