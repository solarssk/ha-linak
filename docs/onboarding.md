# First setup and Bluetooth failures

## User flow

1. Put the panel into Bluetooth pairing mode and close other connected desk apps.
2. In Home Assistant, select the discovered custom LINAK integration (`ha_linak`),
   or select a desk through Add integration.
3. Submit the selection. The form immediately changes to Home Assistant's native
   progress screen while the integration connects and reads the panel.
4. Successful validation releases the validation connection and creates the entry.
   A failed attempt shows a translated reason and a retry form, without creating
   an entry. Re-enable pairing before retrying if needed.
5. Home Assistant then starts the entry, opens the runtime connection and loads
   the sensors. A transient failure here enters HA's setup-retry state.

Discovery alone does not prove a usable GATT connection. The panel accepts one
connection at a time; the phone app or another desk integration may hold it.
Pairing/authentication on the local Bluetooth host can also be necessary. This
integration does not reset the panel or change a Bluetooth user-ID setting.

## Waiting and cancellation

A complete connection/read attempt has a 60-second budget. Notification setup
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
`device_lookup`, `connection`, `notifications`, `extended_reads`, `position_read`, or `disconnect`.
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
Real Raspberry Pi 4 Bluetooth onboarding has not yet been reproduced locally.
These changes fix known waiting/feedback weaknesses; they do not establish the
cause of a particular Raspberry Pi connection failure without its logs.

The implementation follows HA's [config flow](https://contributors.home-assistant.io/core/integrations/config-flow/),
[progress steps](https://contributors.home-assistant.io/core/integrations/flow-steps/#show-progress)
and [Bluetooth integration guidance](https://contributors.home-assistant.io/core/integrations/bluetooth/).
