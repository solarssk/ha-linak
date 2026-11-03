# Reliability, device support and the path to HA Core

The goal is a dependable native Home Assistant integration for LINAK desks: useful configuration without a phone app, predictable centimeter controls and evidence that another maintainer can reproduce. DPG1C is the first validation target. Other desk panels need their own capability and transport evidence; LINAK medical products are outside the current scope.

This is an implementation plan, not a claim of HA Core acceptance, Platinum status or broader hardware compatibility. The [architecture](architecture.md) describes current behavior and the proposed library boundary. The [hardware evidence](hardware-results.md) owns observations and acceptance results.

## Findings and decisions

The external architecture review examined revision `e909e8f`. Its findings are assessed against the implementation, including the subsequent competing-control fix, rather than copied into a new feature list.

| Finding | Assessment | Decision and completion evidence |
| --- | --- | --- |
| Physical Stop, recovery and panel handback | Release validation gap, not proof of a particular firmware defect | Complete the hardware acceptance matrix; transport completion alone cannot pass a physical test |
| Configuration failure makes ordinary readings unavailable | Runtime optional decoding failures are now isolated per group; transport ambiguity still discards the session | Separate reference/position checks and per-group due reads are implemented; preserve generation-discard recovery and validate idle/backend behavior on hardware |
| Monitoring requires control preparation and bounds | Confirmed in the current setup flow | Add an optional monitoring-only path with no activation or bounds; preserve the normal native-control setup path |
| Another HA integration can own the same desk | Implemented configured-entry check for the same normalized address | Setup, calibration, new motion and idle refresh check enabled IKEA entries; Stop/cleanup remain available and no other entry is modified |
| Memory replies can cross request boundaries | Protocol ambiguity remains: type `07` has no slot identifier | Add cross-barrier delayed-duplicate replay cases; retain fail-closed behavior and document what a barrier cannot prove |
| Successful Stop appears as an action failure | Addressed by the competing-control fix | Keep HA regressions for confirmed Stop, failed Stop, bursts and unexpected cancellation |
| Settings read cadence | Runtime reference/position checks every 60 seconds; independent five-minute memory/reminder due checks | Synthetic request-count regressions verify skipped reads; measure latency and OLED behavior on hardware before claiming load/sleep improvements |
| Connection controls and operation status | Useful missing user-facing behavior | Expose deliberate connection ownership and separate commanded goal, measured height and operation result |
| Separate PyPI library | Required for a Core contribution; not needed to repair each current bug | Define and test the boundary, then extract behavior without changing wire ordering in the same PR |
| Additional settings and desk panels | Research candidates, not supported features | Validate each setter/model independently before exposing entities |

A failed optional query cannot simply be ignored on the same session. Once a timeout makes request/reply assignment uncertain, discard that transport generation. The state split must preserve that rule while distinguishing a last-read setting from fresh telemetry after a valid recovery.

## Delivery order

Each row is a scoped change with its own tests and review. Hardware validation runs alongside the software work; broad refactoring does not substitute for it.

| Order | Deliverable | Acceptance condition |
| --- | --- | --- |
| 1 | Telemetry/configuration state contract | Implemented reference/setting freshness contract and monotonic group ages; operation state remains a separate UI deliverable; no cached height represented as live |
| 2 | Split settings refresh from live telemetry | Implemented per-group validity/ages and independent due reads, notification-safe reference polling and full reconnect recovery. Keep timeout/generation and fresh-control regressions; physical idle/backend validation remains |
| 3 | Cross-integration conflict handling | Implemented normalized-address checks and EN/PL recovery messages; disabled/ignored entries and other desks do not block. Registry checks cannot arbitrate an unfinished external wizard or an operation already underway |
| 4 | Optional monitoring and explicit connection ownership | Monitoring performs no activation, calibration or motion; deliberate disconnect suppresses background reconnect until the user requests connection; unload removes callbacks and pending tasks |
| 5 | Operation state for UI and automations | Distinguish preparing, moving, stopping, completed, interrupted and failed; report a reason without recording every feedback tick as a new goal |
| 6 | Protocol replay and capability model | Reproduce known duplicate, late-response and disconnect sequences; distinguish advertised flags, implemented support and hardware validation |
| 7 | Library extraction and package release | Preserve transport injection, single ownership, bounds, Stop, cancellation and redaction through parity tests; reproducible public package release before consuming it as a dependency |
| 8 | Verified settings and more desk panels | One scoped setter/model at a time with acknowledgement, readback, preserved unknown bits and independent hardware evidence |
| 9 | Stable HACS release and Core proposal | Complete applicable acceptance rows, document compatibility, verify installed release, then prepare a minimal Core contribution after architecture feedback |

Connection status and operation status are separate. A rejected second target is not a failed connection; a completed transport write is not proof of physical arrival. The [movement reference](movement.md#competing-requests) defines the existing no-queue policy, which must survive every refactor.

## Evidence and release gates

Use the [hardware acceptance matrix](hardware-results.md#hardware-acceptance-matrix) for physical tests. Record the tested revision, HA version, actual backend, firmware when readable, expected/observed behavior and sanitized evidence. Unknown firmware remains unknown, and RSSI is advertisement data rather than proof of the active path.

| Gate | Required evidence |
| --- | --- |
| Repeated normal use | Up/down targets, saved positions, Stop, physical panel handback and mixed input sequences; record failures as well as successes |
| Idle and recovery | A planned soak with reconnect counts, request/write counts, gaps and visual OLED observations; distinguish deliberate reloads from spontaneous losses |
| Backend compatibility | Independent local BlueZ, proxy-only and mixed-adapter results; one passing path does not validate the other two |
| Settings integrity | Calibration and future setters preserve unrelated fields, verify readback and test agreed restart/power-cycle persistence |
| Regression quality | Current-head tests, meaningful branch coverage and replay fixtures; evaluate a required coverage regression gate before a stable release |
| Dependency transparency | Distinguish direct-pin audit from the complete resolved environment; review the transitive scan scope and ownership of HA-managed dependencies |
| Product claims | Supported features/models match hardware evidence and release artifacts; no borrowed quality-scale badge |

The review's suggested 100 motion cycles and 72-hour soak are candidate project targets, not HA requirements or completed tests. Select repetition counts and duration for each experiment, respect the mechanism's documented duty cycle and stop a failing experiment instead of running an unattended motion loop to reach a number. No finite cycle count guarantees physical safety.

## HA Core and quality-scale strategy

Current HA guidance requires protocol/API communication in a separate Python library on PyPI and a minimal Bronze-level initial integration PR, normally one platform. Those constraints shape the extraction boundary; they do not require removing useful HACS features. See [Create an integration](https://contributors.home-assistant.io/core/integrations/create/) and [Build a Python library](https://contributors.home-assistant.io/core/integrations/api-library/).

Platinum is a long-term engineering target. Track applicable rules with evidence and justified exemptions using the official [quality scale](https://contributors.home-assistant.io/core/quality-scale/) and [tiers](https://contributors.home-assistant.io/core/quality-scale/tiers/); do not claim a tier from a test count or overall coverage alone. Strict typing and async dependencies need explicit assessment, including the extracted library.

Before proposing a new Core domain, resolve overlap with `idasen_desk` discovery and discuss whether a new LINAK integration or an extension is appropriate. The existing `ha_linak` domain and entity identifiers remain stable during HACS development. A package name, new repository, PyPI publication, manufacturer contact and Core submission are separate decisions, not implied by this roadmap.
