# DPG1C settings and implementation reference

Reviewed 2026-10-31. This is a research inventory and product plan, not a list of enabled controls. Runtime 0.1.0a7 adds native slider/button movement; panel-settings writes remain unimplemented. Keep native Home Assistant/Raspberry Pi operation and the owner's goal of configuring supported features without a mandatory phone app.

## Evidence levels

- **O**: LINAK documents a product/UI function. This does not establish a BLE command, permissions or support on this particular firmware.
- **C**: An independent implementation provides a protocol candidate; neither manufacturer authority nor our hardware verification.
- **H**: Recorded read results on the owner's DPG1C; see [hardware results](hardware-results.md).
- **S**: Automated simulation proves software behavior, not physical operation.
- **P**: Maintainer-requested design, pending implementation and relevant hardware validation.

## Source register

| ID | Source | Scope and version |
| --- | --- | --- |
| O1 | [LINAK DPG User Manual](https://assets.linak.com/asset/590184044899/document_hub5bdnb5l13pc4ebsja0cc702?content-disposition=inline) | 35 pages, 2026-04, LIT-13-02-060 B. Printed pages 18–19: calibration/units/limits; 25–27: memories/drive; 29–32: reminders/lock/reset. Product installation/operation reference, not a public BLE SDK. |
| O2 | [DPG1C data sheet](https://assets.linak.com/asset/590184044899/document_1660ji82jh2118i2b6r62ilc56?content-disposition=inline) | 7 pages, retrieved 2026-10-31. Page 3: features/options; page 5: variant ordering restrictions. |
| O3 | [LINAK DPG1C getting started](https://www.linak.com/work-res/start/dpg1c) | Manufacturer instructions/videos for favourites, reminders, pairing and operation. |
| O4 | [LINAK Desk Control App and FAQ](https://www.linak.co.uk/products/controls/desk-control-app/) | Manufacturer explanations of app settings, ownership, connection limits and statistics. App-version behavior must be checked separately. |
| O5 | [LINAK DPG family page](https://www.linak.com/products/controls/dpg-with-reminder) | Product family and current document-download entry point. |
| O6 | [DESKLINE product overview, Polish](https://cdn.linak.com/-/media/files/brochure-source/pl/lpl-deskline-product-overview.pdf) | Historically indexed official SDK overview. Direct retrieval failed in this review; do not treat it as a downloaded/current developer specification. |
| C1 | [linak_bt_desk command definitions](https://github.com/anetczuk/linak_bt_desk/blob/7ac5fe1b69638976326842b27d76e52f0cc958fd/linak_dpg_bt/command.py) | Pinned independent command catalogue/framing. |
| C2 | [LinakDeskApp settings UI](https://github.com/anetczuk/LinakDeskApp/blob/15d57d47327eeb72bacae6fc5a467b9e96ccaeea/src/linakdeskapp/gui/device_settings_widget.py) | Pinned independent settings candidates and write-then-read pattern. UI labels alone do not prove bit semantics. |
| C3 | [linak-controller GATT implementation](https://github.com/rhyst/linak-controller/blob/b46756231ed2ef5764c43bfc4c81f40b23cdc8ec/linak_controller/gatt.py) | Pinned independent transport/movement reference; see the [motion gate](movement.md). |

The downloaded O1 PDF has SHA-256 `7a58ee951c42d39817c2f623525b69d7cd834c19c84959d007623dea0afdcd9e`; O2 has `1b33c711169ff370057af4cc39759f202d9825e0cfba558efae54f400a1af53c`. Copies and a source manifest are retained in the local research workspace, not redistributed in this repository. Search snippets can still describe older 71/76-page editions; use the downloaded 35-page edition for O1 page references. Button symbols can disappear from PDF text extraction: consult the original visual instructions before giving an exact physical-button sequence.

## Manufacturer facts that affect design

O1 describes correcting displayed height without moving the desk, changing display units, upper/lower height limits, a configurable key lock, and different reminder presentations. Positions 3/4 can be disabled by OEM configuration from software 1.29. Its factory reset preserves configurator/OEM settings while clearing user changes. These functions' remote interfaces are not established here. O1 uses Desk Connect naming; older Desk Control material is not automatically a matching firmware/API specification.

O2 distinguishes Limited and Full product variants: Limited lacks app-driven motion and automatic drive; Full permits them. It lists display units including cm/mm/inch and separates optional functions from standard features. Record the exact product/firmware variant before enabling writes. A generic DPG1C model label or a capability bit does not independently establish writable support.

O3 documents four possible favourites, hold-to-drive operation, optional automatic travel with physical-panel stopping, three preset reminder intervals and an off state. Its advertised pairing procedure and visible panel indications describe user interaction, not proof of successful host bonding or GATT initialization.

O4 distinguishes Owner and Guest storage/transfer behavior, describes settings for favourites, height correction, light/app reminders and automatic drive, and limits the desk to one connected Bluetooth client. App statistics can accrue while connected without a person at the desk. These are reasons to investigate ownership and app conflicts, not to implement a guessed occupancy or lifetime-usage sensor.

## Capability and settings inventory

| Feature | Evidence | Intended HA surface | Current boundary / required proof |
| --- | --- | --- | --- |
| Actual height | H, O2 | Regular distance sensor in cm | Implemented. Verify against a physical measurement/panel after calibration. |
| Target height and Stop | O3, C3, S | Native number in cm and Stop button | Registered by default with a configured travel range; simulated HA coverage, physical movement/Stop evidence pending. |
| Drive to favourite 1–4 | O3, H, C1 | Buttons using the common motion path | Drive buttons re-read the selected slot; drive not physically verified. Respect configured/available slots. |
| Save/replace favourite | O4, C1 | Separate explicit save operation | Write payload, slot identity and persistence unverified; read back the exact slot. |
| Height offset/reference | O1, H, C1, P | Read-only diagnostic sensor plus protected calibration flow | Offset read works. Write, persistence and relationship to displayed calibration need verification. |
| Panel display units | O1, O2, C2 | Configuration choice if verified | Preserve the integration's centimeter interface; changing panel units must not reinterpret raw positions or cause motion. |
| Active reminder profile / off | O3, H, C2 | Configuration select after write validation | Profile read works; confirm the encoding/meaning of the off state before writing. |
| Sitting/standing duration per profile | O3/O4, H, C2 | Configuration values with validated ranges | Three profiles read; units, encoding limits and write persistence require validation. |
| Reminder light / presentation | O1, O3, C2 | Configuration control only for verified settings | A light capability is not its on/off state; distinguish panel light from HA/app notifications. |
| Automatic up/down / automatic drive | O2/O3, C2 | Explicit configuration opt-in if supported | Do not equate the firmware's favourite-drive feature with our host-driven target loop. |
| Wake behavior | C2 | Research candidate | Meaning and side effects not hardware-confirmed; no guessed switch. |
| Upper/lower firmware limits | O1 | Research candidate | Keep firmware limits distinct from integration command bounds; no known verified remote setter. |
| Key lock / lock timeout | O1/O2 | Research candidate | Read/write interface unverified; never assume remote movement is blocked by a physical key lock. |
| Reminder/memory/factory reset | O1/O3 | Outside initial controls | Destructive scope; do not add a casual reset button or use reset as routine recovery. |
| Name and connection identity | O4, S | HA device name, discovery label, reconfigure flow | GAP name reads exist in code; radio-name writing and app-name persistence are separate unverified functions. |
| Owner/Guest or user ID | O4, C1 | Research before application initialization | BLE pairing, app ownership and DPG user ID are separate layers. No automatic ownership/user-ID overwrite. |
| Error codes / display logo | O2 | Diagnostics/research where exposed | Display support does not prove a GATT error feed or writable logo. |
| Statistics / counters | O4, H | Preserve unknown raw fields in research | Do not label unexplained counters as occupancy, cycles, uptime or calories. |

The inventory's HA surfaces are project plans, not claims made by LINAK. Some firmware/OEM variants can permanently lack a listed function. Prefer a capability model and honest unavailable/unsupported states over dummy controls.

## Protocol notebook

Existing UUIDs and parsing are recorded in [protocol.md](protocol.md). The suffix for proprietary characteristics is `-338a-1024-8a49-009c0215f78a`.

| Item | Candidate / known representation | Evidence and limit |
| --- | --- | --- |
| DPG channel | `99fa0011` | H reads; serialize requests. |
| Height feedback | `99fa0021`, position and unclassified speed/flags | H reads; relative position units used by current decoder. |
| Capabilities | `0x80` | H read; capability flags are not settings acknowledgements. |
| Offset | `0x81` | H read; C1 names a setting candidate, but no validated setter here. |
| User ID | `0x86` | C1 only; ownership/persistence research required. |
| Reminder time | `0x87` | C1 candidate; distinct from the implemented `0x88` query. |
| Reminder settings | `0x88` | H read; C2 exposes light/wake/automatic-up/down/units/profile candidates. |
| Memory 1–4 | `0x89`–`0x8c` | H reads; C1 proposes get/set operations. |
| Product info / setup / log | `0x08`, `0x0a`, `0x90` | C1 catalogue only; its setup entry is marked nonworking. No runtime support inferred. |
| Read framing | `7f <command> 00` | H verified for the seven allowlisted queries. |
| Write framing | `7f <command> 80 <payload>` | C1 research candidate, not permission to construct arbitrary writes. |
| Movement | `99fa0002` control and `99fa0031` target | C3/S; physical behavior remains gated in movement.md. |

C2's settings UI writes and then reads reminder state. Preserve that verification principle, but do not copy every flag exposed there into HA. Our parser retains unknown flags/counters; setters must retain unrelated bits and validate payload lengths, response types and ordering. Memory responses lack a slot identifier, so ambiguous failures require discarding the session rather than advancing to another slot.

## Maintainer decisions: protected offset calibration

The latest owner decision supersedes a general proposal to expose offset as an editable configuration number. Offset stays a read-only diagnostic sensor; changing it belongs to a dedicated calibration step in post-install settings.

1. Read current panel data and present the current height/reference in cm.
2. Ask for a measured height with a clear description of what is being calibrated. Derive any raw reference value using verified semantics and encoding bounds; do not invent a generic safe range.
3. Show the old/proposed values and effects on displayed/stored-height conversions; require a separate final confirmation before sending a write.
4. Reject calibration while movement/Stop cleanup owns the session. Acquire the same exclusive operation ownership used by other commands.
5. Write only the verified setting, then read it back. Publish the actual result; a successful transmission is not confirmation.
6. Refresh offset, actual height, memories and validated command-bound conversions together. Calibration must not issue a move, wake request or replay a previous target.
7. If the result is uncertain, report it and read state again through a healthy session. Do not silently retry or blindly restore an old value that another controller might have changed.
8. On startup/reconnect, read panel state. Stored HA options must not cause automatic replay of a calibration write.

No offset-write service or unrestricted dashboard control is part of the initial design. The final implementation still depends on validating that the wire-level offset corresponds to the manufacturer's displayed-height correction on this firmware.

## Post-install settings and reconfiguration

Use native configuration entities for ordinary, verified panel settings. Use an Options Flow for integration behavior and the protected calibration workflow. Plan a Reconfigure flow for supported connection changes without making delete/re-add the usual UX; changing physical devices requires an explicit identity/unique-ID design.

Keep three layers distinct: physical/firmware travel limits, HA command bounds, and presentation/calibration settings. Changing an integration option must not claim to program firmware limits. Reload/unload resulting from configuration changes must settle Stop and release the transport safely; no queued move resumes afterward.

For each new setting record: source/revision, model/firmware and characteristics, read format, write format, permissions, bounds/units, preserved bits, acknowledgement/readback, persistence across reconnect/restart, interaction with physical controls/other apps, side effects, recovery and the HA UI contract. Use synthetic fixtures and English/Polish labels/errors. Keep device names/addresses/user IDs out of public evidence.

## SDK and manufacturer questions

No complete public DESKLINE GATT command contract or downloadable developer SDK was obtained in this review. The historically indexed O6 brochure advertises an SDK; its existence in marketing does not establish current access, supported firmware, licensing or open-source/PyPI redistribution rights. The newer publicly readable product documents provide behavior and variant constraints, not executable API permission.

Questions to retain for LINAK or the desk OEM: exact SKU/firmware and Full/Limited capability, SDK access/licensing, supported pairing/ownership initialization, offset and settings payloads/readback/persistence, variant/OEM restrictions, firmware-limit and key-lock APIs, Stop/connection-loss behavior, and permissible use/redistribution of protocol libraries. No inquiry has been sent.

## Delivery order

Native slider/Stop and favourite-drive entities support the first supervised HA tests. Record physical movement/Stop evidence before claiming hardware validation or recommending unattended use. Verify memory/offset/reminder writes separately while designing post-install configuration alongside the control work. This reference does not enable a runtime feature or authorize hardware writes. Keep detailed private progress and captures in the local handoff/research workspace.
