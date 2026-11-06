# DPG1C hardware evidence and validation limits

This register explains what was tested, how it was tested and which conclusions the observations support. It covers one DPG1C, not every LINAK desk. Software implementation and simulation are recorded separately from physical observations; short target arrival is trace-observed, while full-range travel and physical Stop accuracy remain unverified.

## Test environment and evidence classes

Read each conclusion within the recorded environment and its evidence class. Unknown firmware details remain unknown.

| Item | Recorded environment or constraint |
| --- | --- |
| Panel | DPG1C; standard device information reports LINAK A/S and model family DPG |
| Research host | macOS CoreBluetooth for initial service/read inspection |
| HA host | Earlier investigation: Raspberry Pi 4B, HAOS 18.4 and HA Core 2026.10.4. Later native-use/startup observations below: HA Core 2026.11.0 |
| Confirmed control-test backend | Local BlueZ; this does not validate ESPHome or mixed-adapter behavior |
| Firmware/OEM variant | Exact firmware and Full/Limited SKU not established |
| Source material | Private logs/captures and public synthetic/configuration fixtures; no names, addresses or client identifiers published |

| Evidence | Meaning |
| --- | --- |
| Trace-observed | A captured exchange or state transition supports the observation |
| Owner-observed | A person reported the physical/UI result without a corresponding captured proof |
| Simulated | Automated tests verify software behavior with synthetic BLE |
| Unverified | The experiment did not establish the claimed behavior |

## Local and proxy connection establishment

**Question:** why can the first post-restart connection fail through a nearby local adapter while a later proxy attempt succeeds?

**Method:** correlate HA Core 2026.10.4, habluetooth 7.1.2 and bleak-retry-connector 4.7.1 logs with actual scanner allocations and backend diagnostics. For bounded direct BlueZ comparisons, pause only LINAK, capture local HCI events, attempt a connection and read HEIGHT if connected, then close the diagnostic client and restore LINAK. Compare ordinary advertising, a temporary active scan and an owner-enabled pairing window. No movement or application-setting write is part of these comparisons.

| Condition | Observation | Supported conclusion |
| --- | --- | --- |
| Post-restart mixed paths | Two local connection timeouts end setup after 41.446 seconds; the next HA setup retry connects through ESPHome in 1.85 seconds | The old two-attempt cap can end setup before HA's path selection reaches a working proxy |
| Local direct connection | Timeout after 18 seconds despite roughly −60 dBm advertisements and free local slots; HCI reports `ADV_NONCONN_IND`, with no LE Create Connection command | Advertisement strength alone does not establish connectability; this capture does not show a failed over-the-air connection attempt |
| Temporary active scanning | Another 18-second timeout with only nonconnectable advertisements | Active scanning alone did not restore local connectability in this comparison |
| Pairing enabled on the panel | Connectable advertisement followed by LE Create Connection about 2 ms later; successful link completion about 7.15 seconds later and a four-byte HEIGHT read | The local host can connect and read when this panel advertises connectably |
| Cleanup | Diagnostic clients closed and LINAK verified enabled/loaded after each comparison | The comparisons did not intentionally leave the integration disabled |

**Implementation consequence:** preserve the connector's normal retry policy inside the existing refresh deadline, allowing HA to reconsider the path without an intervening failed config-entry setup. The regression test uses the real retry connector with synthetic transport failures; it does not emulate the radio or prove physical proxy failover after the change.

**Uncertainty:** these observations do not establish why the proxy can recover when the local path waits, whether peer/bond state affects panel advertising, or whether the behavior generalizes to other firmware. They do not prove radio interference or command overload. A later controlled local/proxy reconnect comparison needs both peripheral advertising and actual connection ownership, not RSSI alone. The retry change still needs post-restart hardware acceptance and does not make two local timeouts fast.

## Extended configuration reads

**Question:** can a DPG1C provide the configuration needed for centimeter sensors without movement or settings writes?

**Method:** inspect services, subscribe to DPG notifications and send capabilities, offset, four memory and reminder queries serially. Require the expected response type and length before advancing. Close the connection after the read sequence.

**Observation:** the Mac completed all seven configuration reads. Direct reading of the DPG channel alone returned `ff`, whereas notification/query exchanges returned decodable configuration. Position feedback contained a valid four-byte sample.

The public fixture records this initial configuration snapshot. It predates later calibration and must not be used as the desk's current state or as default bounds:

| Field | Fixture value | Interpretation limit |
| --- | --- | --- |
| Capabilities | Four slots; automatic up/down, Bluetooth, display and light flags set | Flags do not prove supported control behavior on the current connection |
| Reference mask | `01` | First reference reported; no mechanical-limit inference |
| Offset | 6800 raw units | 68.00 cm under the current interpretation |
| Memories 1–4 | 1204, 1438, 5152, 5696 raw units | Converted with that snapshot's offset: 80.04, 82.38, 119.52, 124.96 cm |
| Active reminder profile | 3 | Configuration, not occupant activity |
| Sitting/standing pairs | 55/5, 50/10, 45/15 minutes | Three configured profiles, not elapsed counters |
| Reminder flags | `3b` | Unverified bits remain raw; no physical-light-state claim |

**Conclusion:** extended reads work on this panel and supply a per-panel reference. Unknown counters remain uninterpreted. No movement, wake, reset or setting write belonged to this read-only experiment.

## Bluetooth authentication

**Question:** why could local connection/subscription attempts fail despite discovery and earlier Mac reads?

**Method:** compare host/controller pairing evidence with a scoped manual `NoInputNoOutput` agent, then verify HA read availability and restart behavior.

**Observation:** host traces showed missing agent confirmation. Manual pairing completed and BlueZ reported Paired/Bonded; HA loaded the sensors. A Core restart reconnected without another panel pairing interaction. The owner also reported working sensors after a full Pi restart, but that reboot was not independently trace-verified.

**Conclusion:** host authentication was a distinct failure layer. The implemented private same-bus application-agent path follows that requirement; a fresh unbonded end-to-end run of that path remains unverified. These results do not establish proxy pairing or explain every intermittent disconnect.

## Stored-position response ordering

**Question:** why did integration state duplicate one memory and shift later slots?

**Method:** compare a passive radio capture with a system-bus observer, then reproduce duplicate notification bursts in a simulated client.

**Observation:** the radio capture contained one reply per memory request while the bus observer received 24 distinct `PropertiesChanged` signals for each reply. All slot replies shared type `07` and lacked a slot identifier. The previous client could accept a delayed duplicate as the next slot's result.

**Conclusion:** response assignment was vulnerable to duplicate delivery. Capabilities barriers between memory requests reproduce and prevent that assignment failure in simulation while retaining equal saved positions. The cause of the signal multiplication and the corrected client's physical behavior require separate validation.

## Setup session continuity

**Question:** why could initial validation succeed but preparation after the name form time out?

**Method:** follow one complete setup trace through successful reads, disconnect and the next connection attempt.

**Observation:** validation reached `ready`, the integration deliberately disconnected, and subsequent preparation attempts timed out before any panel setting write.

**Conclusion:** reopening a link between foreground forms introduced an avoidable failure opportunity. The wizard now retains its session and transfers it to runtime. Automated HA tests complete setup when every connection after the first is rejected, and cover abort/expiry. This repairs the software lifecycle; it does not prove long-term radio reliability.

## Height-reference calibration

**Question:** can a measured desktop height correct the panel reference without changing mechanism position or saved raw positions?

**Method:** inspect stationary position/reference and client status, test the protected reference setter, activate the existing client when necessary and verify independent readback. Preserve the 16 identifier bytes and do not issue motion commands.

**Observation:** an offset-only write returned `0b 00`, and three reads retained the old reference while client status was inactive. Preserved-identifier activation returned `01 00` and read back active status. The subsequent reference correction returned `01 00`; three reads matched the correction with unchanged relative position and zero speed. A separate connection confirmed the corrected height and active status.

**Conclusion:** activation plus acknowledged/read-back calibration worked on this panel without observed mechanism movement. That reconnect does not establish permanent active status, power-cycle persistence, another firmware's encoding or the detailed meaning of `0b`.

## Client readiness and movement

**Question:** does readable height imply the current DPG client can execute a target?

**Method:** use local BlueZ, inspect feedback during one nearby HA target and compare it with a separately authorized preserved-identifier activation followed by a target 0.5 cm higher. End the latter attempt with scheduled Stop after 0.8 seconds.

| Condition | Trace observation | Supported conclusion |
| --- | --- | --- |
| Readable but inactive client | Repeated target writes; position stayed stationary and speed zero; no-progress guard sent Stop before cleanup disconnected | The disconnect followed the failed movement path; initial radio loss was not the cause of that attempt |
| Readiness preparation | Status changed `0` → `1`; identifier bytes were unchanged | Protected activation/readback succeeded on the current connection |
| Target after preparation | Feedback included nonzero speed and a small position change | Panel response differed from stationary feedback; complete travel was not established |
| Scheduled Stop | Test interrupted at its 0.8-second limit and reported interrupted motion | The test cannot claim target arrival or physical stopping accuracy |
| Recovery | Diagnostic connection closed; HA entry restored and verified enabled/loaded | No diagnostic client or disabled entry intentionally left behind |

Offset, name and stored-position settings were not written. This evidence supports checking client readiness before explicit control, not activating clients during background polling. It does not establish status persistence, downward travel, unattended safety or a universal root cause for adapter-dependent behavior.

## Target release, interruption and quiet idle

**Question:** can a target followed by Stop and another saved-position request leave the panel or HA control path unusable, and does dense logging demonstrate outgoing command flooding?

**Method:** compare the owner's logs with the pinned `idasen` Stop implementation. Pause the native entry to reserve local BlueZ, run isolated candidate code without installing it into HA, and restrict targets to nearby 0.5 cm moves within configured bounds. Record channel writes and feedback, wait for a real target packet before requesting Stop, then request a saved position only when it is within 1 cm of the initial position. Restore the native entry after each test. No offset, name, memory or reminder setting is changed.

| Evidence | Observation | Interpretation |
| --- | --- | --- |
| Owner trace | Two targets reached their exact raw position; each used eight target writes, separated by 0.295–0.367 seconds | These captured loops do not show uncontrolled target flooding |
| Previous Stop path | Sent control `ff 00` without reference-input `01 80`; explicit interruption discarded the native connection even after successful Stop | Missing reference release differs from upstream; deliberate disconnect explains one subsequent unavailable path |
| Notification capture | Repeated identical position/speed pairs arrived several times; polling reads could republish the same sample | HA update/log volume is not the same as outgoing BLE command volume |
| Earlier bounded attempts | A short overall deadline expired during preparation; other attempts hit the old one-second feedback deadline or failed movement | Not every experiment succeeded; successful runs do not establish general radio stability |
| Candidate short travel | A 0.5 cm target produced a 50-raw-unit position change and completed | Short target arrival is trace-observed on this panel |
| Candidate interruption | Stop was requested after the first height-target write; both Stop frames completed, the link remained ready, and the next nearby saved-position request completed | Successful explicit interruption can preserve ownership and the same live session for the next action |
| Quiet idle | The isolated candidate stayed connected for 62 seconds after the sequence, with zero outgoing writes and zero new published position samples | Its movement loop and publication path stopped; this test excludes HA's periodic settings refresh |
| Cleanup | Native LINAK entry restored and enabled/loaded; competing IKEA entry retained its existing disabled state | Diagnostic ownership ended; the installed HA component was not replaced |

**Conclusion:** use the two-channel Stop contract, preserve a sound link after explicit interruption, keep read deadlines separate from Stop deadlines and suppress identical telemetry publications. Slider history should record settled heights while the measurement sensor remains live.

**Limits:** OLED state and physical double-tap response were not observable remotely. The release frame is therefore not proof that the reported physical-panel freeze is resolved. The official [DPG user manual](https://cdn.linak.com/-/media/files/user-manual-source/en/deskline-dpg-desk-panels-and-desk-control-app-user-manual-eng.pdf) distinguishes the height OLED from the reminder light strip and documents a four-hour reminder-light timeout; that is not an OLED sleep specification. The inspected `idasen-ha` connection manager also retains a connection. A persistent GATT link alone does not establish why this panel's display remained lit. A controlled visual comparison with and without periodic reads remains necessary before changing connection policy or firmware settings.

## Startup retry and mixed-backend diagnosis

**Question:** why did a configured entry spend repeated attempts at startup without reaching its first validated read?

**Method:** compare the supplied full-night log with the installed client checksum and the tested HA/connector source. Inspect transport package versions without opening a new BLE connection or changing installed code. Separate initial setup retries from later idle failures.

**Observation:** initial attempts repeatedly ended at 20 seconds, while bleak-retry-connector 4.7.1 itself budgets 20 seconds per connection attempt. First validated reads arrived roughly 13 minutes after the first attempt. Later evidence includes an ESPHome GATT connection error, two idle link losses and a memory-read timeout. The HA wrapper reported backend `other`; its remote path can expose a generic class/metaclass identifier rather than the implementation category.

**Conclusion:** the equal outer and per-attempt budgets can cancel connection setup before service discovery/subscription/reads finish. Deferring radio work through HA's pre-running `ConfigEntryNotReady` started-event path avoids blocking bootstrap, while the ordinary post-start refresh budget permits complete attempts. An allowlisted backend-module fallback and timed-out query name improve subsequent evidence.

**Limits:** equal budgets do not establish the cause of every failed connection, proxy GATT error or idle loss. The proposed startup change has simulated lifecycle/deadline coverage, not a completed cold-start hardware result. It does not pin the local adapter, remove a proxy, change polling cadence or prove the overnight disconnects are fixed.

## Native use, startup and deliberate connection release

**Question:** what do the latest native HA observations establish about controls and recovery before 0.1.0?

**Method:** distinguish the owner's physical reports from the maintainer's summaries of passive logs and stationary connection-switch observations on 2026-11-05. After an owner-installed update/restart, the installed component files matched revision `717a718` and HA reported 2026.11.0. No agent-issued movement belonged to these observations. Earlier observations without a revision/backend record cannot be retroactively assigned to that deployment.

| Evidence | Observation | Supported conclusion and limit |
| --- | --- | --- |
| Owner-observed native controls | The owner confirmed movement using the HA slider and Stop | Native controls worked in the reported use; no measured full-range arrival, Stop delay or overshoot was recorded |
| Owner-observed physical memory and recovery | The owner later used a physical-panel favorite, reported a BLE disconnection and said the entities returned without restarting or pairing | Recovery was reported in this instance; no time-aligned trace establishes the cause or complete panel handback |
| Passive native observation | In 300 seconds, five refreshes succeeded with zero recorded native link-loss, reconnect or timeout events | A bounded quiet interval, not a long soak or proof that losses cannot occur |
| Updated native startup | Three timeouts preceded a connection after about 2 minutes 40 seconds, then four refreshes succeeded | Eventual startup recovery on that deployment; not fast, repeated or backend-complete startup acceptance |
| Stationary Keep connected off | One 90-second observation confirmed connection intent false and connected state false | Deliberate release was observed once, not panel sleep or OLED behavior |
| Stationary Keep connected on | One 90-second observation contained three attempts, two timeout messages and a failed refresh, without ready/recovery | Requested reconnection did not complete in that window. Later recovery was not observed; this is neither proof of permanent failure nor attribution to the driver |

**Conclusion:** retain these as bounded evidence, including the failed reconnect observation. The final connection intent was restored to true. Software retry behavior and the observed link state must remain distinct; no settings, firmware or connection-policy change follows from these records alone.

**Limits:** these summaries do not pass H1–H12. Physical Stop accuracy, complete travel, repeatable handback, long-term recovery, OLED behavior and independent backend coverage remain open. No further hardware experiment is part of release preparation; the acceptance plan remains in force.

## Reminder profile setting

**Question:** can a BLE reminder profile change preserve the remaining settings without activation, wake or movement?

**Method:** the owner first correlated physical Profile 3/Off/Profile 3 with the low two reminder flags bits. A separately approved, single-owner BLE trial then wrote Profile 3 → Off → Profile 3 using fresh reminder data, exact application acknowledgements, capabilities barriers and independent reminder readback. Raw captures and device identifiers remain private.

**Observation:** both writes returned `01 00`, and independent `88` replies confirmed the requested profiles, unchanged unrelated flags and all six intervals. Initial client status was 1. No activation, wake or motion was sent. The raw counter changed; its meaning remains unknown. After verified restoration, a later transport check failed. Subsequent independent native HA reads at 09:59 and 10:01 UTC on 2026-11-05 showed ready/idle, Profile 3, all stored positions and the other settings restored apart from that counter.

**Conclusion:** this is hardware evidence for Off/Profile 3 selection at observed status 1 on one DPG1C. It supports preserving the fresh seven-byte setting body and ignoring the read-only counter in setter verification. The software select additionally exercises profiles 1/2 in simulation.

**Limits:** profiles 1/2 and status-0 writes were not hardware tested. Later native reads show recovery, not long-term stability, persistence across reconnect/power loss or validation of the current implementation installed in HA. This trial did not test interval, other-flag or unit setters; the separate interval result follows below.

For owner acceptance, explicitly agree one supervised sequence covering Profile 1 and Profile 2 with independently observed panel behavior, fresh readback and restoration to the recorded original profile. Keep all interval bytes and unrelated flags unchanged, use one BLE owner and stop on uncertain delivery without blind restoration. Separately confirm that a status-0 software request is refused without a setter or activation. Testing whether the device itself accepts writes at status 0 needs a new scoped research experiment; it is outside this software feature.

## Single reminder interval

**Question:** can one sitting duration be changed independently of the selected profile, standing duration and unrelated settings?

**Method:** in a separately authorized stationary trial, the research owner changed inactive profile 1 sitting duration 55 → 50 → 55 minutes. Each write used the fresh complete reminder body, strict application acknowledgement and an independent `88` query. Immediate checks covered the reminder body, position, reference and capabilities; subsequent independent native HA reads checked the full saved-position/name/configuration state. Captures and identifiers remain private.

**Observation:** both writes returned `01 00`, and independent replies matched the requested seven-byte bodies. Profile 3 stayed selected; all flags and the other five durations were unchanged. In particular, 50 minutes sitting with 5 minutes standing was accepted without normalization to 60. No activation, wake or motion was sent. The raw reminder counter changed and remains uninterpreted. Final native checks confirmed connected/ready/idle, preserved four favorites, name, geometry, offset and capabilities.

**Conclusion:** 50 and 55 are accepted values for this one inactive-profile field on the tested DPG1C at client status 1. This supports a protected single-field setter, not a requirement for each sitting/standing pair to total one hour.

**Limits:** the trial did not validate every value from 1 to 60, the source application's 1–255 bounds, zero, other fields, active-profile edits, actual countdown timing or persistence. The six HA duration inputs and profile 1 standard-time button are software implementations tested with synthetic BLE, not deployed or hardware-accepted by this trial. Their 1–60 range is an integration input policy, not medical or firmware limits. All six byte addresses are backed by the pinned community layout and independent UI fields, not six hardware experiments. Tests verify isolated byte changes, fresh-state active-profile refusal/no-op, preserved flags/counter handling, ACK/readback failures and real HA services. Any further physical test needs its own approved scope and must stop on uncertain delivery without retry or blind restoration.

## Stored unit preference and physical display

**Question:** does the reminder unit flag select a persistent panel preference, and does it uniquely identify the displayed unit?

**Method:** in one authorized stationary trial, the research owner wrote Inch and restored the original metric flag using fresh complete settings, exact application ACKs and independent `88` reads. A deliberately new connection checked the stored inch flag before restoration. A separate trial added the source-backed `FE 00` display activation. Finally the owner selected physical CM → MM → CM while a passive observer recorded normal native reads. Raw captures, screenshots and identifiers remain private.

**Observation:** both writes in the first trial returned `01 00`, independent readbacks matched every requested body byte, and Inch remained stored on the new connection. Geometry, height reference, four favorites, durations and name were preserved; only the uninterpreted counter changed. Fresh client status was 1; there was no activation, wake or motion in that trial. No time-aligned physical Inch confirmation was obtained before restoration. In the separate wake trial the owner reported a stuck display, used height controls manually and then saw inches. The experiment stopped without automatic restoration; the owner confirmed the desk stopped and restored CM through the physical menu.

**Metric sub-unit:** physical MM was subsequently confirmed by the owner. Newly received complete thirteen-byte `88` replies in MM and restored CM were byte-identical, including the counter. All known decoded state was identical too. This proves neither a unique MM getter nor a setter. Clear `0x04` is shared by physical CM and MM. No guessed `0x80`, other bit or vendor command was tried.

**Conclusion:** bit `0x04` is a stored inch versus non-inch/metric preference with ACK/readback and one ordinary reconnect evidenced on this panel. That is the scope of the HA configuration select. Native centimeter geometry and HA unit conversion must remain separate.

**Limits:** immediate stationary OLED redraw is unconfirmed. The manual height operation confounds the wake trial; `FE 00` alone is not shown to cause, be necessary for or be sufficient for the visual change. The implementation therefore sends no wake, movement or forced reconnect. Power-cycle persistence, exact CM/MM encoding, other variants and preservation of panel-local MM across unrelated whole-body `88` writes remain unverified. The select is covered by synthetic protocol/native-client/real-HA tests, not a deployment or new physical acceptance run. The owner's separate Core update during the metric observation does not expand the integration's supported-version claim.

## Desk error frames

**Question:** does the desk report a fault such as a collision over Bluetooth, or only on its display?

**Method:** the client subscribes to the error characteristic `99fa0003` and logs each raw frame with the last position, without decoding it. During panel movement the owner stopped the desk against an obstruction and read the code on the display. No collision was induced by an agent.

| Evidence | Observation | Interpretation |
| --- | --- | --- |
| Frame on a fault | Twice, the desk stopped, a three-byte frame `01 00 5d` arrived while the position was near 3300 and 3647, and the display showed E54 | On this DPG1C the error characteristic notifies, and this frame coincided with E54 in both events |
| Frame on clearing | About 1.5 seconds later an empty frame arrived. The position had risen by about 3 cm, which is a retreat | An empty frame marks the fault as cleared, and the desk retreated by itself |
| Scope | One desk, one panel firmware, one displayed code, two events | The meaning of other frames and the encoding of other E-codes are not established. The integration reports the raw frame and does not name it |

The Operation sensor reports a non-empty frame as `failed` with reason `desk_error` and the frame in `error_code`.

## Hardware acceptance matrix

This matrix is a test plan and evidence index, not twelve successful hardware tests. Existing observations retain their limited scope. For each execution record revision, HA/backend versions, known model/firmware, initial conditions, expected result, actual result and sanitized trace/physical observation. A failing or incomplete run stays recorded as such.

| ID | Scenario | Acceptance evidence | Current evidence |
| --- | --- | --- | --- |
| H1 | Start/reconnect on a bonded local host | Valid reads, bounded setup/retry and no activation or movement from background setup | Local reads/reconnect observed; later HA 2026.11.0 startup recovered after timeouts, but one Keep connected on trial did not recover in 90 seconds; repeated-start acceptance pending |
| H2 | Fresh unbonded onboarding | Complete pairing and setup without a manual agent; no movement | Manual bond evidence only; automatic fresh-host run pending |
| H3 | Targets in both directions | Feedback, physical direction and measured final height within the declared test tolerance; no replay | Nearby arrivals trace-observed and native slider movement owner-reported; complete acceptance pending |
| H4 | Stop during target travel | Physical stop, measured delay/overshoot, two-channel cleanup and a new explicit command afterward | Stop/release and next-command sequence trace-observed; native Stop owner-reported, measured physical accuracy pending |
| H5 | Slider/favorite/Stop bursts | No competing packet streams or delayed goals; physical panel remains usable | Simulated burst/Stop ownership tests; supervised hardware run pending |
| H6 | Link loss during motion | Observe local controller behavior, bound failed operations and never resume the old goal after recovery | Simulated failure paths; scoped physical observation pending |
| H7 | HA reload/restart during motion | Distinguish graceful unload's Stop attempt from abrupt process loss; no goal replay afterward | Simulated unload cleanup; physical lifecycle run pending |
| H8 | Physical panel handback | Manual controls and double-tap favorites work after HA move/Stop without unplugging | Earlier freeze prompted release fix; later physical favorite use, BLE loss and automatic entity return owner-reported; repeatable handback and cause unverified |
| H9 | Proxy-only and mixed adapters | Repeat onboarding, reads, travel and Stop with actual backend/path evidence for each environment | Local BlueZ control evidence only |
| H10 | Calibration/settings persistence | Before/after reference and exact raw memories, no unintended movement, agreed restart/power-cycle readback | Activation/calibration and one reconnect observed; power-cycle result pending |
| H11 | Idle session and display | Count settings queries/control writes, reconnects and freshness gaps; visually compare OLED with/without periodic reads | Short isolated capture had no outgoing writes; later 300-second native observation had five successful refreshes and no recorded native link loss/reconnect/timeout; long soak and periodic-poll/OLED comparison pending |
| H12 | Competing local client/integration | Actionable conflict, no silent takeover and no unexpected movement | Configured-entry conflict guard covered by synthetic HA tests; physical competing-client acceptance pending |

Choose travel distances, repetitions and stopping tolerances before the test. Respect manufacturer duty-cycle and local safety constraints, keep physical stopping access and terminate on a failure. Loss of BLE can prevent remote Stop; a successful API call cannot prove the mechanism stopped. Do not induce destructive interference or clear a working bond as an incidental test setup step.

For an idle soak, select and report the duration rather than implying that a short quiet capture represents days of stability. Do not infer OLED sleep from a reminder-light timeout. A second independent device/firmware result is needed before broad compatibility claims.

Use the [investigation method](bluetooth-research.md) to design each next test. Update this register by research question and conclusion, not by appending a personal work diary. Detailed chronology and private captures remain in the local handoff workspace.
