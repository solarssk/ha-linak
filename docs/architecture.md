# Integration architecture and user interface

## Product contract

Native Home Assistant custom integration distributed through HACS. Runtime is entirely on Home Assistant. Use Home Assistant Bluetooth management for device selection, direct adapters and supported active proxies. macOS is only a research environment.

DPG1C is the initial supported device. Keep protocol parsing independent of HA entity code and BLE transport so other verified LINAK device families can be added without assuming every device implements DPG commands.

## Entity model

| Entity | Meaning |
| --- | --- |
| Height sensor | Actual height including device offset, displayed in cm; updates from physical controls too |
| Target height number | Native slider in cm; reports actual height and setting it explicitly starts a move within measured bounds |
| Stop button | Explicit stop, cancelling an active target operation |
| Memory 1–4 buttons | Re-read the selected slot before moving; unavailable when empty |
| Stored-height sensors | Device-stored positions with offset, read-only initially |
| Reminder configuration | Read-only initially; later select/number entities for verified settings |
| Offset | Read-only diagnostic/configuration initially; do not expose a write control before verification |
| Connection binary sensor | Diagnostic ready-session state; off after link loss, independent of coordinator read availability |
| Signal strength / backend sensors | Optional, default-disabled diagnostics from HA's advertisement cache / active client's public backend category |

The number slider and height sensor both report actual device feedback. Never publish the requested destination as measured height. Do not restore and execute a target after restart/reload/reconnect. Do not queue delayed movement across disconnection. Keep a single movement task; stop/cancel takes precedence. Do not infer occupancy from height.

No cover entity in the initial model: its position contract is 0–100 percent, which does not match the requested primary user interface. A centimeter number entity follows the HA number contract without a custom frontend card.

Travel bounds must come from verified device data or explicit user configuration; do not invent bounds or probe mechanical extremes automatically. Hardware limits and UI validation limits are distinct.

## Lifecycle and quality

- UI config flow with discovered-device selection, unique IDs and connection validation.
- Async BLE client, serialized extended requests, response validation and timeout. Memory responses share a response type; no concurrent queries or request advancement after uncertain timeouts without resynchronization.
- Coordinator for shared state and connection lifecycle; platform entities do not open independent BLE connections.
- Mark stale readings unavailable; reconnect with bounded backoff; unload cancels tasks and disconnects cleanly.
- Diagnostics redact address, name and identifiers.
- English/Polish UI and docs, extensible translations with parity checks.
- pytest tests covering protocol fixtures, mocked BLE failures, real HA config flow/setup/unload, unavailable entities and movement cancellation.
- Ruff, mypy, hassfest, HACS checks and a minimum/latest supported HA compatibility matrix before release.

Reuse project organization and release discipline from the local ztm_warsaw reference, not its cloud polling behavior. Choose supported HA versions after inspecting the actual target installation.

## Milestones

1. Installable read-only HACS alpha validated in real HA with a simulated transport and then Raspberry Pi hardware.
2. Native height slider/Stop and stored-position controls; supervised hardware validation pending.
3. Reminder and offset writes with readback and unrelated-bit preservation.

Repository: solarssk/ha-linak (public). Minimum supported Home Assistant: 2026.10.4, matching the tested release.

## References

- https://github.com/home-assistant/core/blob/dev/homeassistant/components/idasen_desk/cover.py
- https://contributors.home-assistant.io/core/entities/number/
- https://contributors.home-assistant.io/core/integrations/bluetooth/
- https://www.hacs.xyz/docs/publish/integration/

## Entity categories and identity

Height, stored heights and reminder profiles are regular sensor entities. Offset remains diagnostic because it is a technical height-reference parameter. Backend and signal-strength sensors are diagnostic and disabled by default; Connection is a diagnostic binary_sensor enabled by default. Onboarding sets movement bounds and Options Flow changes them later; there is no movement-enable switch. No panel-setting write is implied. Existing product sensor IDs are preserved.

DeviceInfo uses the existing domain/address identifier and also a Bluetooth connection identifier. Names and the address are local device metadata rather than extra entities. Downloaded diagnostics contain only allowlisted transport categories and RSSI, without raw advertisement or client objects. See [diagnostics](diagnostics.md) for freshness and lifecycle limits.

## Control session ownership

Onboarding collects host-side centimeter bounds. Options Flow changes them later and reloads the entry. No target is restored or sent from configuration. Client movement reserves a single task before its first await, shares the existing connection and lock with extended queries, and rejects competing targets. Fresh offset and selected-memory reads are serialized before motion. Periodic polling yields without disconnecting a moving desk when advertisements expire. Height feedback continues to publish actual position.

Stop has a separate shared task and bypasses the polling lock. Movement cancellation settles final Stop before discarding the connection; unload waits for the same cleanup. A Stop transmission is not proof of physical stopping, and a failed cleanup is propagated to the Stop action. Number state follows measured height after setup, physical panel changes and movement feedback. Saving options never executes a target.
