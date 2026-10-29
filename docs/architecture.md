# Integration architecture and user interface

## Product contract

Native Home Assistant custom integration distributed through HACS. Runtime is entirely on Home Assistant. Use Home Assistant Bluetooth management for device selection, direct adapters and supported active proxies. macOS is only a research environment.

DPG1C is the initial supported device. Keep protocol parsing independent of HA entity code and BLE transport so other verified LINAK device families can be added without assuming every device implements DPG commands.

## Entity model

| Entity | Meaning |
| --- | --- |
| Height sensor | Actual height including device offset, displayed in cm; updates from physical controls too |
| Target height number | Requested destination in cm, box mode; setting explicitly starts a move after movement implementation is validated |
| Stop button | Explicit stop, cancelling an active target operation |
| Memory 1–4 buttons | Drive to a device-stored height, only when a position is configured |
| Stored-height sensors | Device-stored positions with offset, read-only initially |
| Reminder configuration | Read-only initially; later select/number entities for verified settings |
| Offset | Read-only diagnostic/configuration initially; do not expose a write control before verification |

Actual and target height are separate states. Never publish the requested destination as measured height. Do not restore and execute a target after restart/reload/reconnect. Do not queue delayed movement across disconnection. Keep a single movement task; stop/cancel takes precedence. Do not infer occupancy from height.

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
2. Target-height/stop and stored-position controls after supervised hardware validation.
3. Reminder and offset writes with readback and unrelated-bit preservation.

Repository: solarssk/ha-linak (public). Minimum supported Home Assistant: 2026.10.4, matching the tested release.

## References

- https://github.com/home-assistant/core/blob/dev/homeassistant/components/idasen_desk/cover.py
- https://contributors.home-assistant.io/core/entities/number/
- https://contributors.home-assistant.io/core/integrations/bluetooth/
- https://www.hacs.xyz/docs/publish/integration/
