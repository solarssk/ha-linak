# DPG1C hardware evidence and validation limits

This register explains what was tested, how it was tested and which conclusions the observations support. It covers one DPG1C, not every LINAK desk. Software implementation and simulation are recorded separately from physical observations; full target arrival and physical Stop accuracy remain unverified.

## Test environment and evidence classes

| Item | Recorded environment or constraint |
| --- | --- |
| Panel | DPG1C; standard device information reports LINAK A/S and model family DPG |
| Research host | macOS CoreBluetooth for initial service/read inspection |
| HA host | Raspberry Pi 4B, HAOS 18.4 and HA Core 2026.10.4 during the recorded investigation |
| Confirmed control-test backend | Local BlueZ; this does not validate ESPHome or mixed-adapter behavior |
| Firmware/OEM variant | Exact firmware and Full/Limited SKU not established |
| Source material | Private logs/captures and public synthetic/configuration fixtures; no names, addresses or client identifiers published |

| Evidence | Meaning |
| --- | --- |
| Trace-observed | A captured exchange or state transition supports the observation |
| Owner-observed | A person reported the physical/UI result without a corresponding captured proof |
| Simulated | Automated tests verify software behavior with synthetic BLE |
| Unverified | The experiment did not establish the claimed behavior |

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

## Validation still required

| Claim | Current status | Evidence needed |
| --- | --- | --- |
| Full upward/downward target arrival | Unverified | Supervised travel with feedback, physical measurement and actual direction |
| Physical Stop and overshoot | Unverified | Interruption during observed motion and measured stopping behavior |
| Automatic first pairing from an unbonded host | Unverified end to end | Scoped fresh-host/backend test without reusing the working bond |
| ESPHome-only and mixed-adapter control | Unverified | Controlled path comparison with actual backend recorded |
| Power-cycle persistence of settings/readiness | Unverified | Agreed restart experiment with before/after reads |
| Other firmware, OEM variants or device families | Unverified | Identified model/variant and independent protocol/control validation |

Use the [investigation method](bluetooth-research.md) to design each next test. Update this register by research question and conclusion, not by appending a personal work diary. Detailed chronology and private captures remain in the local handoff workspace.
