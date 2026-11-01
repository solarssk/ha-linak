# Communication reuse and state lifecycle review

Reviewed 2026-11-01 against HA 2026.10.4 and the libraries installed on the owner's host. This separates verified implementation behavior from changes still requiring implementation or hardware evidence.

## Existing libraries and reusable layers

HA's [Idasen manifest](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/idasen_desk/manifest.json) pins `idasen-ha==3.0.1`. That package [depends on](https://github.com/abmantis/idasen-ha/blob/3.0.1/pyproject.toml) `idasen>=0.13.1,<0.14`; the inspected host has 0.13.1. Both were read from installed package metadata, rather than inferred from the latest upstream branch.

| Layer | Existing implementation | Reuse boundary |
| --- | --- | --- |
| HA entity | HA exposes a percentage cover | Our centimeter number and buttons can use a different transport implementation; percentages are not a BLE restriction |
| Connection | `idasen-ha` uses HA's BLE device, bleak-retry-connector, pairing, one connection manager and reconnect scheduling | We already depend on the same connector; compare lifecycle behavior before maintaining a separate policy |
| Motion | `idasen` accepts target height in meters, emits target keepalives, reads feedback and implements Stop | Compare exact installed command ordering and cancellation semantics; do not recreate protocol facts from guesses |
| Height | `idasen` subscribes to notifications and suppresses unchanged values | Keep push updates and debounce HA publication; do not continuously read unchanged height while idle |
| Extended settings | Community DPG libraries decode offset, capabilities, memories and reminder profiles | These are not provided by the public `idasen-ha` wrapper; retain a separate serialized, validated DPG query layer |

The [idasen-ha Desk wrapper](https://github.com/abmantis/idasen-ha/blob/3.0.1/idasen_ha/__init__.py) exposes both meter height and percentage height, but its public target method accepts percentages. The [lower idasen library](https://github.com/newAM/idasen/blob/v0.13.1/idasen/__init__.py) accepts meter targets. A centimeter UI therefore does not justify implementing an entire Bluetooth stack independently.

## Important differences from the current client

The inspected `idasen` version uses fixed 0.62 m and 1.27 m bounds and uses 0.62 m as its height reference. These are not queried mechanical limits. The inspected DPG1C returns a 0.68 m offset, so blindly using the IKEA reference would introduce a 6 cm error. Its wakeup also writes a DPG user-ID payload. Adopting the whole library requires an explicit solution for per-device reference/bounds and ownership behavior, without globally changing class constants for every desk.

Its movement sequence sends wake before control Stop, whereas the current implementation sends control Stop before wake. Its Stop sends both control `ff00` and reference-input `0180`; our current implementation only sends control Stop. These are concrete differences to resolve with a scoped protocol test, not proof of the cause of a radio disconnect. They have not been changed or tested physically in the duplicate-memory repair.

The [idasen-ha connection manager](https://github.com/abmantis/idasen-ha/blob/3.0.1/idasen_ha/connection_manager.py) explicitly closes stale connections, prevents competing connect attempts and schedules retries after 30 seconds. Our runtime currently retries through coordinator polling; setup and runtime reconnect budgets need separate review against the observed sparse advertisements. Do not clear unrelated bonds or force one adapter globally.

## Required state model

The maintainer requires automatic import of supported panel data and a simple first-run experience. Requesting manually entered bounds as the normal solution is not the intended product. A successful BLE connection does not prove that firmware travel limits can be queried. No supported min/max read command has yet been established from the inspected DPG sources; offset and stored-position extrema must not be presented as physical travel limits.

Keep three kinds of state distinct:

- Live telemetry: actual height and connection state. A stale height must not be presented as current after link loss.
- Last-read panel configuration: stored positions, offset and reminder profiles. Preserve a validated snapshot with its read time, show when it is stale, and reconcile it after connection recovery. A cached position must not authorize movement without fresh validation.
- Host preferences: integration choices and any fallback configuration. Saving these must not silently write firmware settings or execute motion.

This persistence/freshness model is a requirement from this review, not functionality already implemented. The current sensors share coordinator availability, and their values become unavailable on link loss. A durable snapshot and its HA representation need tests for reload, restart, stale settings and physical-panel edits.

## Traffic and command ownership

Use notifications for height. Read supported settings on connection, after an explicit setting change and on a deliberate refresh schedule. The current client refreshes the complete settings set every 60 seconds; this is not evidence that the desk requires a minute-by-minute keepalive. Reduce unnecessary idle reads only after separating connection health from settings freshness.

Movement keepalives exist only during an explicit move. Stop must preempt that move. One owner must serialize settings queries, movement preparation and final cleanup; two libraries must never manage independent connections to the same desk. A transport failure must not queue or resume a target after reconnect.

The first diagnosed repair is the [duplicate-response barrier](protocol.md#duplicate-memory-responses-on-bluez). Further implementation should use a contract comparison against the exact upstream versions above, then choose a configurable upstream dependency or a narrow adapter. No dependency migration, firmware-setting write, new travel-limit inference or physical movement is part of that repair.
