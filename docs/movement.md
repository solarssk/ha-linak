# Movement implementation and validation gate

## Status

Native HA controls are available as an experimental opt-in in 0.1.0a7: Target height (`number`, cm), Stop (`button`) and go-to-memory buttons. Existing installations remain read-only until Options Flow receives measured bounds and explicit confirmation. Saving options, setup and reconnect never issue movement/wakeup commands. No physical movement/Stop result is claimed yet.

The client holds exclusive ownership across preparation, fresh offset/memory queries, movement, position reads and final Stop. Polling returns existing state while a control operation owns the connection. Another target is rejected rather than queued. Stop bypasses the refresh lock, cancels a pending target and drains bounded cleanup. Interrupted/failed moves discard the connection and never resume after reconnection.

The [HA control test procedure](controls.md) covers activation and recording results without a separate computer. The [standalone research runner](movement-test.md) remains an alternative for protocol investigation; its 2 cm experiment limit is not the range of the native target entity.

## Native interface contract

| Control | Experimental behavior |
| --- | --- |
| Target height | Native number, centimeters, box input, measured travel limits; changing it explicitly starts a move |
| Stop | Native button, interrupts a pending movement; no automatic retry |
| Go to stored position 1–4 | Native buttons only for configured slots; use the latest panel value and the same movement path |
| Actual height | Existing sensor; independent of the target and updated from device feedback |

Entity names and exceptions must have English and Polish translations. Rejected commands raise an HA action error. A Stop failure must be visible; sending a BLE packet is not proof the desk physically stopped. No percentage cover, restore of a target on startup, automatic resume, or writing a new stored position is planned in this step. A physical panel change always remains observable.

## Protocol evidence

The research adapter uses characteristic `99fa0002-338a-1024-8a49-009c0215f78a` with wake `fe00` and Stop `ff00`. Targets are unsigned little-endian relative 0.1 mm positions on `99fa0031-338a-1024-8a49-009c0215f78a`. These are independently implemented in [rhyst/linak-controller](https://github.com/rhyst/linak-controller/blob/master/linak_controller/gatt.py) and its [movement loop](https://github.com/rhyst/linak-controller/blob/master/linak_controller/desk.py). This is community protocol evidence, not an official public LINAK specification. No code is copied from that project. Its initialization writes a user ID; this project deliberately does not do that without separately validating its meaning.

The prototype repeats targets every 200 ms, reads fresh position after each, and attempts Stop on success, error, timeout and cancellation. Individual I/O has a one-second deadline, no progress aborts after two seconds, and a movement has a thirty-second deadline. Reverse motion, overshoot and readings outside measured travel bounds abort. Position words are used for feedback without assuming the meaning of speed flags. These timings are research defaults, not device guarantees.

Centimeter conversion subtracts the explicitly supplied panel offset. Travel limits must be supplied from measurements, never guessed from four stored positions or from the protocol's 16-bit capacity. Non-finite heights and out-of-range targets are rejected before any write. Concurrent targets are rejected, not queued. No error reconnects and resumes movement. An I/O or total movement timeout permanently closes the controller, attempts Stop and then discards the transport, even if Stop succeeds. Disconnect failure does not make the controller reusable. A fresh, separately validated session is required. Stop failure also attempts disconnection.

Explicit Stop callers share a single shielded operation. Its reservation lasts until every Stop write completes, including after cancellation of a caller; a new movement is rejected during that interval. Only the movement caller clears the worker reservation. Loss of radio means delivery of Stop cannot be guaranteed.

## Supervised hardware sequence

Record results without device names, addresses or other private identifiers:

1. Verify panel offset, actual height and measured travel bounds against the desk.
2. Confirm characteristic properties and correct write mode on this DPG1C.
3. Test a short move up, a short move down, and physical height readback.
4. Test explicit Stop during movement and cancellation of the requesting action.
5. Check behavior when target packets cease and when the connection is lost.
6. Confirm whether wake and reference writes require a user-ID setting; do not silently change that setting to make a test pass.
7. Validate ownership with the polling client, HA shutdown/unload, disconnect, unavailable feedback and reconnection without resuming a target.
8. Test the native entities for their names, units, range, availability, exceptions and lifecycle on Raspberry Pi. In-process HA tests cover these contracts with simulated Bluetooth.

Native entities are included for explicitly supervised HA testing. Record these results before claiming hardware validation or recommending unattended automations. Writing memories, reminders, offset or unrelated panel bits needs its own evidence and readback verification.

Cancellation of `close()` waits for the reserved Stop operation to settle before disconnecting and then propagates cancellation. Repeated cancellation cannot bypass that wait; Stop keeps its existing I/O deadlines. Shielded task results are observed even when callers cancel, so a later Stop error is consumed while the controller remains closed.

Movement completion and close cancellation share the same shielded cleanup-draining path. Repeated cancellation of the movement caller cannot cancel its final Stop or release ownership before cleanup settles. A successful Stop propagates cancellation afterward; a Stop timeout still closes and discards the session.

Directional progress is measured against the best position reached toward the target. Retreat exceeding the tolerance from that position aborts, including several small backward steps. Only a new best position resets the no-progress deadline; returning to an earlier best or moving backward within tolerance does not count as progress. Small feedback reversals remain allowed when genuine forward progress continues.
