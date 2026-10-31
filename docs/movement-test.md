# Supervised movement test

This branch adds an executable research runner, not HA control entities. HACS remains read-only. Run the test from a nearby computer with Bluetooth, outside the HA process; do not install extra packages inside HA Core. It uses the existing motion controller on one dedicated connection, does not change user ID, memories, reminders or offset, and never reconnects/replays a target. A successful software result is not evidence of physical Stop.

## Prepare

1. Be present at the panel, clear the desk's travel path and have physical stopping available. Do not deliberately interrupt radio or power during this first experiment.
2. Disable the LINAK integration and any IKEA Idasen entry for this desk in HA. Close phone/desktop desk apps. Wait for their connections to close. The script cannot enforce exclusion against another computer.
3. Record measured minimum/maximum desk heights, current physical height and the current read-only offset from HA before disabling it. Use centimeters. Bounds must come from measurements, not favourite positions. The offset argument is a conversion input only; it does not program the panel.
4. Check out this PR on the nearby computer. Use Python 3.14.2+ and the isolated development environment described in [CONTRIBUTING.md](../CONTRIBUTING.md). For a fresh Mac environment, run the commands below from the checkout root. Do not paste real device identifiers in public issues.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m scripts.test_motion_hardware --help
```

Use the computer's local BLE identifier: on macOS this is a UUID, not the Pi's MAC address. See the [Bleak client documentation](https://bleak.readthedocs.io/en/latest/api/client.html). This tool does not scan/list nearby devices itself, pair/unpair explicitly or repair the host's bonding state; connecting by identifier can trigger Bleak's implicit discovery and OS-managed authentication. Reuse the private identifier from the previous local research, or obtain it locally before the experiment. If authentication fails, stop and investigate it rather than resetting the panel.

## Inspect first — no control writes

Replace the placeholders with private local values. Keep the shell variables and reports on your computer; they are not repository configuration.

```sh
DESK_DEVICE='<local BLE identifier>'
DESK_OFFSET='<read offset in cm>'
DESK_MIN='<measured minimum in cm>'
DESK_MAX='<measured maximum in cm>'
.venv/bin/python -m scripts.test_motion_hardware --device "$DESK_DEVICE" --offset-cm "$DESK_OFFSET" --minimum-cm "$DESK_MIN" --maximum-cm "$DESK_MAX" > inspection.json
```

Require `result: inspection_only_no_control_writes`. Compare `initial_height_cm` with the panel and tape measure. The runner requires readable height and write-without-response properties on both motion characteristics; it refuses incompatible properties rather than guessing a write mode. If the reported height or bounds disagree, do not continue.

## One short target and timed Stop

Choose a target 0.5–1 cm above the freshly measured current height, within measured travel bounds and away from either end. Do not copy a sample height from another desk. The runner rejects targets more than 2 cm from its own initial read; that is an experimental limit, not an anti-collision guarantee.

```sh
DESK_TARGET='<chosen height in cm>'
.venv/bin/python -m scripts.test_motion_hardware --device "$DESK_DEVICE" --offset-cm "$DESK_OFFSET" --minimum-cm "$DESK_MIN" --maximum-cm "$DESK_MAX" --target-cm "$DESK_TARGET" --confirm-supervised-motion > short-up.json
```

Observe whether motion starts, its direction, whether it stops and the final measured height. The controller has a 30-second total deadline, two-second stall detection and one-second I/O budgets, with Stop attempted on completion/error/cancellation. If motion is unexpected, use the physical panel immediately; Ctrl+C requests cancellation with bounded Stop cleanup, but cannot guarantee radio delivery. Do not press Ctrl+C repeatedly or forcibly kill the process as the normal stopping method.

After a successful short target, choose another nearby target within 2 cm and request timed Stop:

```sh
.venv/bin/python -m scripts.test_motion_hardware --device "$DESK_DEVICE" --offset-cm "$DESK_OFFSET" --minimum-cm "$DESK_MIN" --maximum-cm "$DESK_MAX" --target-cm "$DESK_TARGET" --stop-after 0.5 --confirm-supervised-motion > timed-stop.json
```

The Stop deadline is measured from task start, not detected physical motion. `completed_before_timed_stop` does not validate interruption during travel: choose a suitable nearby target for a later supervised attempt. `timed_stop_sent_physical_stop_unverified` means only that the software Stop path returned. Observe physical stopping yourself. Test a short downward target separately after the upward/Stop results are understood. Do not continue after unexplained behavior.

## Record and recover

Keep one result per attempt, plus these observations. Reports omit the device identifier and backend exception text; configuration/height values are still personal data to review before sharing.

| Field | Record |
| --- | --- |
| Revision/environment | Commit, OS, Python/Bleak versions, local adapter; no address/name |
| Panel | Model/known firmware/Full or Limited if known; otherwise unknown |
| Measurements | Offset, supplied bounds, initial/target/final physical and reported height |
| Operation | Inspect/up/down/timed Stop/Ctrl+C; exact command with device redacted |
| Physical observation | Direction, actual Stop, delay/overshoot, panel indication |
| Machine result | JSON result/error_type and whether it exited normally |
| Recovery | No continued motion, subsequent read-only HA reconnect and sensor values |

Exit 0 means the selected software path completed, 1 means failure, 130 means interruption. `error_type` is deliberately sanitized: ValueError means check parameters, properties, initial bounds or the 2 cm limit; TimeoutError means an I/O/deadline failed; other backend errors require local Bluetooth investigation. Never publish raw backend logs without identifier review. A failed attempt is not permission to retry blindly or change application ownership.

Re-enable only the LINAK integration after the script has exited and the desk has physically stopped. Verify current height/connection in HA. Attach redacted reports and observations to the PR; record validated results in [hardware-results.md](hardware-results.md). Target/Stop entities are the next step after this evidence, including a separate HA session-ownership/lifecycle test. Disconnect and packet-cessation experiments remain separately scoped work.
