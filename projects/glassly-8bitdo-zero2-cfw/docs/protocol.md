# Proposed Zero 2 button stream

The installed experimental firmware uses **version 4**, documented with its
verified physical mapping and explicit start/stop contract in
[buttons-probe.md](buttons-probe.md). All 12 buttons and A+B have delivered
notifications on hardware. The version-3 design below remains an unbound component.

This describes the compiled transport component, not an observed Zero 2 protocol.
No GATT service/characteristic UUID has been assigned to the custom firmware yet.
The Gamebrick's AE40/AE42 identifiers and Ananke's raw masks do not transfer to
this controller.

Each notification is eight bytes, fitting the default ATT MTU:

| Byte | Meaning |
| --- | --- |
| 0 | `47` (`G`) |
| 1 | `03` (distinct from Ananke's v2 raw format) |
| 2 | Sequence, modulo 256, increments only on accepted sends |
| 3 | Bit 0: lost queued transitions; bit 1: new-session baseline |
| 4–7 | Complete 32-bit button snapshot, little endian |

Zero means all buttons released. Bit-to-physical-button assignments are unresolved;
the component preserves all 32 bits. It does not synthesize repeat presses or gestures.
The stock GPIO-to-mask mapping is now documented in [the binding investigation](radio-binding.md);
it has not yet been connected to hardware. The stock input wrapper returns raw
samples; its delay/resample branch is bypassed in this build. Later report logic's
`0xffffffff` no-change sentinel must never be forwarded as a pressed-button mask.

The unbound `button_input` stage masks raw input to `0x3ff9` and qualifies each
button independently after 8 ms of unchanged observations. This proposed window
needs electrical validation. It starts released, so a held button qualifies
after the window; pulses shorter than the window are filtered. Its owner must
poll regularly (planned at most 1 ms apart), supply a monotonic millisecond clock,
and reset it when the clock restarts or sampling resumes after sleep. Clock wrap
is supported; a full skipped clock period requires reset. Sampling gaps cannot
reconstruct transitions that happened between observations.

A single input-task owner supplies debounced snapshots, including periodic polls
while the keys remain unchanged so blocked packets can retry. Connection handle
zero is valid. A separate `connected` flag and session epoch avoid treating handle
zero as disconnected or confusing a reused handle with an old session. Every
connection or subscription transition must advance the epoch.

The first subscribed poll queues a baseline with sequence zero. Reconnect and
unsubscribe discard pending states. Normal changes queue up to 16 complete
snapshots, preserving short press/release pairs through temporary backpressure.
When full, the queue discards stale history and replaces it with the newest state,
marked overflow. Subsequent changes queue normally. A failed send does not consume
the packet or advance the sequence. There is no periodic radio traffic when idle.

The binding's send function must copy data synchronously, verify the current
session/CCC, serialize submission with lifecycle changes, and wake the radio as
required. Queue acceptance is not proof of over-air delivery. These contracts are
tested against a host sink; the actual firmware implementation is still missing.
On this target, reserve a byte in the IPC ring and distinguish local insertion
from the radio's command acknowledgement. A transport adapter must retain the
pending packet until acceptance is established and invalidate it across epochs.

Glassly should derive edges only from ordinary consecutive packets. Baseline,
overflow and sequence gaps replace its current held state without inventing clicks;
cancel pending hold/tap recognition on resync or disconnect. The firmware sends
button state; gesture timing remains an app responsibility.

For iOS, the eventual native driver must use a discoverable vendor service,
notification subscription, `bluetooth-central`, and central state restoration.
Apple documents background wake for Bluetooth callbacks, subject to OS lifecycle
limits; this is not a guarantee of permanent execution or force-quit recovery.
See [Apple's Core Bluetooth background guide](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html).
No iPhone background behavior has been tested in this project.
