# Implementation plan

1. Completed: query capabilities, offset, four memories and reminders on the Mac; implement strict parsing and captured fixtures. Native read-only HA configuration, entities and lifecycle are implemented with simulated-BLE tests initially on HA 2026.10.2, now validated on HA 2026.10.4 after the uv security update. Real Raspberry Pi/proxy validation remains pending.
2. Implement the asynchronous BLE client using Home Assistant's Bluetooth device selection and connection management. Support direct adapters and compatible active ESPHome proxies. No separate daemon or Mac dependency.
3. Add UI config flow, duplicate prevention, connection validation, retry, unloading and reconnection. Use the domain `ha_linak` to avoid replacing the built-in `idasen_desk` integration. Document connection contention with the built-in integration and phone app.
4. Expose verified reads first. Keep unknown capabilities out of user-facing controls. Redact diagnostics and mark stale readings unavailable.
5. Add explicitly initiated movement, stop and target height after supervised hardware tests; then implement settings with readback verification and preservation of unrelated bits.
6. Validate against the user's actual Home Assistant version and Raspberry Pi Bluetooth environment. Test unavailable devices, malformed responses, lost connections, reloads and shutdown.
7. Complete manifest, English/Polish translations, brand assets, license selection, hassfest and HACS validation after repository identity is agreed. Publish only after hardware and HA checks pass.

HACS is the distribution method; this remains a custom integration, not a promise of acceptance into Home Assistant Core or HACS's default catalog.
