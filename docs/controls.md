# Configure and test desk controls

The device page provides a centimeter height slider, Stop and buttons for positions already saved on the panel. These controls use actual feedback and measured command bounds. Initial tests require someone at the desk; complete travel and physical Stop accuracy are not yet validated across supported environments.

## Configure the desk after installation

Open **Settings → Devices & services → LINAK Desks → Configure**. Choose the task you need:

| Option | What to enter or confirm | What changes |
| --- | --- | --- |
| HA name | A recognizable name | HA entry/device naming; no Bluetooth rename or reconnect |
| Connection preparation | Explicit preparation of the existing panel client | Conditional verified activation; no motion |
| Check/correct height | Whether the current reading matches a tape measurement | A separate confirmation can correct the panel reference |
| Height range | Measured lowest/highest desktop heights | HA command bounds; no motion or firmware-limit programming |

Setup guides you through the same information. Keep the desk stationary from its current-height measurement through correction confirmation. Physical panel movement while measuring the travel range happens before the final current-height check.

## Correct a wrong height reading

Measure from the floor to the top of the desktop. Enter that real measurement; do not alter it to match an incorrect panel reading.

1. Open the height check and choose the correction path if the reading is wrong.
2. Enter the current tape measurement while the desk is stationary.
3. Review the old/proposed height and the effect on displayed saved heights.
4. Confirm the correction. Wait for activation, acknowledgement and independent readback to finish.
5. Verify the resulting height and provide or revise the measured range when requested.

Height correction is available even if no bounds have been saved yet. It changes the reference used for displayed heights, not raw saved mechanism positions. It sends no movement or wake command.

A changed position/reference rejects the proposal before correction. If verification fails after a write, the setting may already have changed. Check the current reading before another attempt; there is no automatic retry or rollback. See the [calibration contract](settings-reference.md#height-calibration-contract) for exact checks.

## Set measured command bounds

Enter the actual lowest and highest desktop heights from measurements or verified product data for this desk. Do not infer them from favorite positions or let the integration probe mechanical extremes.

| Behavior | Result |
| --- | --- |
| Save bounds | Validate them against the current reference and position; do not move |
| Missing bounds | Target and memory travel remain unavailable; Stop can work with a ready connection |
| Corrected reference invalidates old bounds | Request revised bounds instead of silently expanding them |
| Empty memory slot | Its travel button is unavailable |
| Target outside bounds | Reject it without movement |

Host command bounds do not override the desk's firmware limits or anti-collision behavior. No verified remote minimum/maximum query exists yet.

## Use the native controls

The slider uses 1 cm steps inside inward-rounded measured bounds. The height sensor follows measured position live. The slider holds its previous value during travel and updates to the measured height after movement completes or a stationary position remains unchanged for 0.5 seconds, including physical-panel changes. Intermediate travel heights are not slider targets or separate slider history entries. Calibration inputs, raw diagnostics and stored-position targets retain decimal precision; new height history records use whole centimeters.

Before either a target or stored-position drive, the integration checks client readiness and prepares the existing identifier only if inactive. It verifies preparation before wake/target commands. Stored-position drive re-reads that slot and the reference; it does not overwrite the saved position.

Stop preempts an active request. Stop sends control Stop and reference-input release, with no activation, wake or height target. A successful interruption retains the ready link for the next command; failed or ambiguous cleanup still discards it. An interrupted target can report an action error even when Stop succeeds. Failed commands are not queued or resumed after reload/reconnect.

## Test native controls at the panel

Clear the travel path, have physical stopping available and disable any other integration controlling the same desk. Use HA alone, not the standalone BLE runner at the same time. Review the actual/reference height and bounds before each attempt.

| Step | Action | Pass condition and record |
| --- | --- | --- |
| 1 | Add/update the desk and range | Existing sensors and controls appear without spontaneous movement |
| 2 | Press Stop while idle | No motion/wake and no silent action error |
| 3 | Choose a nearby whole-centimeter target above the actual height | Correct direction, observed stopping and measured final height; account for rounding of the current sensor |
| 4 | During another agreed nearby move, press Stop | Observe physical stopping and delay, not only the HA action result |
| 5 | Repeat a nearby downward target | Correct direction and final height |
| 6 | Review a saved height/path, then test its button | Correct destination and unchanged stored value |
| 7 | Test scoped reload/unload during motion | Stop attempted, cleanup settles, no continued/resumed target |
| 8 | Reconnect/restart once stationary | Fresh readings; no motion until another explicit action |

The native slider has no standalone runner's 2 cm experiment cap. Choose the test target deliberately from the fresh actual height, not a rounded value copied from another desk. Do not continue after unexpected direction, failure to stop, a reference disagreement or repeated action errors.

## Interpret and report the result

A successful action means its software path completed, not that a person independently confirmed physical stopping. Keep integration revision, HA/OS version, actual backend, panel/variant, measured bounds, initial/target/final heights and the physical observation for each attempt.

Use the [diagnostic manual](diagnostics.md) to interpret unavailable entities and the reason logged before cleanup. RSSI can remain available after a session failure because it comes from advertisements. Readable sensors do not establish client readiness or motion support on a Limited/OEM-restricted variant.

The [hardware evidence](hardware-results.md) distinguishes observed activation, calibration and limited movement feedback from full target/Stop validation still pending. The [standalone runner](movement-test.md) is a separate research tool with its own ownership and preparation requirements.
