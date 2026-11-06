# Configure and test desk controls

**English** · [Polski](controls.pl.md)

Use this guide to configure height, reminders and native controls. **Position 1–4** buttons request movement; **Stored height 1–4** sensors only display saved heights.

**Initial tests require someone at the desk with physical stopping available.** Complete travel and physical Stop accuracy are not yet validated across supported environments.

Choose your task:

| Task | Section |
| --- | --- |
| First setup or monitoring without movement | [Configure the desk](#configure-the-desk-after-installation) |
| Wrong displayed height | [Correct the reading](#correct-a-wrong-height-reading) |
| Reminders | [Choose a profile](#choose-a-reminder-profile) or [edit one duration](#edit-one-reminder-duration) |
| Panel display units | [Choose panel units](#choose-panel-units) |
| Slider, Position buttons or Stop | [Set measured bounds](#set-measured-command-bounds), then [use controls](#use-the-native-controls) |
| Release or reconnect Bluetooth | [Keep connected](#keep-connected-switch) |
| Agreed hardware test | [Test at the panel](#test-native-controls-at-the-panel) |

## Configure the desk after installation

Open **Settings → Devices & services → LINAK → Configure**. Choose the task you need:

| Option | What to enter or confirm | What changes |
| --- | --- | --- |
| HA name | A recognizable name | HA entry/device naming; no Bluetooth rename or reconnect |
| Connection preparation | Explicit preparation of the existing panel client | Conditional verified activation; no motion |
| Check/correct height | Whether the current reading matches a tape measurement | A separate confirmation can correct the panel reference |
| Height range | Measured lowest/highest desktop heights | HA command bounds; no motion or firmware-limit programming |

Setup guides you through the same information. To only watch the desk, choose **Monitoring only** on the name step. Nothing is written to the panel and no range is requested. Add the range in Configure when you want controls.

Saved positions appear from the first setup form and alongside the travel range. They are informational, not physical limits or tape measurements. Enter both measured bounds before requesting movement; favorites never fill missing bounds. See [saved-position display states](onboarding.md#saved-positions-and-missing-bounds) for empty, unavailable and unsupported slots.

Keep the desk stationary from its current-height measurement through correction confirmation. Physical panel movement while measuring the travel range happens before the final current-height check.

## Correct a wrong height reading

Measure from the floor to the top of the desktop. Enter that real measurement; do not alter it to match an incorrect panel reading.

1. Open the height check and choose the correction path if the reading is wrong.
2. Enter the current tape measurement while the desk is stationary.
3. Review the old/proposed height and the effect on displayed saved heights.
4. Confirm the correction. Wait for activation, acknowledgement and independent readback to finish.
5. Verify the resulting height and provide or revise the measured range when requested.

Height correction is available even if no bounds have been saved yet. It changes the reference used for displayed heights, not raw saved mechanism positions. It sends no movement or wake command.

A changed position/reference rejects the proposal before correction. If verification fails after a write, the setting may already have changed. Check the current reading before another attempt; there is no automatic retry or rollback. See the [calibration contract](settings-reference.md#height-calibration-contract) for exact checks.

## Choose a reminder profile

Use **Reminder profile** to select Off or Profile 1/2/3 without changing the configured durations or other panel flags:

1. Leave the desk stationary and wait for valid reminder readings.
2. On the device page, open **Configuration → Reminder profile**.
3. Select the profile and check the reported result.

No travel range is needed. Selection sends no activation, wake or movement; the active-profile sensor remains available for automations. Profile 1/2 selection still needs hardware acceptance.

If selection fails, use the matching recovery:

| Message | What to do |
| --- | --- |
| Busy | Wait for the current operation to finish |
| Inactive client | Prepare the client through Configure, then read the profile before selecting again |
| Verification failed | A write may have arrived. Reconnect and check the actual profile before another attempt; no automatic retry or restoration |

The [reminder setting contract](settings-reference.md#reminder-profile-selection) defines the exact checks.

## Edit one reminder duration

Change one sitting or standing duration for Profile 1/2/3:

1. Leave the desk stationary with an active client and valid reminder readings.
2. Select **Off** or another profile. Editing the active profile is refused; profiles never switch automatically.
3. Enable the required duration entity in its settings, then open the device page's **Configuration** section.
4. Type **1–60 whole minutes** into the number box. This is a duration, not a clock time.
5. Check the result. For a failure, follow the [profile recovery table](#choose-a-reminder-profile) before trying again.

No travel range is needed. All six inputs and the standard-time button are disabled by default for new entities. Existing names and enablement choices are preserved. Read-only sensors stay enabled; hiding an input changes neither panel reminders nor Bluetooth polling.

Each action has a limited effect:

| Action or value | Effect |
| --- | --- |
| Edit one duration | Preserve its paired duration, other profiles and flags; pairs need not total 60 minutes |
| Existing value outside 1–60 | Keep it visible; never clip or overwrite automatically |
| **Profile 1: use standard time** | Set only profile 1 sitting time to **55 minutes**; no factory reset, backup restore or automatic execution after reconnect/failure |
| Disable reminders | Select **Off**, not zero minutes |

**Hardware evidence covers only 50/55 sitting minutes in inactive profile 1.** Other fields and values have simulated coverage. The input range is integration policy, not medical guidance or an established firmware limit.

Panel edits appear after the ordinary 300-second refresh; about five to six minutes of delay is consistent with this policy. HA edits publish after their own verified acknowledgement/readback. See the [complete interval contract](settings-reference.md#edit-reminder-durations).

## Choose panel units

Choose your preferred units for the panel without changing units, height calibration or the height range in Home Assistant. You don't need to configure a height range for this setting.

1. Leave the desk stationary and wait for Home Assistant to connect.
2. On the LINAK device page, open **Configuration → Preferred panel units**.
3. Choose **Metric** or **Inch**. Metric doesn't let you choose between centimeters and millimeters.

The selection shows the saved preference, not necessarily what the panel displays right now. The panel may still display the previous unit after saving. This action doesn't move the desk; don't move it just to refresh its display.

If Home Assistant says the desk isn't ready, open **Configure** and prepare it for control before trying again. If the desk is busy, wait for the current action to finish. If saving can't be confirmed, wait for the connection to return and check the setting before another attempt.

## Set measured command bounds

Enter the actual lowest and highest desktop heights from measurements or verified product data for this desk. Do not infer them from favorite positions or let the integration probe mechanical extremes.

| Behavior | Result |
| --- | --- |
| Save bounds | Validate them against the current reference and position; do not move |
| Missing bounds | Target and memory travel remain unavailable; Stop can work with a ready connection |
| Corrected reference invalidates old bounds | Request revised bounds instead of silently expanding them |
| Empty memory slot | Its travel button is unavailable; other valid slots keep their original numbers |
| Unavailable memory group | All stored-height sensors and memory buttons are unavailable until a complete read succeeds; height and target controls can remain available |
| Target outside bounds | Reject it without movement |

Host command bounds do not override the desk's firmware limits or anti-collision behavior. No verified remote minimum/maximum query exists yet.

## Use the native controls

The slider uses 1 cm steps inside inward-rounded measured bounds. The height sensor follows measured position live.

- The slider holds its previous value during travel.
- It updates to the measured height 0.5 seconds after this integration finishes a movement, whether from the slider, a stored-position button or Stop. The last position sample of such a move can still report a small speed, so the finished movement counts as stationary.
- It also updates when a stationary position stays unchanged for 0.5 seconds, including physical-panel changes. The speed must then read zero.
- Intermediate travel heights are not slider targets or separate slider history entries.

Calibration inputs, raw diagnostics and stored-position targets retain decimal precision; new height history records use whole centimeters.

Before either a target or stored-position drive, the integration checks client readiness and prepares the existing identifier only if inactive. It verifies preparation before wake/target commands. Stored-position drive re-reads that slot and the reference; it does not overwrite the saved position.

For another target, wait for completion or press **Stop** first. Commands are not queued or resumed after reload/reconnect.

| Situation | What happens |
| --- | --- |
| Press Stop during a request | Interrupt it with control Stop and reference-input release; no activation, wake or new target |
| Stop succeeds | Finish the interrupted request without an error notice; keep the ready link |
| Stop or cleanup fails/is ambiguous | Report an error and discard the session; check physical stopping |
| Press Stop again during cleanup | Share the same Stop operation |
| Select another target while busy | Reject the new request without changing the ongoing move |

A busy refusal is not evidence of a disconnect or failed active move. The rejected automation still receives an action-validation error. HA 2026.10.4 also logged this refusal at `ERROR`; check the message and connection state, not log color alone.

### Operation sensor

It shows what the integration is doing with the desk and how the last request ended.

| State | Meaning |
| --- | --- |
| `idle` | Nothing is running. It is also the resting state about 10 seconds after a result |
| `preparing`, `moving`, `stopping` | A request is running |
| `completed`, `interrupted`, `failed` | The result of the request. A failure adds a `reason` attribute |

- Use it to see whether a request is still running or how the last one ended.
- About 10 seconds after a result it returns to idle, so an automation can notify on the result (`to: completed`, `interrupted` or `failed`).
- The finished result stays in the `last_result` attribute, with `last_reason` for a failure.
- A refused request does not change it, and it stays available when the connection drops.
- A movement started on the desk panel is shown too, with `source: panel` and no `requested_height_cm`. It starts `moving` when height feedback reports speed after a stationary reading, and completes after about one second of zero speed. A request from Home Assistant replaces it. If the Bluetooth link drops during a panel movement, the status returns to idle instead of failing, because the integration only watched that movement.
- When the desk reports a fault on its error characteristic, for example the collision code E54 on the panel display, the sensor shows `failed` with reason `desk_error` and the raw frame in `error_code`. This is the desk's own report, not an inference. [Observed pairing →](hardware-results.md#desk-error-frames)
- If a panel movement turns back by more than 1 mm against the direction it first travelled, the result is `failed` with reason `reverse_motion`. That can be the desk's own anti-collision reversal, but it is inferred from position. The integration does not read the panel's error code (for example E54), so the display remains the source for the actual code.
- It does not show scheduled state reads. They can still refuse a new request with the busy message while it reads idle or completed.
- It reports the request, not physical arrival.

[How the phases change →](movement.md#operation-status)

### Keep connected switch

It is your choice to hold the desk's Bluetooth link. Use it to release the link on purpose, for example to rule out this integration during diagnostics.

**Enable it first.** It is a configuration entity and is disabled by default. Open the desk's entities in **Settings → Devices & services**, select Keep connected and enable it. For existing entries the intent starts on.

| Action | What happens |
| --- | --- |
| Turn off | LINAK does no radio lookups, connections or polls. Readings show unavailable and the Connection sensor stays off. The choice survives a Home Assistant restart |
| Turn off during a move | The desk stops first. If that Stop cannot be confirmed, the action reports a failed Stop: check the desk immediately and use the physical panel |
| Turn on | One normal connection and fresh reads of every value. It never sends a target, calibrates or activates the panel client |
| Turn on, desk unreachable | The action reports a failure, the switch stays on and Home Assistant retries on its normal schedule |

Releasing the link is not evidence that the panel sleeps or that its display turns off.

[How ownership works →](architecture.md#deliberate-connection-ownership)

## Test native controls at the panel

Clear the travel path, have physical stopping available and disable any other integration controlling the same desk. Use HA alone, not the standalone BLE runner at the same time. Review the actual/reference height and bounds before each attempt.

**This is an acceptance checklist, not permission to run experiments.** Agree the test scope with the maintainer first.

<details>
<summary>Supervised hardware acceptance steps</summary>

| Step | Action | Pass condition and record |
| --- | --- | --- |
| 1 | Add/update the desk and range | Existing sensors and controls appear without spontaneous movement |
| 2 | Press Stop while idle | No motion/wake and no silent action error |
| 3 | Choose a nearby whole-centimeter target above the actual height | Correct direction, observed stopping and measured final height; account for rounding of the current sensor; Operation passes through preparing, moving, stopping and completed, then returns to idle after about 10 seconds with the result in `last_result` |
| 4 | During another agreed nearby move, press Stop | Observe physical stopping and delay, not only the HA action result; Operation ends interrupted without an action error |
| 5 | Repeat a nearby downward target | Correct direction and final height |
| 6 | Review a saved height/path, then test its button | Correct destination and unchanged stored value |
| 7 | Test scoped reload/unload during motion | Stop attempted, cleanup settles, no continued/resumed target; Operation starts idle after the reload |
| 8 | Reconnect/restart once stationary | Fresh readings; no motion until another explicit action |
| 9 | Turn Keep connected off while stationary, wait past one polling interval, then turn it on | Readings unavailable and the Connection sensor off while released; no reconnect without the switch; a fresh read and no motion after turning it on |
| 10 | Turn Keep connected off during an agreed nearby move, then restart HA while it is off | The desk stops before the link drops and Operation ends interrupted; after the restart the switch is still off and nothing connects |

The native slider has no standalone runner's 2 cm experiment cap. Choose the test target deliberately from the fresh actual height, not a rounded value copied from another desk. Do not continue after unexpected direction, failure to stop, a reference disagreement or repeated action errors.

</details>

## Interpret and report the result

A successful action means its software path completed, not that a person independently confirmed physical stopping. Keep integration revision, HA/OS version, actual backend, panel/variant, measured bounds, initial/target/final heights and the physical observation for each attempt.

Use the [diagnostic manual](diagnostics.md) to interpret unavailable entities and the reason logged before cleanup. RSSI can remain available after a session failure because it comes from advertisements. Readable sensors do not establish client readiness or motion support on a Limited/OEM-restricted variant.

The [hardware evidence](hardware-results.md) distinguishes observed activation, calibration and limited movement feedback from full target/Stop validation still pending. The [standalone runner](movement-test.md) is a separate research tool with its own ownership and preparation requirements.
