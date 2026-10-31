# Native movement controls and first HA test

Version 0.1.0a7 adds real HA control entities, without a Mac bridge or a separate script. Controls are experimental: software tests use simulated Bluetooth, and physical DPG1C movement/Stop validation is pending. Installing/updating remains read-only until explicit activation. Memory, reminder and offset writes are not included.

## Activate after installation

1. Update LINAK through HACS, restart HA and check that the integration version is 0.1.0a7. Do not delete the integration or remove its Bluetooth bond.
2. Verify Height against the panel and a physical measurement. If the reference disagrees, do not enable movement; offset remains read-only in this version.
3. Establish measured minimum and maximum heights in the same centimeter reference as Height. Do not infer them from stored positions, assume another desk's range or automatically probe mechanical extremes.
4. Open Settings → Devices & services → LINAK → Configure. Enable controls and enter the measured bounds. The ready current position must lie inside them. These limits apply to commands from this integration; they do not program firmware/anti-collision limits.
5. Read the separate confirmation step and confirm enabling movement. Saving options reloads the integration without moving or changing panel settings.
6. Open the device page. It contains Target height (`number`, cm, box mode), Stop (`button`) and Go to stored position 1–4 (`button`, only exposed for reported slots; empty slots are unavailable). Existing sensors and diagnostics retain their unique IDs and categories.

Options can be changed later without deleting/re-adding the device. Turn off Enable controls to return to read-only operation. Reload/unload attempts Stop for an active request and releases the connection. Disabling controls removes their active platform entities; HA can retain their registry/history entries. Re-enabling reuses the same unique IDs. No prior target is restored/executed on reload or reconnect.

## What a command does

Setting Target height explicitly starts a bounded movement. This is not a passive configuration value. Its state starts unknown after setup and records only a completed requested target; Height remains the actual measured position. Stop cancels an active target without waiting for periodic polling. When idle, Stop sends only the stop command, without wake or target packets.

The native number spans your measured bounds in 0.1 cm steps. It does not have the standalone script's 2 cm test limit. A stored-position button re-reads its slot and offset before moving, then uses the same controller and bounds. It does not save/overwrite the position. Targets outside bounds, empty memories, unsupported characteristic operations and competing requests produce errors. The integration never queues a later move or reconnects to complete a failed one.

The command loop uses fresh position reads, one-second I/O deadlines, a two-second no-progress deadline and a thirty-second overall deadline. It attempts Stop on success, error and cancellation. Failure/interruption discards the session; normal read-only polling may reconnect afterward without replaying a target. Radio loss means Stop delivery cannot be guaranteed. Keep physical stopping available and do not use unattended automations until physical behavior is verified.

## First test at the panel

Keep the travel path clear, close other connected desk apps and disable any Idasen integration for this desk. Use HA itself; do not run the standalone BLE tool alongside it. Be present at the physical panel for every initial test. Do not deliberately disconnect Bluetooth or power during this sequence.

| Step | Action | Record / pass condition |
| --- | --- | --- |
| 1 | Activate controls with measured bounds | Entities appear, existing sensors remain, no spontaneous movement |
| 2 | Press Stop while idle | No movement/wakeup; no action error; observe the physical panel |
| 3 | Set a target 0.5–1 cm above the fresh Height reading, inside bounds | Correct direction, stops near target; compare Height, panel and tape measurement |
| 4 | Set a new nearby target and press Stop while physically moving | Observe actual stopping and delay; the interrupted target action may report failure, Stop must not silently hide cleanup failure |
| 5 | Repeat a short downward move | Correct direction and measured final position |
| 6 | Try a stored-position button only after reviewing its read height and travel path | Correct destination, no stored-value change; unavailable/out-of-bounds slots do not move |
| 7 | Reload or disable during a supervised short move | Stop attempted, no continuing target packets, clean disconnect, no resumed move after reload |
| 8 | Reconnect/restart after the desk is stationary | Sensors recover; Target height starts unknown, no movement until a new explicit action |

Do not continue after unexpected direction, failure to stop, height-reference disagreement or repeated action errors. Use the physical panel to stop the desk. A successful HA action means the software path returned, not that physical stopping was independently confirmed.

## Evidence and debugging

For each attempt retain the integration commit/version, HA/OS version, adapter category, panel/known firmware variant, measured bounds/reference, initial/target/final Height, physical measurements, action and outcome. Record actual Stop behavior and whether read-only reconnection recovered. Review names, addresses and locations before sharing screenshots/logs. Add redacted observations to [hardware-results.md](hardware-results.md), explicitly separating software results from physical observations.

Download diagnostics after a failure. `stage` can show movement_prepare, movement, stop or the normal read phases; `controls.last_result` is an allowlisted software outcome, not physical motion telemetry. The debug log records action, phase and exception type without logging targets or backend error text. If reads work but motion fails, capture characteristic properties and the phase/error rather than resetting pairing, changing user ID or silently retrying. Some firmware/Full/Limited variants may reject motion despite readable sensors.

[Movement implementation](movement.md) · [Settings/calibration research](settings-reference.md) · [Standalone protocol experiment](movement-test.md)
