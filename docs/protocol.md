# Protocol evidence

Research date: 2026-10-29. Manufacturer documentation describes capabilities, not a public BLE command contract. Device behavior can vary by firmware and OEM configuration.

## Verified on the user's DPG1C

- macOS CoreBluetooth can connect and discover services.
- Device Information reports manufacturer `LINAK A/S` and model family `DPG`.
- Services: `99fa0001`, `99fa0010`, `99fa0020`, `99fa0030` using UUID suffix `-338a-1024-8a49-009c0215f78a`.
- Height characteristic `99fa0021` returned `9e 05 00 00`.
- Direct read of `99fa0011` returned `ff`; this is not decoded extended configuration. Extended queries require notifications and query writes. These were subsequently tested successfully; see hardware-results.md.
- No movement commands or configuration changes have been sent.

The sample position word is 1438. With a hypothetical 0.6200 m datum it would yield 0.7638 m. A subsequent query returned an offset of 0.6800 m, making that original sample 0.8238 m under the community protocol interpretation. The physical panel display has not yet been compared.

## Research candidates

Community code frames extended read requests as `7f <command> 00` on `99fa0011`, with responses through notifications. All seven queries below returned matching response types and lengths on this device on 2026-10-29.

| Command | Candidate meaning |
| --- | --- |
| 80 | Capabilities |
| 81 | Height offset |
| 88 | Reminder settings |
| 89–8c | Stored positions 1–4 |

Do not treat a successful GATT write as a successful query. Correlate and validate each response; serialize requests and retain unknown bytes. Do not label unknown counters as lifetime usage or infer occupant presence from desk height.

## Sources

- Official DPG manual, 2026-04: https://cdn.linak.com/-/media/files/user-manual-source/en/deskline-dpg-desk-panels-and-desk-control-app-user-manual-eng.ashx
- Official SDK brochure: https://cdn.linak.com/-/media/files/brochure-source/pl/lpl-deskline-product-overview.pdf
- Extended query framing: https://github.com/anetczuk/linak_bt_desk/blob/master/linak_dpg_bt/command.py
- Mock responses: https://github.com/anetczuk/LinakDeskApp/blob/master/src/linakdeskmock/service/dpgservice.py
- Device settings: https://github.com/anetczuk/LinakDeskApp/blob/master/src/linakdeskapp/gui/device_settings_widget.py
- Basic movement: https://github.com/rhyst/linak-controller

Speed interpretation differs between community implementations. Preserve the raw word until direction, flags and units are verified against hardware.

No public downloadable DESKLINE SDK or complete public GATT specification was found. SDK availability and open-source redistribution terms remain unknown.

## Optional standard device metadata

Version 0.1.0a6 can read GAP Device Name (`00002a00-0000-1000-8000-00805f9b34fb`)
after pairing when the cached BLE name is only an address or generic fallback.
The service inventory must expose that characteristic as readable. It is a normal
GATT read, not an extended DPG command or a name/setting write. Missing or denied
metadata keeps the fallback. Name bytes are decoded as printable UTF-8 and kept
out of DeskState/downloaded diagnostics. Tests simulate this path; automatic
name repair on the owner's installation remains to be checked.
