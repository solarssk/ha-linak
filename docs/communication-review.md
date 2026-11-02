# Compare existing Idasen and DPG implementations

Existing projects already implement substantial LINAK communication behavior. This comparison identifies which contracts can be reused and which differ from a DPG1C integration with centimeter heights, a panel reference and extended settings. It is a dependency/design reference, not a claim that a particular library fixes every observed failure.

## Comparison baseline

The inspected HA 2026.10.4 [Idasen manifest](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/idasen_desk/manifest.json) pins `idasen-ha==3.0.1`. Its [dependency declaration](https://github.com/abmantis/idasen-ha/blob/3.0.1/pyproject.toml) accepts `idasen>=0.13.1,<0.14`; the inspected host used 0.13.1. Compare these versions rather than an unpinned latest branch.

| Layer | Existing contract | Reuse or adaptation needed |
| --- | --- | --- |
| HA entity | HA exposes an Idasen percentage cover | Percentage is an entity choice, not a BLE requirement; retain the native centimeter number/buttons |
| Connection | `idasen-ha` uses HA BLE metadata, bleak-retry-connector, pairing and one connection manager | Reuse HA's transport ownership; compare retry and cleanup policy |
| Height conversion | `idasen` uses a fixed 0.62 m reference and 0.62–1.27 m bounds | Read the panel reference and use measured/verified bounds per device |
| Movement target | Lower `idasen` accepts meter targets; the public HA wrapper accepts percentages | A narrow adapter can expose centimeters without changing protocol units |
| Feedback | Height notifications and changed-value filtering | Preserve measured feedback and avoid needless HA publication |
| Extended configuration | DPG libraries decode capabilities, reference, memories and reminders | Maintain serialized query validation and per-frame evidence |
| Application readiness | DPG1C wakeup includes a user-ID write | Preserve the existing identifier, check status and verify acknowledgement/readback rather than copying a fixed identity |

The [HA wrapper](https://github.com/abmantis/idasen-ha/blob/3.0.1/idasen_ha/__init__.py) and [lower library](https://github.com/newAM/idasen/blob/v0.13.1/idasen/__init__.py) expose different target surfaces. A centimeter UI alone does not justify a separate Bluetooth stack. Per-panel reference, bounds, settings and ownership behavior are the actual adaptation requirements.

## Movement contract differences

These differences are research questions, not instructions to copy behavior into production without a scoped test.

| Contract | Inspected upstream | Current integration | Required decision/evidence |
| --- | --- | --- | --- |
| Reference and bounds | Fixed IKEA values | Live panel offset and configured centimeter bounds | Do not infer mechanical limits from either source |
| Readiness identity | Wakeup writes a user-ID payload | Conditional activation preserves and verifies the existing identifier | Readiness must hold on the control connection; polling remains read-only |
| Initial control ordering | Wake before control Stop | Control Stop before wake | Compare ordering only in a bounded experiment |
| Stop frames | Control `ff 00` and reference-input `01 80` | Control `ff 00` followed by reference-input `01 80` | Shared bounded cleanup; physical-panel handback still needs observation |
| Target loop | Version-specific keepalive/feedback policy | Serialized target, 0.2-second wait and fresh read | Compare effective latency, not only the configured wait |
| Recovery | Connection manager schedules retries and closes stale links | Coordinator refresh retries; ambiguous query/control failures discard the session | Never resume an old target after recovery |

The [pinned idasen implementation](https://github.com/newAM/idasen/blob/db7cdd246d4ccb6e09ee3dfe83d192d9a5623b5b/idasen/__init__.py) and [connection manager](https://github.com/abmantis/idasen-ha/blob/3.0.1/idasen_ha/connection_manager.py) are the comparison sources. Upstream's DPG1C initialization is also discussed in [issue 32](https://github.com/rhyst/linak-controller/issues/32#issuecomment-1784055470). Neither source replaces the [hardware evidence](hardware-results.md).

## Extended configuration differences

Community DPG implementations provide command catalogues and write/read patterns beyond the Idasen wrapper. Those are candidates for a small protocol layer, not a reason to expose every setting as a writable entity.

| Requirement | Current handling | Limit |
| --- | --- | --- |
| Correct per-panel height | Read `0x81`; protected measured-height correction | Not a travel-limit query |
| Correct memory slot assignment | Type/length validation and capabilities barriers | Memory responses have no slot identifier |
| Unknown counters/flags | Preserve raw fields | No invented occupancy, usage or state meaning |
| New setters | Allowlist, acknowledgement, readback and side-effect scope | Memories/reminders/name writes remain unimplemented |
| Device variants | Record model, firmware and capabilities | Product labels alone do not prove remote control support |

The [protocol reference](protocol.md) owns exact frames; the [settings reference](settings-reference.md) owns source revisions and implementation status.

## State and traffic design

Current reads share coordinator availability and a 60-second full refresh. A durable snapshot of last-read settings with a visible age is not implemented. A future optimization must separate:

| State | Freshness requirement | Must not do |
| --- | --- | --- |
| Live telemetry | Fresh position and connection status | Present stale height as current |
| Last-read configuration | Known read time and reconciliation after reconnect/panel edits | Authorize movement solely from cached settings |
| Host preferences | Durable HA configuration | Silently write firmware settings or replay a target |

Notifications should provide height feedback; target keepalives exist only during explicit movement. Two libraries must not independently own connections to the same panel. A dependency migration must preserve cancellation, final Stop, bounds, per-device reference, setting verification and redaction before replacing the current client.

## Criteria for adopting an upstream dependency

Accept a configurable dependency or narrow adapter only when it can satisfy the current public contract:

1. Retain one HA-managed transport and current adapter metadata.
2. Use per-device reference and bounds without global class-constant changes.
3. Preserve the panel identifier and separate pairing from application readiness.
4. Serialize DPG queries and handle ambiguous/duplicated replies.
5. Preserve foreground-only side effects, Stop priority and bounded cleanup.
6. Demonstrate matching behavior with synthetic HA tests and scoped hardware evidence.

No dependency migration is implied by this comparison. Unresolved behavior is listed in the [investigation plan](bluetooth-research.md#next-tests-that-can-change-a-conclusion).
