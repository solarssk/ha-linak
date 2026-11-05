![LINAK](docs/assets/linak-logo.svg)

# LINAK for Home Assistant

Control a height-adjustable desk with a LINAK **DPG1C** panel from Home Assistant over Bluetooth. Set the height in centimeters, use saved positions and check reminder settings.

🇬🇧 **English** · 🇵🇱 [Polski](README.pl.md)

[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.10.4%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![CI](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/ha-linak/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/solarssk/ha-linak/blob/main/LICENSE)

## 🪑 Supported devices

| Series | Model | Support | Hardware tested |
| --- | --- | :---: | :---: |
| DPG | DPG1C | ✓ | ✓* |
| DPG | DPG1M | ? | – |
| DPG | DPG1B | ? | – |
| DPG | DPG1I | ? | – |
| DPI | DPI1C | ✗ | – |

**✓** available or tested · **?** compatibility unconfirmed · **✗** unsupported · **–** not tested.

\* DPG1C was checked on one panel within the [documented test scope](docs/hardware-results.md). This does not mean every function and device version has been fully validated.

Check the model on the panel label. [Testing another model](docs/device-support.md#test-another-panel) has its own guide.

## 🏠 Your desk on the dashboard

Add **Height** to a standard Home Assistant card to see the desk's current position. Use the height slider to choose a working height, or a stored-position button to switch between sitting and standing.

The integration runs directly on your Home Assistant host over Bluetooth. You don't need a phone app, Mac or separate bridge.

## 📊 Home Assistant entities

### Sensors

View these desk readings:

- 📏 **Height** (`sensor`): current desktop height in centimeters
- 🔖 **Stored height 1–4** (`sensor`): heights saved on the panel, with one sensor per available slot
- 🔔 **Active reminder profile** (`sensor`): the selected reminder profile
- ⏱️ **Profile 1–3 sitting time** and **standing time** (`sensor`): the durations configured on the panel
- 🧭 **Operation** (`sensor`): follow preparation, movement, stopping and the result of your request

Reminder durations are settings, not elapsed-time counters. Viewing a stored height does not move the desk.

**Operation** returns to idle about 10 seconds after showing the result. Its `last_result` attribute keeps that result for automations. It describes the integration's request; it doesn't independently verify physical arrival.

### Controls

Use these controls from the device page, dashboard or an automation:

- 🎚️ **Target height** (`number`): choose a height with the centimeter slider
- ⏹️ **Stop** (`button`): stop the current movement
- 🔖 **Go to stored position 1–4** (`button`): move to a position saved on the panel

The slider uses 1 cm steps within your measured range. It updates after a move finishes; **Height** shows the changing position during travel. Wait for a move to finish or press **Stop** before choosing another target. Requests aren't queued.

### Configuration

- 🔔 **Reminder profile** (`select`): choose Off or Profile 1/2/3, preserving the intervals
- 📏 **Preferred panel units** (`select`): choose Metric or Inch for the panel, independently of Home Assistant
- ⏱️ **Profile 1 sitting time** (`number`): type 1–60 whole minutes for an inactive profile
- ↩️ **Profile 1: use standard 55 minutes** (`button`): change only that duration, not a factory reset
- 🔌 **Keep connected** (`switch`): release the Bluetooth connection on purpose, then reconnect when needed

**Keep connected** is disabled by default. Enable it in the entity settings to show the switch. Turning the switch off stops polling and reconnecting until you turn it on, including after a restart. During movement, it stops the desk first.

Choose **Metric** or **Inch** in **Preferred panel units**. This doesn't change units in Home Assistant. The Metric option doesn't let you choose between centimeters and millimeters.

The panel may still display the previous unit after saving. Don't move the desk just to refresh its display. [How to change panel units](docs/controls.md#choose-panel-units).

### Diagnostics

Use these entities when checking the connection or height calibration:

- 🔗 **Connection** (`binary_sensor`): whether the desk is connected and its readings are available
- 📐 **Height offset** (`sensor`): the height reference saved on the panel
- 📶 **Bluetooth signal strength** (`sensor`): the latest signal received by Home Assistant
- 🛠️ **Bluetooth backend** (`sensor`): whether the connection uses a local adapter or proxy

Signal strength and backend are optional. Enable them under **Settings → Devices & services → Entities**, showing disabled LINAK entities.

## 📋 What you need

Prepare these before installation:

- **Home Assistant 2026.10.4 or newer**
- A **DPG1C** panel within Bluetooth range
- A local Bluetooth adapter or compatible active **ESPHome Bluetooth proxy** with pairing support

## 🚀 Install and connect

1. In HACS, add `https://github.com/solarssk/ha-linak` as a custom repository of type **Integration**.
2. Download **LINAK**, then restart Home Assistant.
3. Disable any IKEA Idasen Desk integration using this same desk. Disconnect another desk app if one is connected.
4. Enable **Bluetooth pairing** on the panel.
5. Open **Settings → Devices & services → Add integration**, search for **LINAK** and choose your desk. You can also use its discovery card.
6. Follow the setup screens to name the desk, check its connection and configure the height range.

Choose **Monitoring only** in setup if you want readings without preparing movement controls. You can add the measured height range later through **Configure**.

Allow up to **60 seconds** for connection and another **10 seconds** to release a failed attempt. If setup fails, follow the displayed message and retry. [Manual installation](.github/README.md#installation).

## ⚙️ Adjust the desk settings

Open **Settings → Devices & services → LINAK → Configure** to change the name shown in HA, set the measured travel range or check the height calibration.

If the panel shows the wrong height, measure from the floor to the top of the desktop. Enter that value in **Height measured with a tape**, then review and confirm the correction. Saving the correction doesn't move the desk.

Height displays use whole centimeters. Enter your measurements at their measured precision; calibration keeps that precision. Choose Off or Profile 1/2/3 with Reminder profile. Selection preserves the intervals and other panel settings, does not move the desk and never activates the client. A write requires an active client and valid reminder readings. Profiles 1/2 still need hardware acceptance. Saved-position editing remains unavailable.

On the device page under **Configuration**, type **1–60 whole minutes** into **Profile 1 sitting time**, or explicitly choose its standard **55 minutes** with the button. Select Off or another profile first; changing an active profile's duration is refused. Only this sitting duration changes, with no adjustment of standing time or automatic profile change. Existing values outside the input range stay visible and are not overwritten. The range is integration policy, not medical or firmware limits. Hardware evidence covers 50/55 in inactive profile 1 only; other durations remain read-only. Neither action is a factory reset or an automatic restore. [Interval details](docs/settings-reference.md#edit-profile-1-sitting-time).

Unused memory slots do not need to be filled before setup. If saved positions or reminders cannot be read, height can remain available while the affected settings are unavailable. A timed-out group is retried after five minutes; stored-position buttons require a complete valid memory read.

## 🛠️ Get help

If readings become unavailable, check **Connection** and the error shown by Home Assistant. Open the LINAK device page to download diagnostics. For a bug report, include the panel model, HA/integration versions and whether you use a local adapter or proxy. Remove private names and Bluetooth addresses from any logs you attach.

- [Configuration and first control test](docs/controls.md)
- [Troubleshooting](docs/diagnostics.md)
- [Report a bug](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml)

## 📚 Technical documentation

For testing another model or contributing to the integration:

- [Documentation index](docs/README.md)
- [Device families and tester guide](docs/device-support.md)
- [Hardware test coverage and known limits](docs/hardware-results.md)
- [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md) · [Contributing](CONTRIBUTING.md)

Independent community project, not affiliated with LINAK or IKEA. Code is MIT licensed; LINAK artwork belongs to its owner. [Branding and sources](docs/branding.md).
