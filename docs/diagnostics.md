# Desk readings and Bluetooth diagnostics

## What belongs where

Height, stored positions and reminder profiles are ordinary `sensor` entities. They describe how the desk is used. They remain read-only; reminder times are configured durations, not elapsed counters. Existing unique IDs are unchanged. HA updates the integration-defined category of existing entities on setup while retaining user names and enabled/disabled choices.

Height offset stays Diagnostic: it is the technical reference used for converting raw positions. A future writable setting would need its own verified control. No settings, radio-enable, pairing, restart or movement switch is introduced.

## Transport entities

| Entity | HA type | Default | Meaning |
| --- | --- | --- | --- |
| Connection | `binary_sensor`, connectivity | Enabled | A ready session with validated desk readings; off after link loss |
| Bluetooth signal strength | `sensor`, signal strength, dBm | Disabled | RSSI of HA's latest connectable advertisement |
| Bluetooth backend | `sensor`, enum | Disabled | Allowlisted backend of the active client, such as local BlueZ or ESPHome |

All three have the Diagnostic category. Enable optional entities in Settings → Devices & services → Entities, including disabled LINAK entities in the filter. Enabling an entity publishes its readings in HA; it does not change the desk.

RSSI comes from HA's public Bluetooth cache APIs, using connectable observations. It is not a controller measurement of an active GATT link and may come from a scanner other than the connected adapter. Do not use it to identify which proxy carries the connection. It becomes unavailable when HA no longer considers the advertiser present, when no advertisement exists, or for the Bluetooth unknown RSSI marker (127). The entity does not retain stale values as a current reading. No additional scan, active scan request or GATT query is made. Updates follow the shared coordinator. While enabled, RSSI also rechecks the cached value/presence every 60 seconds, independently of coordinator success. This prevents stale RSSI when repeated connection failures suppress coordinator notifications. Its timer is removed when the entity is unloaded; disabled entities create no timer. These updates do not run for every advertisement. A quiet connected desk can have an unavailable RSSI sensor.

Backend is unavailable without a connected client. Unknown identifiers are mapped to Other managed backend without publishing their raw value. HA can expose a generic proxy wrapper rather than a specific ESPHome backend ID; report Other in that case instead of guessing the proxy type. It is a category, not an adapter name, MAC, source ID or signal measurement. Connection stays available and reports off when the desk session fails, while ordinary desk readings become unavailable. These entities require a successfully loaded integration; first-onboarding failures still use the setup error/logs.

## Local identity and safe downloads

The device registry contains its configured name and Bluetooth address. A native name obtained from cached HA metadata or the optional GAP Device Name read can replace an integration-supplied LINAK fallback. Explicit device name_by_user is preserved; an existing LINAK config-entry title is not assumed to be user-owned or automatically renamed. Separate name/MAC sensors would duplicate this metadata and create unnecessary history. The address supplements the existing device identifier without changing entity unique IDs. Local device metadata can therefore identify the desk to its owner.

The downloadable diagnostic file omits names, Bluetooth addresses and adapter identifiers. Its Bluetooth section contains only signal_strength and an allowlisted backend category, alongside the existing readiness, last stage and read results. Manually shared screenshots or HA/upstream debug logs still need identifier removal.

## Validation and next hardware test

Tests use synthetic Bluetooth, device/entity registries and failure/recovery in real in-process HA. Physical values and UI layout on the owner's installation remain to be checked after updating to 0.1.0a5. This update does not require bond removal and does not establish automatic first-pairing or proxy stability.

## Home Assistant references

- [Entity categories](https://contributors.home-assistant.io/core/quality-scale/entity-category/)
- [Device registry](https://contributors.home-assistant.io/core/integrations/device-registry/)
- [Bluetooth integration APIs](https://contributors.home-assistant.io/core/integrations/bluetooth/)
