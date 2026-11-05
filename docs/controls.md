# Configure and test desk controls

The device page provides a centimeter height slider, Stop and buttons for positions already saved on the panel. These controls use actual feedback and measured command bounds. Initial tests require someone at the desk; complete travel and physical Stop accuracy are not yet validated across supported environments.

## Configure the desk after installation

Open **Settings → Devices & services → LINAK → Configure**. Choose the task you need:

| Option | What to enter or confirm | What changes |
| --- | --- | --- |
| HA name | A recognizable name | HA entry/device naming; no Bluetooth rename or reconnect |
| Connection preparation | Explicit preparation of the existing panel client | Conditional verified activation; no motion |
| Check/correct height | Whether the current reading matches a tape measurement | A separate confirmation can correct the panel reference |
| Height range | Measured lowest/highest desktop heights | HA command bounds; no motion or firmware-limit programming |

Setup guides you through the same information. To only watch the desk, choose **Monitoring only** on the name step. Nothing is written to the panel and no range is requested. Add the range in Configure when you want controls.

Saved positions are shown from the first setup form and alongside the travel range. They are informational, not physical limits or confirmed tape measurements. Missing measured bounds stay blank, never inferred from favorites. Enter both measured ends before requesting a target or saved-position move. See [saved-position display states](onboarding.md#saved-positions-and-missing-bounds) for empty, unavailable and unsupported slots.

🇵🇱 Pozycje pamięci są widoczne od pierwszego formularza oraz obok zakresu ruchu. To informacja, nie fizyczne limity ani potwierdzone pomiary. Puste pola wymagają wpisania obu zmierzonych granic. Ulubione pozycje nie wypełniają zakresu i nie odblokowują ruchu.

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

In the LINAK device's Configuration section, use **Reminder profile** to choose Off or Profile 1/2/3. It preserves the configured sitting/standing times and other panel flags. It needs no travel range and sends no activation, wake or movement. The existing active-profile sensor remains available for automations.

Wait for valid reminder readings and a stationary desk. A busy operation is refused. If HA reports an inactive client, use explicit control preparation in Configure separately, then read the profile before another selection. A failed verification may follow a delivered write: check the actual profile after reconnecting before trying again. There is no automatic retry or restoration. Profiles 1/2 still need owner hardware acceptance; see the [setting contract](settings-reference.md#reminder-profile-selection).

## Edit one reminder duration

On the LINAK device page, open Configuration and use the sitting or standing time input for Profile 1/2/3. The five new inputs are disabled by default; enable only those you need in the entity settings. Existing **Profile 1 sitting time** keeps its name and registry settings. Type a whole number from **1 to 60 minutes**. This is a number box, not a height slider or a clock time. Use Off or another profile before changing a duration of the selected profile; active-profile interval changes are refused. No profile is switched automatically. The stationary/active-client and error-recovery requirements above apply, without requiring a travel range.

Each edit changes only the chosen duration. The paired duration and all other profiles/flags are preserved, with no requirement for the pair to total 60 minutes. Existing readings outside 1–60, such as 90, stay visible and are never clipped or automatically overwritten. The range restricts newly submitted edits only; it is a product choice, not medical guidance or the panel's established firmware range.

To explicitly set the manufacturer's standard sitting-reminder value, press **Profile 1: use standard time**. It assigns **55 minutes** to profile 1 sitting time using the same protected setter. It is not a factory reset, does not restore all reminder pairs or a saved backup, and never runs on reconnect or failure. Use the separate Off selection to disable reminders, not zero minutes. Only 50/55 in inactive profile 1 have hardware evidence; the other fields and values are synthetic-test coverage. See the [complete interval contract](settings-reference.md#edit-reminder-durations).

Zmiana dotyczy tylko wybranego czasu siedzenia lub stania w profilu 1/2/3. Pięć nowych pól jest domyślnie wyłączonych; włącz potrzebne encje w ich ustawieniach. Dotychczasowy czas siedzenia profilu 1 zachowuje nazwę i ustawienia rejestru. Wpisz 1–60 pełnych minut, po wybraniu Wyłączone lub innego profilu. Przycisk **Profil 1: ustaw standardowy czas** ustawia tylko czas siedzenia profilu 1 na **55 minut**, bez resetu pozostałych pól. Zakres jest zasadą integracji, nie limitem firmware ani zaleceniem medycznym. Na sprzęcie potwierdzono tylko 50/55 w nieaktywnym profilu 1, nie pozostałe pola.

Physical panel changes wait for the ordinary 300-second reminder refresh; about five to six minutes of delay is consistent with this policy. HA changes publish after their own verified ACK/readback. Zmiany na panelu pojawiają się po zwykłym odświeżeniu przypomnień co 300 sekund, więc opóźnienie około 5–6 minut jest zgodne z tą polityką. Zapis z HA aktualizuje stan po potwierdzonym odczycie w tej samej transakcji.

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

Stop preempts an active request. Stop sends control Stop and reference-input release, with no activation, wake or height target. A successful interruption retains the ready link for the next command; failed or ambiguous cleanup still discards it. A successful Stop completes the interrupted action without an error notice. A failed Stop remains an error. During an operation, another slider or stored-position request is rejected with a busy message. Wait for completion or press Stop, then select the new target. Repeated Stop clicks during cleanup share that operation. Failed commands are not queued or resumed after reload/reconnect.

A busy message means that the new command was not accepted; it does not mean that the desk disconnected or the ongoing movement failed. HA classifies it as action validation, and an automation calling the rejected action still receives an error. In HA 2026.10.4 this expected refusal can also appear at `ERROR` level in frontend logs. Check the message and connection state before treating a log entry as a device fault.

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

## Interpret and report the result

A successful action means its software path completed, not that a person independently confirmed physical stopping. Keep integration revision, HA/OS version, actual backend, panel/variant, measured bounds, initial/target/final heights and the physical observation for each attempt.

Use the [diagnostic manual](diagnostics.md) to interpret unavailable entities and the reason logged before cleanup. RSSI can remain available after a session failure because it comes from advertisements. Readable sensors do not establish client readiness or motion support on a Limited/OEM-restricted variant.

The [hardware evidence](hardware-results.md) distinguishes observed activation, calibration and limited movement feedback from full target/Stop validation still pending. The [standalone runner](movement-test.md) is a separate research tool with its own ownership and preparation requirements.
