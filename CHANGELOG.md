# Changelog

## Unreleased

## 0.1.1

LINAK 0.1.1 shows desk faults and panel movements in Home Assistant and keeps the Bluetooth link when the desk reverses on its own.

### ⚠️ Before you update

- Restart Home Assistant after updating an already loaded integration. The desk reconnects with fresh reads and no movement is replayed.
- The Operation sensor now also changes state for movements started on the desk panel, not only for requests from Home Assistant. Automations that trigger on `moving`, `completed` or `failed` can now fire for panel movements and desk faults. Check the new `source` attribute (`home_assistant` or `panel`) to tell them apart.

### ✨ New

- Movements started on the desk panel appear in the Operation sensor with `source: panel` and no requested height. They end as `completed` after about one second without movement.
- When the desk reports a fault on its error characteristic, Operation shows `failed` with reason `desk_error` and the raw frame in `error_code`. On the tested DPG1C the frame `01 00 5d` appeared with the panel code E54 when the desk stopped against an obstruction, and the desk then backed away by itself. The frame is not decoded or named a collision; [see the observed pairing](docs/hardware-results.md#desk-error-frames).

### 🔧 Improvements

- A movement requested from Home Assistant that the desk reverses on its own, for example with its own collision protection, now returns an error that names a possible obstruction and points you to the panel display. The generic failure text stays for other failures.
- The desk's own retreat after a fault no longer replaces the reported fault in the Operation sensor, and the next panel movement is followed once the desk has stopped.
- Explain an unreachable desk in the log with Home Assistant's own Bluetooth reachability diagnostics, once per outage, and in the setup retry message. It names causes such as a scanner that cannot connect or a proxy without free connection slots.

### 🐛 Fixes

- Keep the Bluetooth link after a requested movement ends with `reverse_motion` and the final Stop was delivered. Before, the integration closed the session and reconnected.
- Do not report a failure when the Bluetooth link drops during a movement that was only observed from the desk panel. A requested movement still fails with `link_lost`.
- Close the Bluetooth client the desk dropped, so its private D-Bus connection and notification registrations no longer pile up until Home Assistant restarts.

### 📌 Known limitations

- Panel movements are inferred from height feedback. Stopping and then moving the other way counts as a new movement, so a reversal that comes with a stop is reported only through the desk's error frame. The meaning of other error frames is not established.
- Evidence covers one DPG1C and one displayed code (E54). In the author's setup connecting to the desk after a Home Assistant restart took from about a minute to more than ten minutes, with a signal of about -70 dBm, and the link dropped more often through a local BlueZ adapter than through an ESPHome proxy. This release adds log diagnostics but does not change it. An ESPHome Bluetooth proxy close to the desk is the best-supported remedy, and Shelly gateways cannot carry a connection. See the [0.1.0 limitations](#010) for startup, recovery and hardware acceptance.

## 0.1.0

LINAK brings DPG1C desk readings, centimeter controls and selected panel settings directly into Home Assistant over Bluetooth. No phone app or separate bridge is needed.

### ⚠️ Before you update

- Use **Home Assistant 2026.11.0 or newer**. Add this repository through **Settings → Marketplace → Add from link**. HA migrates existing HACS installations; restart HA after updating an already loaded integration.
- Enter your measured minimum and maximum desktop heights before using target or saved-position travel. Favorites are not physical limits. Stop does not require configured bounds.
- Disable an IKEA Idasen Desk entry for the same desk and disconnect competing desk apps. Keep existing pairing, entity IDs and custom names when updating a development installation.
- Initial control tests require someone at the desk and physical stopping access. Bluetooth loss can prevent remote Stop; unattended movement is not validated.

### ✨ New

- Read desktop height, available saved heights, the active reminder profile and sitting/standing durations. Check connection state and optional Bluetooth diagnostics.
- Move with a **Target height** slider in 1 cm steps, **Position 1–4** buttons and **Stop** within your measured range. Stored height sensors only show saved heights; Operation shows the request's phase and result, not independent proof of physical arrival.
- Choose monitoring-only setup or prepare controls through guided configuration. Check and correct the measured height reference without moving the desk.
- Select Off or a reminder profile, edit an inactive profile's sitting/standing durations in 1–60 whole minutes, or explicitly set profile 1 sitting time to 55 minutes. All six duration inputs and the standard-time button are disabled by default for new entities; enable only those you need. Existing registry choices are preserved.
- Choose the stored Metric/Inch panel preference independently of Home Assistant's centimeter readings.
- Optionally enable **Keep connected** to deliberately release the link and suspend polling until connection is requested again. Connection intent survives restart; reconnection uses fresh reads and never replays a movement.
- Use English or Polish setup and entity labels. Administrators can explicitly request a read-only protocol inventory on an existing ready connection; review raw research responses privately before sharing.

### 🔒 Security

- The integration ZIP attached to a GitHub Release includes a SHA-256 checksum and a Sigstore-backed build attestation. Verify both before installing; GitHub-generated source archives are not covered. See the [release artifact verification guide](docs/release-integrity.md).

### 📌 Known limitations

- Hardware evidence covers one DPG1C, not every function or firmware. Other panel variants, fresh unbonded onboarding and proxy-only/mixed-backend control acceptance remain unverified. Default-catalog acceptance is not claimed.
- Bluetooth startup and recovery can be slow or fail, including after enabling Keep connected. Long-term reliability, complete travel, measured Stop accuracy and repeatable physical-panel handback remain unverified.
- Reminder profiles and durations have only partial hardware coverage. The 1–60-minute input range is product policy, not medical guidance or a firmware limit. Saved-position editing is unavailable.
- Metric cannot distinguish physical CM from MM. Immediate OLED unit redraw, sleep behavior and power-cycle persistence remain unverified. See the [hardware evidence](docs/hardware-results.md) and [remaining acceptance gates](docs/roadmap.md#evidence-and-release-gates).
