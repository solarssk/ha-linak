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
  <a href="https://app.codecov.io/gh/solarssk/ha-linak"><img src="https://codecov.io/gh/solarssk/ha-linak/graph/badge.svg" alt="Codecov"></a>
  <a href="https://sonarcloud.io/summary/new_code?id=solarssk_ha-linak"><img src="https://sonarcloud.io/api/project_badges/measure?project=solarssk_ha-linak&amp;metric=alert_status" alt="Sonar quality gate"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak"><img src="https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge" alt="OpenSSF Scorecard"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="Code license: MIT"></a>
</p>

> [!IMPORTANT]
> **Read-only alpha.** You can view desk data. Movement, Stop and changing panel settings are still being developed. [What's next →](docs/roadmap.md)

<details>
<summary><strong>On this page</strong></summary>

- [🪑 Supported panels](#supported-panels)
- [📊 Home Assistant entities](#entities)
- [📋 Requirements](#requirements)
- [📦 Installation](#installation)
- [🔌 Configuration](#configuration)
- [🏠 Everyday use](#daily-use)
- [🧪 Validation status](#validation)
- [📚 Help and documentation](#help)
- [📄 License](#license)

</details>

<a id="supported-panels"></a>

## 🪑 Supported panels

The first supported model is **DPG1C**. This version reads desk data.

| LINAK panel | Available functions | Hardware evidence |
| --- | --- | --- |
| **DPG1C** | Height, stored heights, height offset and reminder profiles | Read queries verified on one panel |

Compatibility with other panel models is not confirmed. [Read-query results →](docs/hardware-results.md)

<a id="entities"></a>

## 📊 Home Assistant entities

The integration creates **sensor entities (`sensor`)**. These labels match the English names in HA; your device name may appear before them.

<table>
  <thead>
    <tr><th scope="col">Entity type</th><th scope="col">Name in HA</th><th scope="col">Unit</th><th scope="col">What it shows</th></tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="6">Sensor<br><code>sensor</code></td>
      <td>📏 <strong>Height</strong></td>
      <td>cm</td>
      <td>Current desk height, including the panel offset</td>
    </tr>
    <tr>
      <td>🔖 <strong>Stored height 1–4</strong></td>
      <td>cm</td>
      <td>Heights saved on the panel; up to four entities</td>
    </tr>
    <tr>
      <td>🔔 <strong>Active reminder profile</strong></td>
      <td>—</td>
      <td>The selected profile number</td>
    </tr>
    <tr>
      <td>⏱️ <strong>Profile 1–3 sitting time</strong></td>
      <td>min</td>
      <td>Sitting time configured for each of three profiles</td>
    </tr>
    <tr>
      <td>🚶 <strong>Profile 1–3 standing time</strong></td>
      <td>min</td>
      <td>Standing time configured for each of three profiles</td>
    </tr>
    <tr>
      <td>📐 <strong>Height offset</strong></td>
      <td>cm</td>
      <td>The height reference stored on the panel</td>
    </tr>
  </tbody>
</table>

- **Height** is the main measurement sensor.
- All other entities have the **Diagnostic** category and show settings read from the panel.
- Reminder durations are configured values, not elapsed-time counters.
- Sensors do not move the desk or change its settings.

<a id="requirements"></a>

## 📋 Requirements

- **Home Assistant 2026.10.4+**.
- **HACS** for installation, or a manual copy of the integration.
- A Bluetooth adapter within reach, or a compatible **active ESPHome Bluetooth proxy**.
- A free Bluetooth connection on the panel.

Raspberry Pi and proxy validation are covered [separately](#validation).

<a id="installation"></a>

## 📦 Installation

### With HACS

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

<a id="configuration"></a>

## 🔌 Configuration

1. Close the phone app. Disable any IKEA Idasen Desk integration using the same desk.
2. Put the panel in **Bluetooth pairing mode**.
3. Open **Settings → Devices & services → Add integration** and search for **LINAK**, or use the discovered-device card.
4. Select this custom integration, domain **`ha_linak`**, then choose your desk.

After submitting, HA shows a progress screen. The attempt has a **60-second** limit; releasing the connection can take another **10 seconds**. A failed attempt shows a reason and lets you retry. [First setup and diagnosis →](docs/onboarding.md)

> [!TIP]
> The panel accepts one Bluetooth connection at a time. If setup fails, check that another app is not connected. A local adapter may also need pairing on the HA host.

<details>
<summary>About this alpha and the built-in LINAK entry</summary>

- This is a HACS custom repository, outside the default catalog.
- There is no versioned release yet; HACS downloads the default branch. Check [CI status](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml).
- The built-in LINAK entry leads to IKEA Idasen Desk, a different integration. Choose `ha_linak` for this project.

</details>

<a id="daily-use"></a>

## 🏠 Everyday use

- Find your sensors under **Settings → Devices & services → LINAK**.
- Add the height sensor to your dashboard with a standard HA card.
- View the heights saved on your panel. Viewing a saved height does not move the desk.
- Height updates arrive through Bluetooth. Settings refresh every **60 seconds**.
- If the connection fails, sensors become unavailable and HA retries while they are loaded.

<details>
<summary>Remove the integration</summary>

Delete its entry in Home Assistant, remove `custom_components/ha_linak`, then restart HA. This alpha does not change the panel's saved settings.

</details>

<a id="validation"></a>

## 🧪 Validation status

- **Physical DPG1C:** seven read queries verified through macOS CoreBluetooth.
- **Home Assistant 2026.10.4 with simulated Bluetooth:** setup, sensor, disconnect/recovery and unloading tests.
- **Raspberry Pi and ESPHome proxy:** real-device integration testing pending.

This describes environment validation, not supported panel models. [Full results →](docs/hardware-results.md)

<details>
<summary>Measurement and control limitations</summary>

- Unknown speed words and counters are not exposed as verified measurements.
- Desk height does not indicate occupancy.
- Movement and Stop remain unavailable. There is no percentage-based cover entity.

</details>

<a id="help"></a>

## 📚 Help and documentation

- **Something isn't working?** [Report a bug](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml).
- **Follow development:** [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md).
- **Want to contribute?** [Contributing](CONTRIBUTING.md) · [Agent instructions](AGENTS.md).
- **Technical details:** [Protocol](docs/protocol.md) · [Architecture](docs/architecture.md) · [Movement plan](docs/movement.md).
- **Security:** [Private reporting](SECURITY.md) · [Tier 2 maintenance baseline](docs/governance.md). Diagnostics omit device identifiers.

<a id="license"></a>

## 📄 License

Code: [MIT](LICENSE). Independent community project, not affiliated with LINAK or IKEA. No official HA quality-scale award or HACS default-catalog acceptance is claimed.

The official LINAK artwork supplied for this project identifies the hardware. Names and graphics remain the property of their respective owners and are excluded from the code license. See [asset provenance](docs/branding.md) and [protocol sources](docs/protocol.md).
