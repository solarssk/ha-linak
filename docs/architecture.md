# How the integration manages desk state and control

LINAK Desks is a native Home Assistant integration distributed through HACS. Home Assistant owns discovery and adapter selection; one coordinator and one BLE client own each configured desk. The initial hardware target is DPG1C, not every LINAK actuator or product family.

## Component boundaries

An entity requests an operation through the coordinator. It never creates a Bluetooth connection itself.

```mermaid
flowchart TD
    accTitle: Integration component boundaries
    accDescr: HA entities share one coordinator and BLE client; protocol parsing and movement remain separate.
    UI[HA entities and configuration] --> Coordinator[LinakCoordinator]
    Coordinator --> Client[DeskClient]
    Client --> Protocol[Pure frame decoders]
    Client --> Motion[MotionController]
    Client --> Connector[HA Bluetooth and bleak-retry-connector]
    Motion --> Link[Existing BLE session]
    Connector --> Link
    Link --> Panel[DPG1C panel]
    Panel --> Feedback[Position notifications]
    Feedback --> Client
    Client --> Coordinator
```

| Component | Responsibility | Boundary |
| --- | --- | --- |
| `config_flow.py` | Discovery, setup, explicit preparation and configuration | No movement during setup; HA naming does not rename the panel |
| `setup_session.py` | One-time transfer from setup to runtime | Transfer stays in memory and expires if unconsumed |
| `coordinator.py` | Shared state, availability, polling and HA action errors | Uses the existing client; does not resume old targets |
| `client.py` | Connection, pairing, subscriptions, serialized queries and exclusive operations | Discards ambiguous sessions rather than assigning uncertain replies |
| `protocol.py` | Frame validation and decoding | No Bluetooth I/O or setting policy |
| `calibration.py` | Measurement proposal and offset encoding | No transport or unrestricted setting-write API |
| `motion.py` | Target loop, feedback guards and Stop cleanup | Uses an already connected, exclusively owned session |
| Entity platforms | HA values, units, categories and actions | Publish measured feedback, not an assumed target result |

## Entity contract

Centimeters are the primary height interface. A `number` entity supports that interface without a percentage-based cover or a custom frontend card.

| HA surface | Data or action | Category |
| --- | --- | --- |
| Height sensor | Current position plus panel offset | Ordinary sensor |
| Stored-height sensors | Saved mechanism positions plus current offset | Ordinary sensors |
| Active profile and profile-duration sensors | Reminder configuration read from the panel | Ordinary sensors |
| Target height number | Whole-centimeter target within measured bounds; state follows actual feedback | Control |
| Stored-position buttons | Freshly read slot passed to the common movement controller | Controls |
| Stop button | Interrupt an active operation or send Stop while idle | Control |
| Offset sensor | Technical reference used in height conversion | Diagnostic |
| Connection binary sensor | Current client readiness | Diagnostic, enabled by default |
| Signal strength and backend sensors | Advertisement RSSI and active backend category | Diagnostic, disabled by default |

Raw position, offset and stored positions retain their precision. Height-related sensor states and new history records use whole centimeters. Slider bounds round inward: `ceil(minimum)` and `floor(maximum)`. The slider uses 1 cm targets; stored-position buttons retain exact stored positions. Presentation rounding cannot expand the command range.

Device identity uses the `ha_linak` domain and Bluetooth address. Existing entity unique IDs remain stable. HA names and `name_by_user` belong to HA registries; they are separate from the advertised/GAP name. Downloaded diagnostics omit those identifiers.

## State and freshness

Live height requires a validated connection and reference. Optional memories and reminders additionally have independent response-validity metadata during runtime refresh; initial setup and calibration verification still require complete validated reads.

| State | Source | On disconnect | Persistence |
| --- | --- | --- | --- |
| Position and speed word | Height reads and notifications | Ordinary readings become unavailable | No target or motion replay |
| Offset | Required serialized reference read | Dependent readings become unavailable with the link | No assumed reference from a previous generation |
| Memories and reminders | Serialized optional groups with validity and last-success age | Cached objects remain only in memory; their entities report unavailable when the group or link is invalid | No durable snapshot or stale-as-live values |
| Measured command bounds | HA options | Retained for later validation | Stored in the config entry; do not program firmware limits |
| Explicit HA name | HA entry and device registry | Retained | Stored independently of discovery metadata |
| RSSI | HA connectable advertisement cache | Can remain available independently of the session | No extra GATT request |

Config-entry setup defers all radio work until HA reaches running, using HA's started-event retry. The initial post-start connection/read has the 60-second refresh budget plus bounded cleanup; HA owns later retries and platforms are created only after a successful read. The normal runtime check reads capabilities, offset and position every 60 seconds. Height notifications update position between these checks without resetting the polling deadline; identical samples are not republished. Memories and reminders have independent five-minute due checks based on each group's last successful monotonic timestamp. A skipped read preserves both its last value and timestamp. Invalid groups retry on the next runtime check without rereading a healthy group that is not due. Reconnection, changed capabilities or a changed offset forces both groups to be read. Foreground setup/calibration keeps full reads; movement still reads its conversion reference and selected memory under exclusive ownership.

| Freshness term | Meaning in this integration | HA behavior |
| --- | --- | --- |
| Not read | No validated value in this process/session | Unknown data is never substituted with zero |
| Valid live height | Position from this ready session plus its validated reference | Notifications publish height; periodic reference/position checks continue during notification traffic |
| Valid last-read setting | A successfully decoded group in this ready session | Displayed until a scheduled check, reference change or disconnect; age is time since the group read, not since any notification |
| Invalid group | A completed matching reply failed decoding | That group's entities are unavailable; another group's valid read can remain available |
| Lost or ambiguous session | Disconnect, timeout, invalid reference or other transport failure | All ordinary readings become unavailable; cached objects are diagnostic history only |

The five-minute interval is an explicit software read policy, not evidence of an overloaded controller or proof that the OLED sleeps. During an unchanged four-slot session, the synthetic request count is two extended reads per normal check instead of ten; a due full check retains the existing memory barriers. Polling yields while control owns the client, so deadlines are not hard real-time guarantees. The number entity holds its last settled height during travel while the measurement sensor stays live. All timeouts still invalidate the transport generation; recovery creates a session with fresh required data and settings, never a cached height or queued target. Operation-result entities and deliberate connection ownership remain separate roadmap work.

## Operation ownership

One desk must have one active owner of its BLE connection. The [cross-integration check](onboarding.md#one-integration-per-desk) rejects known enabled IKEA entries for the same address before new LINAK I/O. Idle refresh releases our connection on conflict; Stop and cleanup retain their existing ownership rules. This registry check is not a system-wide Bluetooth mutex. The client reserves a foreground operation before awaiting I/O and uses one query lock to serialize its exchanges.

| Operation | Shared lock/ownership | Possible panel side effects |
| --- | --- | --- |
| Discovery or ordinary refresh | Serialized reads | GATT writes carrying read requests only |
| Confirmed setup preparation | Foreground preparation | Verified activation of the existing client when inactive |
| Confirmed height calibration | Calibration reservation and query lock | Verified activation and one offset correction |
| Explicit target or stored-position drive | Movement reservation and query lock | Verified client activation if needed, then wake/target/Stop |
| Stop | Separate shared Stop task; preempts motion | Control Stop and reference release when idle; no activation or height target |
| Unload/shutdown | Waits for owned cleanup | Attempts final Stop and releases the link |

A second target or calibration cannot compete with an active operation. Cancellation and unload wait for bounded cleanup. A session failure never queues a target for later reconnect. See the [movement reference](movement.md) for the controller and the [settings reference](settings-reference.md#height-calibration-contract) for calibration.

## Connection and recovery

The [connection lifecycle](onboarding.md) defines authentication, setup transfer and retry. HA supplies current connectable device metadata; the integration does not force `hci0`, clear unrelated bonds or choose a proxy by name.

A backend disconnect cancels pending I/O. Ambiguous query failures invalidate the session because some DPG replies do not identify their request. The coordinator attempts recovery through its normal refresh schedule and reports stale readings unavailable. Reconnection performs reads only; a later explicit control request must validate its own readiness and bounds.

## Supported environment and evidence

Automated tests run against HA 2026.10.4 with simulated Bluetooth. The [hardware evidence](hardware-results.md) covers one DPG1C on macOS and a Raspberry Pi 4B. Complete target arrival, physical Stop accuracy, fresh unbonded onboarding and mixed-adapter stability remain open validation work. No Home Assistant quality-scale award or HACS default-catalog acceptance is claimed.

## Proposed state and library contracts

This section defines the intended refactoring boundary, not implemented state fields or a published library API. The [delivery plan](roadmap.md#delivery-order) sequences migration and acceptance tests. Keep runtime fixes small while the contract is established.

| Model | Required information | Trust boundary |
| --- | --- | --- |
| Telemetry sample | Raw position, speed word, observation time and connection generation | A sample from a closed generation cannot become current after reconnect |
| Configuration snapshot | Reference, memories, reminders, per-group read time and validity | Last-read configuration is not permission to move; unknown/unsupported differs from a failed read |
| Connection state | Disconnected, connecting, authenticating, ready, recovering or deliberately suspended | Suspension must not trigger a polling-driven reconnect; readiness is not a movement result |
| Operation result | Operation identifier, kind, requested goal, phase, start/end time and typed outcome/reason | Reject competing goals without queueing; successful explicit Stop is interrupted rather than failed |
| Device capabilities | Protocol flags, implemented operations and evidence-supported model/firmware scope | An advertised bit does not establish a working setter or compatibility with another family |

A settings snapshot may be displayed as last-read data only with explicit freshness semantics. Fresh height needs a valid sample and reference for the current connection. An offset change invalidates derived height and configured control assumptions until reconciled; it must not silently reinterpret old measurements. Reconnect can recover telemetry before optional settings, but cannot authorize target travel from an uncertain reference or memory response.

```mermaid
flowchart TD
    accTitle: Proposed library and HA ownership boundary
    accDescr: HA owns discovery and entities while one injected library session owns protocol and movement.
    HA[HA discovery and adapter selection] --> Session[One injected BLE session]
    Session --> Protocol[Protocol and response correlation]
    Protocol --> State[Telemetry and settings models]
    Protocol --> Motion[Exclusive bounded movement]
    State --> Adapter[HA coordinator and entities]
    Motion --> Result[Typed operation result]
    Result --> Adapter
```

| Responsibility | Future library | HA integration |
| --- | --- | --- |
| Transport | Accept injected BLE device/connector and callbacks; own one session | Resolve HA Bluetooth candidates and connection policy; do not add a second reconnect manager |
| Protocol | Validate/decode frames, correlate requests, invalidate ambiguous generations | Translate supported data and errors into HA concepts |
| Movement | Bound targets and I/O, prioritize Stop, retain cleanup ownership | Accept explicit actions and provide translated busy/error messages |
| Settings | Separate pure preview from explicit acknowledged writes/readback | Present confirmation and persist host preferences |
| Lifetime | Explicit async connect/close, removable subscriptions and bounded cancellation | Config-entry startup/retry, unload and registry lifecycle |
| Diagnostics | Typed reasons, durations and counts with no raw private identifiers by default | HA diagnostics/redaction, repairs and diagnostic entities |
| Capabilities | Describe known protocol support without assuming every model works | Create only supported entities and preserve existing entity identity |

Start with the existing protocol/calibration models and narrow transport interfaces. Library modules must not import HA, and entities must not parse wire packets. Use typed immutable snapshots/events at the boundary rather than exporting the client's mutable state or backend exceptions as a public API. Select public method and package names in the extraction design; this table is not a promise that a `python-linak` package already exists.

Before changing the import path, run the same synthetic frame, duplicate-response, cancellation, Stop, bounds and redaction cases against the candidate library and HA adapter. Keep packet-order or polling-policy changes in separate reviewed patches. Validate dependency license compatibility, source distribution, tagged version and public build/publish provenance before publishing or adding a package dependency. The [HA library requirements](https://contributors.home-assistant.io/core/integrations/api-library/) own those external acceptance rules.
