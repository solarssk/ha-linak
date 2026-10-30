# ha-linak

Native Home Assistant custom integration, intended for HACS distribution. The first supported hardware target is LINAK DPG1C. Home Assistant owns the Bluetooth connection; no Mac, MQTT broker, daemon or custom dashboard card is required at runtime.

[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge)](https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak) [![HACS: custom](https://img.shields.io/badge/HACS-custom-orange.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)

[Polski](README.pl.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)


## Local alpha 0.1.0a1

This alpha is **read-only**: configuration through the Home Assistant interface, Bluetooth discovery, live height updates, stored heights and reminder profiles. It sends only extended read queries, not movement or configuration commands.

Entities:

- Actual height in centimeters (including the offset reported by the panel).
- Height offset and up to four stored heights.
- Active reminder profile and sitting/standing durations for three profiles.

A [movement research module](docs/movement.md) is implemented and tested with simulated transport, but is not connected to any HA action or entity. Target-height, Stop and stored-position drive controls remain unavailable until supervised hardware validation. There is no percentage-based cover entity.

## Validation status

The seven extended queries were verified on one physical DPG1C using macOS CoreBluetooth. The Python BLE client and integration were tested in **real Home Assistant 2026.10.4 with simulated Bluetooth**, including discovery/configuration, centimeter entities, link loss, recovery, unload and redacted diagnostics. The Raspberry Pi and ESPHome proxy have not yet been tested. Minimum compatibility target is provisionally 2026.10.4; only 2026.10.4 is locally validated.

This is an early read-only alpha. Use it through HACS as a custom repository; it is not listed in the default catalog. Check the current CI run before installing. No official Home Assistant quality-scale rating is claimed.

## Install with HACS

1. Open HACS and its **Custom repositories** menu.
2. Add `https://github.com/solarssk/ha-linak` with type **Integration**.
3. Download **LINAK**, restart Home Assistant, then add the custom LINAK integration in **Settings → Devices & services**.

This is a custom repository, not an entry in the HACS default catalog. While no release is published, HACS installs the default branch. Review the alpha limitations below.

## Manual installation for local testing

1. Copy the entire `custom_components/ha_linak` folder into your Home Assistant configuration's `custom_components` folder.
2. Restart Home Assistant.
3. Close other applications connected to the desk. If the official IKEA Idasen Desk integration is already connected to this desk, disable that entry before testing this one.
4. Put the panel in Bluetooth pairing mode.
5. Go to **Settings → Devices & services → Add integration**, search for **LINAK**, and select the custom integration named LINAK. Its domain is `ha_linak`; the built-in LINAK brand redirects to IKEA Idasen Desk and is a different integration. Bluetooth discovery can also show a discovered card for this custom integration.
6. Select the desk. Setup validates all extended reads before saving an entry.

A reachable Bluetooth adapter or active ESPHome Bluetooth proxy is required. Local adapter authentication may require host-level Bluetooth pairing. Setup may fail while another application holds the panel's single connection.

To uninstall, delete the integration entry in Home Assistant, remove `custom_components/ha_linak`, and restart. The alpha does not modify stored device settings.

## Data updates and failures

Position updates arrive through BLE notifications. Every 60 seconds, the integration refreshes configuration and reads the position to check the connection. A failed refresh or detected disconnect makes sensors unavailable. While entities are loaded, refresh retries use Home Assistant's coordinator scheduling. Failed/ambiguous requests close the connection before retrying, since memory responses do not identify their slot.

The integration requires the verified extended-response layout; it does not yet offer a basic-height fallback for other LINAK models. Unknown speed words and counters are preserved internally without assuming their meaning. Desk height is not occupancy detection.

## Development and security

See [Contributing](CONTRIBUTING.md) for setup, tests and dependency updates, and
[AGENTS.md](AGENTS.md) for implementation rules. The project adopts the playbook's
[Tier 2 baseline](docs/governance.md). CI includes tests, type checks, CodeQL,
workflow lint, dependency and secret scans; main requires passing checks and
signed commits. Private identifiers are excluded from diagnostics. Report
vulnerabilities through [Security](SECURITY.md).

See [hardware results](docs/hardware-results.md), [protocol evidence](docs/protocol.md) and [architecture](docs/architecture.md). Private Bluetooth logs stay outside the project. Test fixtures contain no names, addresses or location identifiers.

## License and acknowledgements

MIT. Independent community project, not affiliated with LINAK or IKEA. See [protocol sources](docs/protocol.md) for the reverse-engineering references. The supplied manufacturer icon and logo identify LINAK hardware. They are excluded from the MIT code license; see [brand asset provenance](docs/branding.md).
