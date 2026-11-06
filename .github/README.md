<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../docs/assets/linak-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="../docs/assets/linak-logo-light.svg">
    <img src="../docs/assets/linak-logo-light.svg" alt="LINAK: We improve your life" width="360">
  </picture>
</p>

<h1 align="center">LINAK for Home Assistant</h1>

<p align="center">
  <strong>Your LINAK desk in Home Assistant.<br>Height control in centimeters, saved positions and reminders.</strong><br>
  Runs directly in Home Assistant. First hardware target: <strong>DPG1C</strong>.
</p>

<p align="center">
  🇬🇧 <strong>English</strong> &nbsp;·&nbsp; 🇵🇱 <a href="README.pl.md">Polski</a>
</p>

<p align="center">
  <a href="../hacs.json"><img src="https://img.shields.io/badge/Home%20Assistant-2026.11.0%2B-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Home Assistant 2026.11.0 or newer"></a>
  <a href="https://www.home-assistant.io/blog/2026/11/04/release-202611/#custom-repositories"><img src="https://img.shields.io/badge/Marketplace-Custom-41BDF5?logo=homeassistant&amp;logoColor=white" alt="Marketplace custom repository"></a>
</p>

<p align="center">
  <a href="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml"><img src="https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://app.codecov.io/gh/solarssk/ha-linak"><img src="https://codecov.io/gh/solarssk/ha-linak/graph/badge.svg" alt="Codecov"></a>
  <a href="https://sonarcloud.io/summary/new_code?id=solarssk_ha-linak"><img src="https://sonarcloud.io/api/project_badges/measure?project=solarssk_ha-linak&amp;metric=alert_status" alt="Sonar quality gate"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/solarssk/ha-linak"><img src="https://api.securityscorecards.dev/projects/github.com/solarssk/ha-linak/badge" alt="OpenSSF Scorecard"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="Code license: MIT"></a>
</p>

<details>
<summary><strong>On this page</strong></summary>

- [🪑 Supported devices](#supported-panels)
- [📊 Home Assistant entities](#entities)
- [📋 Requirements](#requirements)
- [📦 Installation](#installation)
- [🔌 Configuration](#configuration)
- [🏠 Everyday use](#daily-use)
- [📚 Help and documentation](#help)
- [📄 License](#license)

</details>

<a id="supported-panels"></a>

## 🪑 Supported devices

| Series | Model | Support | Hardware tested |
| --- | --- | :---: | :---: |
| DPG | DPG1C | ✓ | ✓* |
| DPG | DPG1M | ? | – |
| DPG | DPG1B | ? | – |
| DPG | DPG1I | ? | – |
| DPI | DPI1C | ✗ | – |

**✓** available or tested · **?** compatibility unconfirmed · **✗** unsupported · **–** not tested.

\* DPG1C was checked on one panel within the [documented test scope](../docs/hardware-results.md). This does not mean every function and device version has been fully validated.

**0.1.1 is for supervised use on DPG1C.** Hardware acceptance is not complete:

- Full-range arrival, physical stopping accuracy and repeatable panel handback remain unverified.
- Long-term Bluetooth reliability remains unverified. Startup and recovery can be slow or fail, including after enabling Keep connected.

Before using automations, read the [release notes](../CHANGELOG.md) and [remaining hardware tests](../docs/hardware-results.md#hardware-acceptance-matrix).

Check the model on the panel label. [Testing another model](../docs/device-support.md#test-another-panel) has its own guide.

<a id="entities"></a>

## 📊 Home Assistant entities

The device page groups desk readings, diagnostics and movement controls. These labels match the English names in HA; your device name may appear before them.

Entity type is the Home Assistant domain, such as `sensor` or `button`. The sections below group entities by their purpose; units have a separate column.

### Sensors

<table>
  <thead>
    <tr><th scope="col">Entity type</th><th scope="col">Name in HA</th><th scope="col">Unit</th><th scope="col">What it shows</th></tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="6"><code>sensor</code></td>
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
      <td>-</td>
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
    <tr><td>🧭 <strong>Operation</strong></td><td>-</td><td>Progress and result of a movement request</td></tr>
  </tbody>
</table>

- **Height** is the main measurement sensor.
- Stored heights and reminder profiles are regular desk sensors, without the Diagnostic category.
- Reminder durations are configured values, not elapsed-time counters.
- Sensors do not move the desk or change its settings.

**Operation** shows the progress and result of your request, then returns to idle after about 10 seconds. Its `last_result` attribute keeps the result for automations. It describes the integration's request, not an independent measurement of physical arrival.

### Controls

<table>
  <thead><tr><th scope="col">Entity type</th><th scope="col">Name in HA</th><th scope="col">Unit</th><th scope="col">Action</th></tr></thead>
  <tbody>
    <tr><td><code>number</code></td><td>🎯 <strong>Target height</strong></td><td>cm</td><td>Choose a height with the slider</td></tr>
    <tr><td rowspan="2"><code>button</code></td><td>⏹️ <strong>Stop</strong></td><td>-</td><td>Interrupt the current movement</td></tr>
    <tr><td>🔖 <strong>Position 1–4</strong></td><td>-</td><td>Move to a position saved on the panel; empty slots are unavailable. Stored height sensors only show its height</td></tr>
  </tbody>
</table>

The slider selects heights in 1 cm steps within your measured range. It updates after travel finishes, while **Height** shows the changing position. Wait for a move to finish or press **Stop** before choosing another target. Requests aren't queued.

### Configuration

| Entity type | Name in HA | Default | Action |
| --- | --- | --- | --- |
| `select` | 🔔 **Reminder profile** | Enabled | Choose Off or Profile 1/2/3, preserving intervals without moving the desk |
| `select` | 📏 **Preferred panel units** | Enabled | Choose Metric or Inch for the panel, independently of Home Assistant |
| `number` | ⏱️ **Profile 1 sitting time** | Entity disabled | Type 1–60 whole minutes for inactive profile 1; preserve other fields |
| `number` | ⏱️ **Profile 1 standing time**, **Profile 2–3 sitting/standing time** | Entity disabled | Optional 1–60-minute inputs for inactive profiles; preserve other fields |
| `button` | ↩️ **Profile 1: use standard time** | Entity disabled | Set only its sitting time to 55 minutes, not a factory reset |
| `switch` | 🔌 **Keep connected** | Entity disabled | Turn off to release the Bluetooth connection, or on to reconnect |

Enable **Keep connected** in its entity settings to show the switch. While the switch is off, polling and reconnecting stop, including after a restart. Turning it off during travel stops the desk first.

Choose **Metric** or **Inch** in **Preferred panel units**. This doesn't change units in Home Assistant. The Metric option doesn't let you choose between centimeters and millimeters.

The panel may still display the previous unit after saving. Don't move the desk just to refresh its display. [How to change panel units](../docs/controls.md#choose-panel-units).

For settings beyond the table, follow the procedure for your task:

| Task | Where to start | Before saving |
| --- | --- | --- |
| Name, measured range or height correction | [Configure the desk](../docs/controls.md#configure-the-desk-after-installation) | For correction, enter the floor-to-desktop measurement, then review and confirm; no motion |
| Reminder profile | [Select Off or Profile 1/2/3](../docs/controls.md#choose-a-reminder-profile) | Active client, valid readings and stationary desk; intervals stay unchanged |
| Reminder duration | [Edit one duration](../docs/controls.md#edit-one-reminder-duration) | Enable the input, select Off or another profile, then enter 1–60 whole minutes |

Reminder edits preserve other durations and flags. Existing names and enablement choices are preserved; read-only sensors stay enabled. Out-of-range readings remain visible without automatic overwrite. The standard-time button sets only profile 1 sitting time to 55 minutes, not a reset or backup restore. Saved-position editing is unavailable.

Profile 1/2 selection still needs hardware acceptance. Duration hardware evidence covers only 50/55 sitting minutes in inactive profile 1; other fields have simulated coverage. The input range is integration policy, not medical guidance or a firmware limit.

### Diagnostics

<table>
  <thead><tr><th scope="col">Entity type</th><th scope="col">Name in HA</th><th scope="col">Default</th><th scope="col">Meaning</th></tr></thead>
  <tbody>
    <tr><td rowspan="3"><code>sensor</code></td><td>📐 <strong>Height offset</strong></td><td>Enabled</td><td>The height reference stored on the panel, in cm</td></tr>
    <tr><td>📶 <strong>Bluetooth signal strength</strong></td><td>Disabled</td><td>Latest advertisement received by HA, in dBm; not the active link's RSSI</td></tr>
    <tr><td>🛠️ <strong>Bluetooth backend</strong></td><td>Disabled</td><td>Active connection category, such as BlueZ or ESPHome</td></tr>
    <tr><td><code>binary_sensor</code></td><td>🔗 <strong>Connection</strong></td><td>Enabled</td><td>A ready desk session; disconnected after link loss</td></tr>
  </tbody>
</table>

Enable optional entities under **Settings → Devices & services → Entities**, showing disabled LINAK entities. They are not desk-setting switches. Name and MAC are device information, without separate sensors; downloaded diagnostics omit these identifiers. [Interpreting diagnostics →](../docs/diagnostics.md)

<a id="requirements"></a>

## 📋 Requirements

- **Home Assistant 2026.11.0+**.
- The built-in **Marketplace** for installation, or a manual copy of the integration.
- A Bluetooth adapter within reach, or a compatible **active ESPHome Bluetooth proxy**.
- A free Bluetooth connection on the panel.

<a id="installation"></a>

## 📦 Installation

### With Marketplace

1. Open **Settings → Marketplace → Add from link** and connect your GitHub account when prompted.
2. Enter `https://github.com/solarssk/ha-linak`.
3. Install **LINAK**. A first installation with this config flow loads without a restart; updating an already loaded integration still requires one.

HA 2026.11 migrates existing HACS repositories/installations into Marketplace. This project is available through a custom link, not a claimed default-catalog listing. Installed views use bundled brand images; a pre-installation catalog icon is not guaranteed. See [the branding contract](../docs/hacs-presentation.md#name-and-catalog-icon).

<details>
<summary>Prefer manual installation?</summary>

Copy [`custom_components/ha_linak`](../custom_components/ha_linak) into the `custom_components` folder in your Home Assistant configuration, then restart HA.

HA below 2026.11.0 is unsupported here too. The minimum in `hacs.json` is checked for repositories with releases, not enforced as a runtime guard for every manual/default-branch install.

</details>

<a id="configuration"></a>

## 🔌 Configuration

Home Assistant lists the integration as **LINAK**. Its internal domain remains `ha_linak`.

1. Close the phone app. Disable any IKEA Idasen Desk integration using the same desk. LINAK detects enabled IKEA entries for the same desk and explains how to resolve the conflict; it leaves their configuration unchanged.
2. Put the panel in **Bluetooth pairing mode**.
3. Open **Settings → Devices & services → Add integration** and search for **LINAK**, or use the discovered-device card.
4. Select this custom integration, domain **`ha_linak`**, then choose your desk.

Setup guides you through a name in HA, connection, measured travel range and a height check. Choose **Monitoring only** if you want readings without movement setup. Add controls later through **Configure**.

After submitting, allow up to **60 seconds** for connection and another **10 seconds** to release a failed attempt. Follow the displayed error and retry. Disconnect another desk app if one is connected.

<a id="daily-use"></a>

## 🏠 Everyday use

- Find your sensors under **Settings → Devices & services → LINAK**.
- Add the height sensor to your dashboard with a standard HA card.
- View the heights saved on your panel. Viewing a saved height does not move the desk.
- Height updates arrive through Bluetooth, with a reference/position check every **60 seconds**. Saved positions and reminders refresh every **5 minutes**, after reconnecting or when their reference changes.
- If the connection fails, sensors become unavailable and HA retries while they are loaded.

<details>
<summary>Remove the integration</summary>

Delete its entry in Home Assistant, remove `custom_components/ha_linak`, then restart HA. Removing the integration does not undo calibration saved on the panel.

</details>

<a id="validation"></a>
<a id="help"></a>

## 📚 Help and documentation

Choose the guide for your task:

- **Configuration:** [Settings and first control test](../docs/controls.md).
- **Connection or control problems:** [Troubleshooting](../docs/diagnostics.md#choose-the-symptom).
- **Bug report:** [Collect safe evidence](../docs/diagnostics.md#prepare-a-bug-report), then use the [issue form](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml).
- **Help writing a report:** [Optional AI instructions](../docs/diagnostics.md#prepare-a-report-with-ai), without HA access or automatic submission.

### For testers and developers

- [Technical documentation index](../docs/README.md)
- [Device families and testing another model](../docs/device-support.md)
- [Hardware test coverage and known limits](../docs/hardware-results.md)
- [Changelog](../CHANGELOG.md) · [Roadmap](../docs/roadmap.md) · [Contributing](../CONTRIBUTING.md)
- [Private security reporting](../SECURITY.md)

<a id="license"></a>

## 📄 License

Code: [MIT](../LICENSE). Independent community project, not affiliated with LINAK or IKEA.

The official LINAK artwork supplied for this project identifies the hardware. Names and graphics remain the property of their respective owners and are excluded from the code license. See [asset provenance](../docs/branding.md) and [protocol sources](../docs/protocol.md).
