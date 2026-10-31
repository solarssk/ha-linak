# First setup and Bluetooth failures

## User flow

1. Put the panel into Bluetooth pairing mode and close other connected desk apps.
2. In Home Assistant, select the discovered custom LINAK integration (`ha_linak`),
   or select a desk through Add integration.
3. Submit the selection. The form immediately changes to Home Assistant's native
   progress screen while the integration connects, authenticates and reads the panel.
4. Successful validation releases the validation connection and creates the entry.
   A failed attempt shows a translated reason and a retry form, without creating
   an entry. Re-enable pairing before retrying if needed.
5. Home Assistant then starts the entry, opens the runtime connection and loads
   the sensors. A transient failure here enters HA's setup-retry state.

Discovery uses the native name and a short address suffix, matching the Idasen
presentation: `Office desk (EEFF)`. The flow checks current HA connectable metadata
and BLEDevice names as well as the original discovery snapshot. Generic `LINAK`
and address-only names do not hide a usable native name. Discovery does not
connect, request an active scan or read GATT solely to obtain a card title. If no
native name is cached yet, the card shows `LINAK (EEFF)`.

During the already-authorized connection, after pairing, a desk whose cached name
is still a fallback can supply its standard GAP Device Name characteristic
(0x2A00). The client reads it once per connection only if it exists and is readable.
Missing, denied or malformed names retain the fallback; transport loss and read
timeout still invalidate the session. This optional metadata phase is named
`device_name`, has the existing 10-second I/O limit inside the total 60-second
attempt, and sends no DPG settings writes. Raw names are never put in logs or the
diagnostic state object.

A new entry uses the resolved native name after validation. Existing address-only
entry titles are repaired as before. An older entry titled exactly `LINAK` retains
its title because its origin may be ambiguous, while its device-registry name is
improved when a native name is available. Other entry titles and HA's explicit
device name_by_user are preserved. Existing entity IDs and bonds are unchanged.

Discovery alone does not prove a usable GATT connection. The panel accepts one
connection at a time; the phone app or another desk integration may hold it.
Pairing/authentication on the local Bluetooth host can also be necessary. This
integration does not reset the panel or change a Bluetooth user-ID setting.

## Waiting and cancellation

A complete connection/read attempt has a 60-second budget. Explicit pairing has a 30-second limit within the same total budget. Each notification subscription
and the final position read have 10-second limits; each extended query has an
8-second limit. Failed sessions are invalidated and disconnected before retry.
Releasing a connection has a separate 10-second limit, so cleanup can extend a
failed attempt to approximately 70 seconds. Connection retries stay inside the
same total budget. The connector retains its own service-resolution timeouts;
these are not shortened below Home Assistant's recommended connection window.

The frontend does not keep a submitted form waiting for this work. HA owns a
single registered progress task. Revisiting the step does not create another
connection, and aborting the flow cancels validation and releases the session.
Instant failures still pass through progress before showing retry, preventing
form-submission data from being mistaken for a retry submission.

Both configuration and runtime use the current connectable BLE device from
Home Assistant's Bluetooth manager. A device callback lets the connector use
updated adapter/proxy information. Passive-only discovery is not accepted.

## Diagnosis

A failed validation writes a `ha_linak` warning containing a stage and error code:
`device_lookup`, `connection`, `pairing`, `device_name`, `notify_dpg`, `notify_height`, `extended_reads`, `position_read`, or `disconnect`.
Warnings for expected failures omit the desk name, Bluetooth address and raw
exception message. The UI distinguishes timeout, connection failure, unsupported
responses and unexpected errors. Unexpected errors retain a traceback for diagnosis.

When reporting a failure, include the HA Core version, local adapter or proxy,
setup stage, elapsed wait and relevant `ha_linak` log lines. Remove device names,
Bluetooth addresses and other private identifiers before posting.

## Evidence and limits

Tests run in real in-process HA with simulated Bluetooth. They cover manual and
Bluetooth-discovered setup, user confirmation, progress revisits, retry, abort,
updated device selection, phase timeouts and HA's initial setup-retry state.
Raspberry Pi 4 reads and reconnect after an HA Core restart were observed after
manual host pairing. The owner also confirmed working sensors after a full host
restart. Automatic first pairing in 0.1.0a4 is not yet hardware-validated.
See hardware-results.md for the distinction between these results.

The implementation follows HA's [config flow](https://contributors.home-assistant.io/core/integrations/config-flow/),
[progress steps](https://contributors.home-assistant.io/core/integrations/flow-steps/#show-progress)
and [Bluetooth integration guidance](https://contributors.home-assistant.io/core/integrations/bluetooth/).

See [Bluetooth research and diagnostic design](bluetooth-research.md) for the source comparison, known gaps and the next hardware experiment.

## Authentication sequence in 0.1.0a3

After GATT connection, the selected backend's pair method runs before either
subscription. Local BlueZ and compatible active proxies use explicit pairing;
CoreBluetooth performs authentication automatically and its unsupported explicit
pair method is not called. Pairing may establish or reuse a Bluetooth bond. It
does not write the DPG user-ID setting, reset the panel or send movement/wakeup
commands. Unsupported proxy pairing produces a specific error, not a silent bypass.
The bluetooth_adapters dependency lets HA initialize remote adapters before setup.

A link-loss callback cancels the currently owned pairing, subscription, query or
position operation. Setup reports connection_lost instead of waiting for its
operation timeout. External cancellation remains cancellation, and bounded cleanup
is drained even when the flow is cancelled repeatedly. No session is reused after
failure. Authentication failure, pairing_timeout and pairing_unsupported have
separate translated UI errors. The full-attempt budget can expire before a phase's
individual limit; its stage is retained in logs.

These paths were tested with simulated local/proxy/CoreBluetooth backends.
The local BlueZ first-pairing failure was subsequently traced to missing agent
confirmation; the follow-up below replaces that local pairing path. ESPHome
first pairing and long-term stability remain unverified.

## Local BlueZ pairing in 0.1.0a4

HA and bleak-retry-connector still choose and open the connection. For the public
`bluez_dbus` backend only, the integration resolves one connected BlueZ Device1
object matching the chosen address; it never assumes hci0. No match or multiple
connected matches fail rather than selecting an arbitrary adapter.

An existing Paired property skips pairing without resetting keys. Otherwise a
private system D-Bus connection exports a NoInputNoOutput Agent1 and calls both
RegisterAgent and Device1.Pair on that same connection. This matters because
BlueZ associates an application agent with the caller's bus identity. Registering
an agent on one connection and calling Bleak.pair() on another would still use
the host default. Only the selected device path is accepted; PIN/passkey entry
and service authorization are not provided.

The integration never requests default-agent status or replaces an existing
default. BlueZ itself makes the first registered agent a fallback if none exists;
during this bounded interval, requests for other devices are rejected. Closing
the private bus removes the agent on success, failure, timeout or cancellation.
BlueZ also cancels unfinished bonding when its requesting application exits.
No shell process, permanent agent, adapter scan-mode change, Trusted-property
change or DPG settings write is used. The pairing phase keeps its 30-second
limit inside the 60-second complete attempt.

ESPHome and other non-BlueZ backends continue through their own pair method;
CoreBluetooth remains OS-managed. A local agent preparation failure has the
translated error pairing_agent_unavailable; rejected Device1.Pair remains
authentication_failed. These messages omit raw D-Bus errors and identifiers.

Initial position notifications update internal state but do not publish an
unavailable coordinator update before the initial full read completes. Invalid
positions and disconnections after readiness still make sensors unavailable.

The automated tests simulate D-Bus and BLE. A fresh, unbonded Raspberry Pi
onboarding test is still required; the existing working bond must not be removed
without an agreed hardware-test scope. Connection deadlines are unchanged:
rare advertisements and intermittent disconnections need separate evidence.
