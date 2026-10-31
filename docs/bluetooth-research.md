# DPG1C Bluetooth research and diagnostic design

Reviewed: 2026-10-30. This is an evidence review and implementation plan, not a claim that Raspberry Pi onboarding is fixed. Upstream branch links are mutable; the Idasen helper comparison below uses its 3.0.1 tag.

## Initial failure report (before the agent diagnosis)

User-supplied Raspberry Pi traces show connection through local BlueZ, successful return from DPG notification setup, then a pending height subscription. The transport disconnects about 2–3 seconds later; the integration eventually reports its 10-second notification deadline. The same sequence occurs with the user reporting only the Pi adapter enabled. Do not infer that multiple adapters caused the failure. Do not publish the private traces, device address or advertised desk name.

A separate Idasen attempt failed during connection, including an ESPHome backend attempt. That is a different failure phase, not proof that Idasen reached and failed the same height operation. The trace does not contain the controller's HCI disconnect reason, an ATT authentication error, or proof of successful bonding.

## Keep these layers separate

| Layer | Evidence of success | What it does not establish |
| --- | --- | --- |
| Discovery | Advertisement received by HA | Connection or authentication |
| GATT connection | Connector returns a connected client and resolved services | Bonding or working notifications |
| BLE pairing/bonding | Backend authentication completes | DPG application initialization |
| Notification subscription | start_notify returns for the specific characteristic | A valid position or extended response |
| Extended read | Matching, validated response to one serialized query | Support for other commands or firmware variants |
| Ready | Valid height, offset and required alpha readings | Movement safety or successful reconnect |

A panel display message is not a machine-readable confirmation of all these stages.

## Source comparison

### Manufacturer

The [LINAK DPG product page](https://www.linak.com/products/controls/dpg-with-reminder) and linked [35-page user manual](https://assets.linak.com/asset/590184044899/document_hub5bdnb5l13pc4ebsja0cc702?content-disposition=inline) describe Bluetooth pairing mode, memories and reminders. They document pressing the Bluetooth button for two seconds and the blue flashing indication. They do not provide the complete GATT authentication/initialization contract needed here. A complete public command specification was not found in these documents; this is not a claim that no manufacturer SDK exists.

### Native Home Assistant Idasen

The inspected HA manifest pins idasen-ha 3.0.1. Its [tagged connection manager](https://github.com/abmantis/idasen-ha/blob/3.0.1/idasen_ha/connection_manager.py) cleans stale connections, establishes a client, then explicitly pairs, performs wakeup and invokes the connected callback. Pairing and wakeup have separate 45-second budgets; AuthenticationFailed is classified separately. Its overall policy should not be copied as an unbounded retry loop into config flow.

The [underlying idasen implementation](https://github.com/newAM/idasen/blob/master/idasen/__init__.py) delegates pair to Bleak. Its DPG1C wakeup reads command 0x86, writes a user-ID payload through 99fa0011 and sends the control wakeup command. This writes application state; it is not merely BLE pairing. Its monitor subscribes to 99fa0021. Branch content may differ from the exact dependency version installed on a particular HA host.

### Other community implementations

[rhyst/linak-controller](https://github.com/rhyst/linak-controller) separates characteristic/service transport from desk operations. Its [GATT code](https://github.com/rhyst/linak-controller/blob/master/linak_controller/gatt.py) identifies 99fa0011 as the DPG command channel, 99fa0021 as height/speed and 99fa0031 as target input. Extended queries subscribe to DPG responses and unsubscribe after a response. Its [desk initialization](https://github.com/rhyst/linak-controller/blob/master/linak_controller/desk.py) checks capabilities and user ID, conditionally changing the latter. This differs from our two persistent subscriptions before reads.

The original [DPG1C discussion #32](https://github.com/rhyst/linak-controller/issues/32) contains user-ID initialization reports. The opening symptom was readable height but failed movement, not our subscription disconnect. Treat this as a candidate initialization requirement, not proof of our root cause.

[Laeborg/hass-linak-dpg](https://github.com/Laeborg/hass-linak-dpg) uses bluetoothctl. It is historical protocol context rather than a suitable transport architecture for today's HA adapter/proxy manager. [LinakDeskApp](https://github.com/anetczuk/LinakDeskApp) explicitly reports testing with a DPG1C and supplies useful mock/extended-command references already linked in protocol.md. These projects are independent implementations, not manufacturer specifications.

## Architecture decisions

Follow [HA Bluetooth guidance](https://contributors.home-assistant.io/core/integrations/bluetooth/): HA owns scanning and adapter selection; use connectable BLEDevice objects, fresh clients and bleak-retry-connector. Add bluetooth_adapters as the startup dependency when implementing the handshake change so remote adapters are available before connection. Do not pin a user's installation to hci0 or shell out to bluetoothctl as the normal transport.

[Deprecation-free Bleak APIs](https://bleak.readthedocs.io/en/latest/api/client.html) distinguish pairing from connection. macOS can initiate authentication automatically for protected characteristics; that successful test does not validate Linux bonding behavior. The missing explicit authentication phase in 0.1.0a2 is a plausible gap. The later Pi investigation below identifies the missing BlueZ confirmation agent. Proxy pairing behavior must be checked separately against the HA-pinned backend.

Keep protocol decoding, transport lifecycle and HA entities separate. Preserve centimeters and the panel's offset rather than Idasen's fixed minimum-height assumption. Never publish stale data as current after a lost session. Serialize DPG queries: memory responses do not contain a slot identifier, so a timed-out session must be discarded.

Do not automatically copy user-ID writes, reset bonds, clear caches globally, enable automatic drive, move the desk, or fall back to made-up offset values. Optional feature discovery and partial availability need an explicit capability model before relaxing the alpha's strict full-read requirement.

## Diagnostic contract

Current changes split notify_dpg and notify_height and log stage transitions, elapsed seconds and unexpected link loss without names or addresses. Config-entry diagnostics expose the current stage. This is instrumentation, not a handshake fix.

The next implementation should record a bounded per-attempt history: attempt number, operation, elapsed time, backend category, result and sanitized error code. Distinguish connection timeout, authentication failure, unsupported pairing, missing characteristic, rejected subscription, link loss and malformed response. Preserve the failed operation through cleanup. Race pending I/O against a session disconnect signal so known link loss does not become a misleading timeout; cancellation must drain owned tasks and release the transport.

Diagnostics must not dump BLEDevice.details, raw exception messages, advertised names, MACs, location names or DPG user IDs. Use an allowlist and privacy tests. A backend disconnect callback does not automatically expose the radio-level reason: report unknown unless an actual HCI reason is available.

[HA diagnostics](https://contributors.home-assistant.io/core/integrations/diagnostics/) are useful after an entry exists. Failed onboarding has no config entry, so it also needs self-contained sanitized stage logs and a clear UI error. Do not promise a diagnostics download on a setup that never created an entry. Upstream Bleak/connector debug logs can contain identifiers even when our own logs do not.

## Ordered validation plan

1. Verify the exact HA, OS, integration and Bluetooth backend versions; retain a private service/characteristic-properties inventory. No repeated blind pairing attempts.
2. Implement bounded explicit authentication, backend compatibility and distinct errors. Validate missing/protected characteristics before subscribing. No DPG settings writes in this experiment.
3. Test one session on the Pi: authentication, height read/subscription, then serialized DPG reads. Compare against the current sequence. If it disconnects, obtain a private host Bluetooth trace with the actual disconnect reason; Core logs alone cannot supply it.
4. If authentication succeeds but application initialization remains necessary, test user-ID read and separately assess any write with a documented restore/ownership policy. Do not infer permission to change settings from support for a read command.
5. Test Pi only, proxy only, then mixed adapters; also abort, retry, phone contention, reconnect after panel/HA restart and unavailable adapters. Single-adapter mode is diagnostic isolation, not a product requirement.
6. Publish the read-only fix after simulated failure tests, required local checks, Linux HA/HACS CI and a successful Pi test. Keep supervised movement validation separate.

Required regression cases include disconnect during each subscription, authentication timeout/rejection, late notifications from discarded clients, repeated cancellation, updated adapter selection, missing properties and private-error redaction. Simulated tests establish software behavior, not hardware compatibility.

## Implemented follow-up (0.1.0a3)

The client now explicitly pairs before subscribing, except on the public
CoreBluetooth backend IDs where authentication is OS-managed. Pairing is bounded
and failures are classified. HA's bluetooth_adapters dependency replaces the
Bluetooth-only startup dependency. Pending I/O is cancelled on the current
transport's disconnect callback; caller cancellation and transport cleanup remain
separate. Simulated tests cover the changes. This implements the software part of
step 2 above, without GATT-property preflight or application settings writes;
hardware validation and any manufacturer-specific initialization remain open.

The [ESPHome backend pair implementation](https://github.com/bluetooth-devices/bleak-esphome/blob/main/src/bleak_esphome/backend/client.py)
checks proxy pairing support and can raise NotImplementedError. That receives a
specific setup error; the integration does not disable adapter routing globally.

## BlueZ agent follow-up (2026-10-31)

Private HCI and host-log diagnostics identified a local pairing exchange rejected
because BlueZ had no confirmation agent. Manual NoInputNoOutput pairing then
allowed read-only HA operation. This establishes a local authentication problem;
it does not explain every earlier proxy disconnection. See the sanitized outcome
in [hardware results](hardware-results.md).

The implementation in 0.1.0a4 follows the public BlueZ
[AgentManager API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.AgentManager.rst)
and [Agent API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Agent.rst).
The [agent implementation](https://github.com/bluez/bluez/blob/master/src/agent.c)
selects an agent by caller identity, makes the first registered agent a default
fallback, and removes agents on caller disconnect. The
[device implementation](https://github.com/bluez/bluez/blob/master/src/device.c)
selects that caller's agent for Pair and watches for requester exit to cancel
unfinished bonding. Both registration and Pair therefore use the same short-lived
bus. The agent rejects any other device path and does not call RequestDefaultAgent.

This solution uses public D-Bus objects rather than private Bleak client fields.
The dependency is HA-owned dbus-fast (tested at 5.0.22); no independent override of
HA's pin is introduced. Physical testing of this automatic path is pending.
