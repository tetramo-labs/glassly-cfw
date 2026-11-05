# Experimental button streaming image

**Flashed and fully read back on 2026-11-05.** Runtime USB boot and the first
valid eight-byte baseline (`4704000200000000`) are observed over BLE with USB
connected. The first hold lasted 187.590 seconds; reconnect produced another
sequence-zero baseline. Both A1 and A0 were acknowledged in each session.
A later live test verified all 12 physical press/release pairs and an A+B chord
with 27 consecutive packets, no sequence gaps and no overflow flags. Evidence:
`evidence/buttons-probe-mapping.json`.
The installed notification/idle image passed a 188.448-second battery hold
without keepalive writes and four echo notifications after reconnect. This next
image adds actual GPIO snapshots. It is a separate compact assembly implementation;
`button_stream.arm.o` and `button_input.arm.o` remain unbound.

## Wire contract and lifecycle

Retain stock FF10 service / FF13 write-and-notify characteristic and dynamic
handle at `0x20648`. The host subscribes, waits for subscription completion, then
writes the single byte **A1** with response. This resets the stream and requests
a baseline. The host writes **A0** and waits for its response before unsubscribing.
A new connection resets stream state before the original connection helper;
disconnected sampling also resets it. Other values, wrong handles and wrong
lengths do not change stream state. A1 is a new-session command, not a keepalive. Stop/reset invalidates local queued
and in-flight state; it cannot recall a notification already queued by the radio.

The explicit host protocol supplies subscription intent. It does not discover
the radio's internal CCC callback. Unsubscribing without A0 violates this contract;
the radio still owns actual CCC enforcement, whose ordering remains unproven.
Do not claim automatic firmware CCC tracking. The diagnostic always disconnects
after its bounded capture, and sends A0 before intentional disconnect when possible.

Each FF13 notification is eight bytes:

| Bytes | Meaning |
| --- | --- |
| 0–1 | `47 04`: experimental stream version 4 |
| 2 | Sequence modulo 256; advanced after zero-status command-09 acknowledgement |
| 3 | Bit 0: queued transitions lost; bit 1: new-session baseline |
| 4–7 | Full stock button mask, little endian; valid bits `0x3ff9` |

The user-confirmed ordered tap test established these stock masks on the tested
YC3121 unit (no mapping imported from another controller):

| Button | Mask | Button | Mask |
| --- | --- | --- | --- |
| A | `0x2000` | B | `0x1000` |
| X | `0x0010` | Y | `0x0020` |
| Up | `0x0200` | Down | `0x0100` |
| Left | `0x0080` | Right | `0x0040` |
| L | `0x0400` | R | `0x0800` |
| Select | `0x0008` | Start | `0x0001` |

Baseline, overflow or a sequence gap
replaces held state without synthesizing press/release edges. Ordinary consecutive
snapshots yield pressed/released masks. The host decoder tests those rules and
sequence wrap, rejects malformed packets and requires an initial baseline.

## Sampling and queue

Replace the complete BL at `0x0101be28`, the timer's call to the OEM report task,
with a wrapper that calls the actual raw reader `0x0101f64c` **before** all OEM
report congestion/mode gates, then calls the original task with its original
argument and returns its result. Keep the OEM input/remapping/report code intact.
The timer remains the stock one, with nominal startup tick 10 ms and dynamic
rearming; no 1 ms polling or exact wall-clock interval is claimed.

A changed whole mask qualifies when observed on two consecutive polls. This
is a sample-based experimental filter, distinct from the unbound per-button
8 ms component. A held key qualifies after two polls; an initially released
baseline can be sent immediately. Bounce on one key can delay the whole mask.
No changes between polls can be reconstructed. Sixteen qualified snapshots are
queued. Overflow discards queued history, retains the newest snapshot and marks
resynchronization. It does not overwrite the separate in-flight record.

Submission serializes the awake check, capacity check, stale-bit clear and stock
synchronous IPC copy under saved/restored PRIMASK. Require capacity **greater
than 13** (header 3 + dynamic handle 2 + packet 8), retaining one byte to avoid
exact-fill ambiguity. Skip sleeping radio instead of entering stock wake/delay.
Move the queue head into an in-flight record; submit no further packet until
stock acknowledgement bit 6 is observed. The retained four-byte record stores
sequence/flags/16-bit mask; the remaining packet bytes are constant. An ACK is
radio command acceptance, not proof of host receipt. Nonzero/missing ACK stalls
sending while sampling continues and can overflow the queue. There is no guessed
retry timeout. Restart with A1 or reconnect to establish a new baseline.

Radio error/FIFO behavior, late completion across session cancellation and CCC
ordering still require live characterization. No final reliable-delivery claim
is made. The first full button-stream hardware experiment now delivers actual transitions.

## Owned state, placement and stack

The first OEM static pool uses three 600-byte BSS blocks beginning at `0x22064`.
Change its count instruction at `0x01023bba` from 3 to 2. The actual initializer
then links only `0x22064` and `0x222bc`, leaving **`[0x22514,0x2276c)`** out of the
free list. Stream state uses the first 48 bytes:

| Offset | Storage |
| --- | --- |
| 0, 2 | Candidate/stable mask, two bytes each |
| 4–7 | Head, count, sequence, pending flags |
| 8–11 | Enabled, in-flight, initialized, padding |
| 12–43 | Sixteen two-byte queued masks |
| 44–47 | In-flight sequence/flags/mask |

Startup already zeroes this BSS. No copy table or SP changes. The pool initializer
leaves all 600 reserved bytes untouched in emulation; other seven pools retain
their exact lists. A scan of all four-byte windows finds no stock pointer into
the reserved block and only one pool-base literal, used by this initializer.
This ownership evidence does not exclude arbitrary computed ROM/DMA accesses.
The tradeoff is **two OEM blocks rather than three**, requiring live coexistence
checks; it is not previously unused RAM.

All 364 bytes of added code/literals fit in the same audited stock-cleared
508-byte tail used by the notification probe. Both package headers, GD32 section,
Yichip extent and startup reconstruction are unchanged. No code executes from
RAM. Static branch and pointer checks plus actual startup execution retain the
placement limits documented in `notification-probe.md`. Original nonzero device
tail backups remain local.

The polling wrapper reserves 48 stack bytes, control/connect/idle wrappers eight.
The maximum observed test stack is 892 bytes, with OEM input/report generation
and connect power side effects stubbed. Main's known 24 bytes, actual report-task
callees and interrupts are additional; this is not a whole-device worst-case
bound. State is about 55 KiB below the initial SP; no new SP is configured.

## Reproducible validation

`python3 tools/build_buttons_probe.py` builds and independently decrypts the
package. `.venv/bin/python tools/inspect_buttons_probe.py` checks:

- Actual startup reconstruction and no tail data reads.
- Reduced first pool list and all seven untouched lists.
- All 4,096 GPIO combinations, two-sample qualification and baseline bytes.
- 2,048 ring-cursor/IRQ cases, exact-fill rejection, wrap and asleep deferral.
- 12,000 polls against an independent queue model, including 164 overflows and
  1,371 sends; pending ACKs, sequence wrap and packet contents are checked.
- Real software event dequeue/control matching, reconnect reset, disconnect
  reset, idle/watchdog guards, original task argument/result and saved registers.

Only OEM report generation and connection power/indicator side effects are
stubbed. GPIO, custom code, event dequeue, timers and IPC execute real Thumb.
MMIO and radio ACKs are synthetic; no radio or interrupt execution is modeled.
`python3 scripts/check.py` passes 29 Python tests, native sanitized suites,
Swift receiver compilation and packet decoder self-tests.

Exact hashes and audit metadata: `evidence/buttons-probe.json` and
`evidence/buttons-probe-emulation.json`. The native flasher admits this exact pair
and the previous four known images/baselines, preserving backups and requiring
full readback before version commit/reset.

For another live capture, run `scripts/ble_probe.py buttons --identifier <observed UUID>
--seconds 180` while pressing/releasing buttons. Baseline reception alone is not
a button-transition test. Keep raw captures local and report hardware results
separately from these offline checks.

Battery validation at 21:48 UTC: USB registry was empty. A fresh session received
a baseline plus A press/release, remained connected for **187.951 seconds** with
no keepalive writes, and acknowledged A0 before intentional disconnect. Idle time
after the release was **166.260 seconds**. Evidence: `evidence/buttons-probe-battery.json`.
This does not establish long-term power consumption or iPhone background behavior.
