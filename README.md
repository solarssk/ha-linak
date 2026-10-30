<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/linak-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/linak-logo-light.svg">
    <img src="docs/assets/linak-logo-light.svg" alt="LINAK — We improve your life" width="360">
  </picture>
</p>

<h1 align="center">LINAK for Home Assistant</h1>

<p align="center">
  <strong>Your LINAK desk in Home Assistant.<br>Live height in centimeters, saved heights and reminders.</strong><br>
  Runs directly in Home Assistant. First hardware target: <strong>DPG1C</strong>.
</p>

<p align="center">
  🇬🇧 <strong>English</strong> &nbsp;·&nbsp; 🇵🇱 <a href="README.pl.md">Polski</a>
</p>

<p align="center">
  <a href="hacs.json"><img src="https://img.shields.io/badge/Home%20Assistant-2026.10.4%2B-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Home Assistant 2026.10.4 or newer"></a>
  <a href="https://www.hacs.xyz/docs/faq/custom_repositories/"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&amp;logoColor=white" alt="HACS custom repository"></a>
</p>

<p align="center">
  <a href="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml"><img src="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak"><img src="https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge" alt="OpenSSF Scorecard"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="Code license: MIT"></a>
</p>

> [!IMPORTANT]
> **Read-only alpha.** You can view desk data. Movement, Stop and changing panel settings are still being developed. [What's next →](docs/roadmap.md)

<details>
<summary><strong>On this page</strong></summary>

- [What you can see](#what-you-can-see)
- [Install and connect](#install-and-connect)
- [Everyday use](#everyday-use)
- [Tested hardware](#tested-hardware)
- [Help and project details](#help-and-project-details)
- [License](#license)

</details>

## What you can see

| Sensor | In Home Assistant |
| --- | --- |
| Desk height | Current height in **cm**, including the panel's height offset |
| Saved heights | Up to **four positions**, in cm |
| Reminders | Active profile and sitting/standing times for **three profiles** |
| Height offset | The panel's height reference, in cm |

## Install and connect

**You'll need:** Home Assistant **2026.10.4+**, HACS and Bluetooth within reach of the desk.

A local adapter or compatible **active ESPHome Bluetooth proxy** can provide the connection. Raspberry Pi and proxy operation still need real-device testing.

### 1. Download through HACS

1. Open HACS → **Custom repositories**.
2. Add this address and choose **Integration**:

   ```text
   https://github.com/solarssk/ha-linak
   ```

3. Download **LINAK** and restart Home Assistant.

<details>
<summary>Prefer manual installation?</summary>

Copy [`custom_components/ha_linak`](custom_components/ha_linak) into the `custom_components` folder in your Home Assistant configuration, then restart HA.

</details>

### 2. Connect your desk

1. Close the phone app. Disable any IKEA Idasen Desk integration using the same desk.
2. Put the panel in **Bluetooth pairing mode**.
3. Open **Settings → Devices & services → Add integration** and search for **LINAK**, or use the discovered-device card.
4. Select this custom integration, domain **`ha_linak`**, then choose your desk.

> [!TIP]
> The panel accepts one Bluetooth connection at a time. If setup fails, check that another app is not connected. A local adapter may also need pairing on the HA host.

<details>
<summary>About this alpha and the built-in LINAK entry</summary>

- This is a HACS custom repository, outside the default catalog.
- There is no versioned release yet; HACS downloads the default branch. Check [CI status](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml).
- The built-in LINAK entry leads to IKEA Idasen Desk, a different integration. Choose `ha_linak` for this project.

</details>

## Everyday use

- Find your sensors under **Settings → Devices & services → LINAK**.
- Add the height sensor to your dashboard with a standard HA card.
- View the heights saved on your panel. Viewing a saved height does not move the desk.
- Height updates arrive through Bluetooth. Settings refresh every **60 seconds**.
- If the connection fails, sensors become unavailable and HA retries while they are loaded.

<details>
<summary>Remove the integration</summary>

Delete its entry in Home Assistant, remove `custom_components/ha_linak`, then restart HA. This alpha does not change the panel's saved settings.

</details>

## Tested hardware

| Environment | Status |
| --- | --- |
| One physical **DPG1C** | Seven read queries verified through macOS CoreBluetooth |
| **HA 2026.10.4**, simulated Bluetooth | Setup, sensors, disconnect/recovery and unloading tested |
| Raspberry Pi / ESPHome proxy | Real-device validation pending |
| Other LINAK panels | Compatibility not confirmed |

Details: [hardware results](docs/hardware-results.md). There is no percentage-based cover entity. Unknown speed fields and counters are not exposed as verified measurements; height does not indicate occupancy.

## Help and project details

- **Something isn't working?** [Report a bug](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml).
- **Follow development:** [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md).
- **Want to contribute?** [Contributing](CONTRIBUTING.md) · [Agent instructions](AGENTS.md).
- **Technical details:** [Protocol](docs/protocol.md) · [Architecture](docs/architecture.md) · [Movement plan](docs/movement.md).
- **Security:** [Private reporting](SECURITY.md) · [Tier 2 maintenance baseline](docs/governance.md). Diagnostics omit device identifiers.

## License

Code: [MIT](LICENSE). Independent community project, not affiliated with LINAK or IKEA. No official HA quality-scale award or HACS default-catalog acceptance is claimed.

The official LINAK artwork supplied for this project identifies the hardware. Names and graphics remain the property of their respective owners and are excluded from the code license. See [asset provenance](docs/branding.md) and [protocol sources](docs/protocol.md).
