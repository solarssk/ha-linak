# Desk height slider and buttons

The device page includes a height slider in centimeters, Stop and buttons for positions saved on the panel. The slider follows the current desk height, including changes made with the physical panel. Selecting a new height starts movement. No previous target is restored or executed after reload or reconnect.

## Set the height range

New onboarding asks for the desk's measured minimum and maximum heights. Use the same centimeter reference as the Height reading and compare it against the panel and a physical measurement. Do not infer the range from favourites or probe mechanical extremes automatically.

For an existing installation, update through HACS, restart HA and open Settings → Devices & services → LINAK → Configure to fill in the range. Use the same page to change it later. There is no movement-enable switch or extra confirmation step. Saving the range does not move the desk or program firmware limits or offset.

All control entities are registered by default. Stop works with a ready connection even before the range is filled in. The slider and saved-position travel need the range; on an older entry they remain unavailable until it is supplied. Empty memory slots are unavailable. Existing sensor, diagnostic and control unique IDs are preserved.

## How movement works

The native slider spans your measured bounds in 0.1 cm steps. It does not have the standalone script's 2 cm experiment limit. A stored-position button re-reads its slot and offset before moving through the same controller and bounds. It does not save/overwrite the position. Targets outside bounds, empty memories, unsupported characteristic operations and competing requests produce errors. Commands are not queued or resumed after connection loss.

Stop cancels an active request without waiting for periodic polling. When idle, it sends only Stop, without wake or target packets. Reload/unload settles movement cleanup before releasing the connection. The command loop uses fresh position reads, one-second I/O deadlines, a two-second no-progress deadline and a thirty-second overall deadline. It attempts Stop on completion, failure and cancellation. Radio loss means Stop delivery cannot be guaranteed, so keep the physical panel available during tests.

## First test at the panel

Keep the travel path clear, close other connected desk apps and disable any Idasen integration for this desk. Use HA itself; do not run the standalone BLE tool alongside it. Be present at the physical panel for every initial test. Do not deliberately disconnect Bluetooth or power during this sequence.

| Step | Action | Record / pass condition |
| --- | --- | --- |
| 1 | Add the desk or update its height range | Entities appear, existing sensors remain, no spontaneous movement |
| 2 | Press Stop while idle | No movement/wakeup; no action error; observe the physical panel |
| 3 | Set a target 0.5–1 cm above the fresh Height reading, inside bounds | Correct direction, stops near target; compare Height, panel and tape measurement |
| 4 | Set a new nearby target and press Stop while physically moving | Observe actual stopping and delay; the interrupted target action may report failure, Stop must not silently hide cleanup failure |
| 5 | Repeat a short downward move | Correct direction and measured final position |
| 6 | Try a stored-position button only after reviewing its read height and travel path | Correct destination, no stored-value change; unavailable/out-of-bounds slots do not move |
| 7 | Reload or disable during a supervised short move | Stop attempted, no continuing target packets, clean disconnect, no resumed move after reload |
| 8 | Reconnect/restart after the desk is stationary | Sensors recover; Slider follows current height; no movement until a new explicit action |

Do not continue after unexpected direction, failure to stop, height-reference disagreement or repeated action errors. Use the physical panel to stop the desk. A successful HA action means the software path returned, not that physical stopping was independently confirmed.

## Evidence and debugging

For each attempt retain the integration commit/version, HA/OS version, adapter category, panel/known firmware variant, measured bounds/reference, initial/target/final Height, physical measurements, action and outcome. Record actual Stop behavior and whether read-only reconnection recovered. Review names, addresses and locations before sharing screenshots/logs. Add redacted observations to [hardware-results.md](hardware-results.md), explicitly separating software results from physical observations.

Download diagnostics after a failure. `stage` can show movement_prepare, movement, stop or the normal read phases; `controls.range_configured` shows whether bounds exist; `controls.last_result` is an allowlisted software outcome, not physical motion telemetry. The debug log records action, phase and exception type without logging targets or backend error text. If reads work but motion fails, capture characteristic properties and the phase/error rather than resetting pairing, changing user ID or silently retrying. Some firmware/Full/Limited variants may reject motion despite readable sensors.

[Movement implementation](movement.md) · [Settings/calibration research](settings-reference.md) · [Standalone protocol experiment](movement-test.md)

## Validation status

Software tests run in real in-process HA with synthetic Bluetooth. Physical DPG1C movement and Stop tests remain pending. This alpha does not write offset, memories, reminder settings or user ID. Record the supervised outcomes above before recommending unattended automations.
