<p align="center">
  <img src="custom_components/ha_linak/brand/logo.png" alt="LINAK" width="360">
</p>

# ha-linak

Bring your LINAK desk into Home Assistant with live height readings in centimeters, saved positions and reminder settings. This community integration runs directly in Home Assistant and is installed through HACS. The first hardware target is the **DPG1C** panel.

[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![HACS: custom](https://img.shields.io/badge/HACS-custom-orange.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge)](https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak)

**English** · [Polski](README.pl.md)

[Features](#features) · [Installation](#installation) · [Daily use](#daily-use) · [Compatibility](#compatibility) · [Documentation](#documentation) · [License](#license)

> [!IMPORTANT]
> **Read-only alpha.** The integration reads desk data. Movement, Stop and changes to panel settings are not available yet. The movement research module is isolated from the installed integration until supervised hardware validation. See the [movement plan](docs/movement.md).

## Features

| In Home Assistant | What you can read |
| --- | --- |
| Actual height | Current height in **cm**, including the offset reported by the panel |
| Height offset | The panel's height reference, in cm |
| Stored positions | Up to four saved heights, in cm |
| Reminders | Active profile and sitting/standing durations for three profiles |

Setup uses Home Assistant's interface and Bluetooth discovery. There is no separate Mac service, MQTT broker or custom dashboard card to maintain.

## Installation

### Before you start

- **Home Assistant 2026.10.4 or newer.** The locally validated version is 2026.10.4.
- A Bluetooth adapter within reach of the desk, or a compatible **active ESPHome Bluetooth proxy**. Raspberry Pi and proxy operation still need real-device validation.
- A free Bluetooth connection on the panel. Close the phone app and disable any IKEA Idasen Desk integration connected to the same desk.

### Download with HACS

1. In HACS, open **Custom repositories**.
2. Add the address below with type **Integration**:

   ```text
   https://github.com/solarssk/ha-linak
   ```

3. Download **LINAK**, then restart Home Assistant.
4. Continue with **Connect your desk** below.

This is a HACS custom repository, outside the default catalog. No versioned release has been published yet; HACS currently downloads the default branch. Check [CI status](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml) before installing.

<details>
<summary>Manual installation</summary>

Copy the entire [`custom_components/ha_linak`](custom_components/ha_linak) folder into your Home Assistant configuration's `custom_components` directory. Restart Home Assistant, then follow the connection steps below.

</details>

### Connect your desk

1. Put the desk panel in Bluetooth pairing mode.
2. Open **Settings → Devices & services → Add integration** and search for **LINAK**. You can also use the discovered-device card.
3. Choose this custom integration, with domain **`ha_linak`**, and select your desk. Setup checks the connection and extended reads before saving the entry.

The built-in LINAK brand leads to IKEA Idasen Desk, a different integration. With a local adapter, Bluetooth authentication may also require pairing on the Home Assistant host.

## Daily use

Open the LINAK device under **Settings → Devices & services** to view its entities. Add the actual-height sensor to a dashboard using Home Assistant's standard cards. Stored-position sensors show the heights saved on the panel; selecting or viewing one does not move the desk.

Height updates arrive through Bluetooth notifications. The integration also refreshes settings and checks the connection every **60 seconds**. A detected disconnect or failed refresh makes the entities unavailable; Home Assistant retries while they are loaded. It closes ambiguous sessions before retrying.

To uninstall, delete the integration entry, remove `custom_components/ha_linak`, then restart Home Assistant. This alpha does not change the panel's stored settings.

## Compatibility

Seven extended read queries were verified on **one physical DPG1C** using macOS CoreBluetooth. The Python client and integration were tested in **Home Assistant 2026.10.4 with simulated Bluetooth**, including setup, live updates, connection loss, recovery and unloading. [Hardware results](docs/hardware-results.md) distinguish device evidence from simulation.

- Raspberry Pi and ESPHome proxy operation remain unverified on real hardware.
- Other LINAK panels are not confirmed compatible. The client requires the verified extended-response layout.
- Motion commands remain unregistered. There is no percentage-based cover entity.
- Unknown speed words and counters are not presented as verified measurements. Desk height does not indicate occupancy.

The project has no official Home Assistant quality-scale award or HACS default-catalog acceptance.

## Documentation

| Read more | Purpose |
| --- | --- |
| [Hardware results](docs/hardware-results.md) | What was observed on the DPG1C |
| [Protocol evidence](docs/protocol.md) | BLE formats and research sources |
| [Movement plan](docs/movement.md) | Control design and supervised validation |
| [Architecture](docs/architecture.md) | Connection and integration design |
| [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md) | Changes and next steps |

For development, see [Contributing](CONTRIBUTING.md) and [agent instructions](AGENTS.md). The repository adopts the playbook's [Tier 2 baseline](docs/governance.md), including tests, type checks, CodeQL, dependency/secret scans and protected main. Diagnostics omit device identifiers. Report vulnerabilities through [Security](SECURITY.md).

## License

Code: [MIT](LICENSE). This is an independent community project, not affiliated with LINAK or IKEA.

LINAK names, icon and logo identify the supported hardware and remain the property of their respective owners. The artwork is excluded from the MIT code license. See [asset provenance](docs/branding.md) and [protocol acknowledgements](docs/protocol.md).
