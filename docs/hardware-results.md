# DPG1C hardware read results — 2026-10-29

The Mac successfully subscribed to notifications on the DPG characteristic and sent seven serialized read requests (`7f <command> 00`) using GATT writes with response. Each query received one response before the next query. The connection was closed after completion. No movement, wake, reset or configuration-write commands were sent.

## Results

| Item | Result |
| --- | --- |
| Capabilities | Four memory slots, automatic up/down, Bluetooth, display and light flags set |
| Reference mask | `01` (first reference reported) |
| Height offset | Raw 6800; interpreted as 68.00 cm |
| Memory 1 | Raw 1204; 80.04 cm including offset |
| Memory 2 | Raw 1438; 82.38 cm including offset |
| Memory 3 | Raw 5152; 119.52 cm including offset |
| Memory 4 | Raw 5696; 124.96 cm including offset |
| Selected reminder profile | 3 |
| Profile 1 | 55 minutes sitting / 5 standing |
| Profile 2 | 50 minutes sitting / 10 standing |
| Profile 3 | 45 minutes sitting / 15 standing |
| Reminder flags | `3b`; community mapping: centimeters, automatic up/down and wake set, light-guidance bit clear |

Height, timing and flag interpretations follow the referenced community implementations. Actual panel/app values have not yet been compared. The light bit does not prove that the physical light is off. Capability flags do not prove automatic movement has been tested or is enabled in every context.

Four memory responses and the reminder response also contain counters. They are preserved without assigning an unverified meaning such as use count, uptime or total cycles.

Public fixtures contain only configuration response bytes and unknown counters, with no device name, Bluetooth identifier or location. Private discovery/connection logs remain outside the project.

## What the initial Mac test proves

Extended read access works on this particular DPG1C. It does not yet prove compatibility with other firmware, setting persistence, movement behavior, Raspberry Pi pairing or ESPHome proxy operation. The later Raspberry Pi results below extend this initial evidence; automatic first pairing and proxy validation remain pending.

## Raspberry Pi pairing investigation — 2026-10-31

Environment reported during the supervised investigation: Raspberry Pi 4B, HAOS 18.4, Home Assistant Core 2026.10.4, local BlueZ, DPG1C. Private captures and identifiers are not included here.

- HCI and host logs showed a local pairing failure with no confirmation agent.
- Manual host pairing with a NoInputNoOutput agent completed; BlueZ reported Paired/Bonded and HA subsequently loaded the desk's read-only sensors.
- Following an HA Core restart, logs showed an automatic reconnect without re-enabling pairing on the panel.
- The owner then confirmed working sensors after a full Raspberry Pi restart. Host logs after that reboot were not collected because SSH host-key verification blocked access; persistence is owner-observed rather than trace-verified.
- Some earlier connections disconnected and some motion-notification intervals were irregular. Their causes remain unresolved; no stability guarantee follows.

These observations concern manual pairing with 0.1.0a3. They do not validate the new automatic application-agent path in 0.1.0a4, an unbonded first setup, other panels or ESPHome proxy behavior. No runtime movement feature was enabled.
