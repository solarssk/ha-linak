# Movement implementation and validation gate

## Status

`motion.py` is a tested research foundation, not an enabled feature. No runtime
module imports it, no action or entity invokes it, and configuration does not offer
an override. Installing this revision through HACS remains read-only. Simulated
BLE tests do not establish physical Stop behavior or motion support on DPG1C.

The next PR may connect native entities only after supervised hardware tests.
Never put this controller on the read client's connection while its refresh task
is running: the future integration must hold exclusive session ownership across
movement, readback and final Stop. Stop must bypass polling and queued commands.

## Native interface contract

| Control | Behavior after validation |
| --- | --- |
| Target height | Native number, centimeters, box input, measured travel limits; changing it explicitly starts a move |
| Stop | Native button, interrupts a pending movement; no automatic retry |
| Go to stored position 1–4 | Native buttons only for configured slots; use the latest panel value and the same movement path |
| Actual height | Existing sensor; independent of the target and updated from device feedback |

Entity names and exceptions must have English and Polish translations. Rejected
commands raise an HA action error. A Stop failure must be visible; sending a BLE
packet is not proof the desk physically stopped. No percentage cover, restore of
a target on startup, automatic resume, or writing a new stored position is planned
in this step. A physical panel change always remains observable.

## Protocol evidence

The research adapter uses characteristic `99fa0002-338a-1024-8a49-009c0215f78a`
with wake `fe00` and Stop `ff00`. Targets are unsigned little-endian relative
0.1 mm positions on `99fa0031-338a-1024-8a49-009c0215f78a`.
These are independently implemented in
[rhyst/linak-controller](https://github.com/rhyst/linak-controller/blob/master/linak_controller/gatt.py)
and its [movement loop](https://github.com/rhyst/linak-controller/blob/master/linak_controller/desk.py).
This is community protocol evidence, not an official public LINAK specification.
No code is copied from that project. Its initialization writes a user ID; this
project deliberately does not do that without separately validating its meaning.

The prototype repeats targets every 200 ms, reads fresh position after each,
and attempts Stop on success, error, timeout and cancellation. Individual I/O has
a one-second deadline, no progress aborts after two seconds, and a movement has
a thirty-second deadline. Reverse motion, overshoot and readings outside measured
travel bounds abort. Position words are used for feedback without assuming the
meaning of speed flags. These timings are research defaults, not device guarantees.

Centimeter conversion subtracts the explicitly supplied panel offset. Travel limits
must be supplied from measurements, never guessed from four stored positions or
from the protocol's 16-bit capacity. Non-finite heights and out-of-range targets
are rejected before any write. Concurrent targets are rejected, not queued.
No error reconnects and resumes movement. Stop failure attempts disconnection.
Loss of radio means delivery of Stop cannot be guaranteed.

## Supervised hardware sequence

Record results without device names, addresses or other private identifiers:

1. Verify panel offset, actual height and measured travel bounds against the desk.
2. Confirm characteristic properties and correct write mode on this DPG1C.
3. Test a short move up, a short move down, and physical height readback.
4. Test explicit Stop during movement and cancellation of the requesting action.
5. Check behavior when target packets cease and when the connection is lost.
6. Confirm whether wake and reference writes require a user-ID setting; do not
   silently change that setting to make a test pass.
7. Validate ownership with the polling client, HA shutdown/unload, disconnect,
   unavailable feedback and reconnection without resuming a target.
8. Add native entities and run real HA tests for their names, units, range,
   availability, exceptions and lifecycle. Then validate on Raspberry Pi.

Only after these results are recorded may movement controls be enabled in a
mergeable PR. Writing memories, reminders, offset or unrelated panel bits needs
its own evidence and readback verification.
