# Changelog

## Unreleased

- Keep the Bluetooth link after a movement from Home Assistant ends with `reverse_motion` and the final Stop was delivered. The desk's own reversal, such as anti-collision, no longer causes a disconnect and reconnect.
- Give a movement from Home Assistant that ends in `reverse_motion` its own error message, which names a possible obstruction and points to the panel display instead of the generic failure text.
- Do not report a failure when the Bluetooth link drops during a movement that was only observed from the desk panel; a requested movement still fails with `link_lost`.
- Subscribe to the desk's error characteristic and report a non-empty frame as a failed Operation with reason `desk_error` and the raw frame in `error_code`. The frame is not decoded and is not named a collision until its meaning is verified against the panel display. The desk's own retreat after the fault does not replace the reported failure. An explicit request keeps its own outcome. An empty frame does not erase the reported failure, but it releases the hold on panel observation once the desk is stationary, and the hold also ends after 30 seconds if that frame is lost. A missing or refused channel does not affect the connection.
- Show movements started on the desk panel in the Operation sensor with a `source` attribute (`home_assistant` or `panel`). A panel movement that turns back reports `failed` with reason `reverse_motion`, worded as a possible obstruction. The integration infers this from position and does not read the panel error code.

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
