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

The hardware results in this document were obtained with the first revision
(package `a64e0b6e…`, plaintext `bcb8f2e9…`). The current build adds a steady
connected LED while a BLE host is connected (see below). **That revision has not
been flashed or observed on hardware**; its evidence is offline only.

## Connected LED indication (built 2026-11-12, not flashed)

Reported on hardware with the first revision: while the Glassly App is connected
the LED keeps blinking. Stock stops blinking once a host connects.

**Stock mechanism (static).** The LED driver `0x010232bc(mask, value)` drives
mask bit 0 → GPIO0.3, bit 1 → GPIO0.2, bit 2 → GPIO2.3 through the SDK's
`GPIO_SetBits` `0x0101bd48` / `GPIO_ResetBits` `0x0101bc7c` (named by their
`yc_gpio.c` asserts). Which of the three is populated on the Zero 2 PCB is not
established; with the default `0x20158 = 0` the emulated indications use GPIO2.3.
A timer (`0x2204c`, callback `0x010248e0`) calls the tick pointer `0x206b8`, set
to `0x01024585` by the engine start `0x010247c4`, which also sets the reselect
flag `0x206b0`. The tick `0x01024584` reruns the pattern selector `0x010242f0`
when that flag is set, at the end of each blink cycle, or when its snapshot
changes: HID state `0x20182` (`0x206d9`), `0x20181` (`0x206de`), the pairing
predicate `0x0101f080` (`0x206da`), and `0x206b1`/`0x206b3`/`0x206b2`.
The selector tests, in order:

1. `0x0101f080()` at `0x01024304`, bit 6 of `0x201dc`: the pairing pattern, a
   continuous fast blink; it also rewrites idle threshold `0x20194 = 6000`.
2. `0x20182 == 2` at `0x01024354`: the connected branch — no blink, solid mask
   2 or 4 (by `0x20158`); mask 1 if `0x206b1 && !0x206b2`; a slow blink if `0x206b3`.
3. Otherwise the reconnect pattern: 2–10 toggles chosen by mode `0x201b4`, then
   a 101-tick pause.

Bit 6 of `0x201dc` is the pairing flag: holding a mask of `0x0008` (Select in the
tested mapping) past a timed count at `0x0101dc66`, while HID is not connected,
stores `0x12345678` at `0x2fff0` and restarts; at boot `0x01024d0c(1)` sees that marker
(`0x0101a910`) and calls `0x0101b5d8`, which stores `0x201dc = 0x40`, copies six
zero bytes to `0x20179` and requests radio visibility through `0x0101a304`. That is the documented
Glassly pairing step. Stock HID connect, dispatcher case `0xb7`, stores HID state
2 **and clears `0x201dc`**; `0xb0` stores 2 and calls `Handle_HidConnectStateCallback`
`0x0101c900`. Other writers of `0x20182` (literal scan): `0xb6` (3), `0x0101ac7c`
(1), `0x01022af0` (3), `0x01022ba8` (0), vendor commands `0x01022d82` (0) /
`0x01022dae` (2). The BLE events do not write `0x20182` or `0x201dc`. Event `0x02`
stores 2 in BLE state `0x20682` and calls `0x0101c874(2)`, which only reaches the
idle-threshold setter, `0x01020350` (an empty `bx lr` in this build, despite the
"power/indicator" name used elsewhere) and a timer removal. No LED code reads
`0x20682`; stock never makes BLE visible, so its LED logic only knows HID. A
missing CCC or encryption event is therefore not the cause: no BLE event feeds
the LED, and in pairing mode the flag would win even if HID state were set.

**Emulated root cause.** On the stock Yichip section, in reconnect mode and
after the real pairing entry `0x0101b5d8`, the real dispatcher handles event
`0x02` (BLE state 2); the next 400 LED ticks keep blinking (6 and 39 changes).
Dispatching case `0xb7` instead gives a solid output from the next tick.

**Patch.** Four replacements inside the LED engine, three short tail routines
(`.Lled_pairing`/`.Lled_snapshot` share one body), no new RAM and no GPIO writes
of their own:

| Offset | Stock | Replacement |
| --- | --- | --- |
| `0xc304` | `bl 0x0101f080` (`faf7bcfe`) | 0 while BLE state is 2, else the stock predicate |
| `0xc354` | `ldr r0,=0x20182; ldrb r0,[r0]` (`86480078`) | 2 while BLE state is 2, else HID state |
| `0xc5ee` | `bl 0x0101f080` (`faf747fd`) | snapshot: 2 while BLE state is 2, else the stock predicate |
| `0xc62e` | `bl 0x0101f080` (`faf727fd`) | same snapshot routine |

While BLE state is 2 the selector therefore sees what stock HID connect leaves
(HID 2, pairing flag clear) and takes the stock connected branch, including its
low-battery and `0x206b1` variants; the flag itself is not modified. The snapshot
value changes on connect and disconnect, so the pattern is reselected on the next
tick; after disconnect (BLE state 3) the stock selector resumes the pairing or
reconnect pattern. Snapshot byte `0x206da` now holds 0–2; only the LED tick reads
or writes it. While linked the pairing branch no longer rewrites threshold 6000,
as after stock HID connect; the idle wrapper already clears the counter then.
Not changed: transient LED animations keyed to HID state (button-combination
confirmation `0x010247e8`, shutdown sequences), the pairing flag and HID state,
which also gate OEM reports, idle and watchdog behavior.

**Offline validation** (`tools/inspect_buttons_probe.py`, LED section; dispatcher,
connect helper, pairing entry and LED engine run unstubbed except the pairing
entry's command-02 submission, which waits for a radio acknowledgement):

- In reconnect and pairing modes, patched event `0x02` gives the stock `0xb7`
  output from the first tick; A1/A0 writes leave it unchanged; event `0x05`
  reproduces the stock blink sequence exactly; a second connect is solid again.
- 9,216 selector states: with BLE state 2 the patched output equals stock with
  HID 2 and the pairing flag clear, otherwise it equals stock; 2,382 states change,
  all with BLE state 2.
- 6,000 lock-step ticks with random inputs against stock: identical LED output and
  RAM writes; with a BLE link only snapshot bytes `0x206d9`/`0x206da` differ.
- Observed LED tick stack is 40 bytes on both; the shared routine adds 8 bytes
  on a path that is not the deepest.

| Artifact | Bytes | SHA256 |
| --- | --- | --- |
| `build/buttons-probe/Zero2-v1.08-buttons-probe.dat` | 124,472 | `007ca4b94e765ba20bfeb7aaaf7728c14a741b6bac821d74932084b8536334a8` |
| `build/buttons-probe/yichip.bin` (plaintext) | 73,216 | `9c93ce2bbf3bba0a4e41e7505e65b4c0deeedb082668ad384e8653aad3333528` |

Against the first revision, only the 16 bytes of the four LED hooks change
outside the tail. Evidence: `evidence/buttons-probe-led.json` and
`evidence/buttons-probe-led-emulation.json`. **Unverified on hardware:** that the
LED actually turns steady with the Glassly App connected (from pairing and from
reconnect), that it resumes the stock pattern after disconnect, which pin/colour
is lit, the battery cost of a steady LED, and charging/low-battery indications
on a real controller.

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

All 408 bytes of added code/literals (364 in the first revision) fit in the
same audited stock-cleared 508-byte tail used by the notification probe; the
builder rejects anything larger. Both package headers, GD32 section,
Yichip extent and startup reconstruction are unchanged. No code executes from
RAM. Static branch and pointer checks plus actual startup execution retain the
placement limits documented in `notification-probe.md`. Original nonzero device
tail backups remain local.

The polling wrapper reserves 48 stack bytes, control/connect/idle wrappers and
the shared LED pairing/snapshot routine eight; the LED link test uses none.
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
- The connected LED checks listed above, against the unmodified stock section.

Only OEM report generation and connection power/indicator side effects are
stubbed; the LED checks run that helper unstubbed and skip only the pairing
entry's command-02 submission. GPIO, custom code, event dequeue, timers and IPC
execute real Thumb. MMIO and radio ACKs are synthetic; no radio or interrupt
execution is modeled.
`python3 scripts/check.py` passes 29 Python tests, native sanitized suites,
Swift receiver compilation and packet decoder self-tests.

Exact hashes and audit metadata: `evidence/buttons-probe-led.json` and
`evidence/buttons-probe-led-emulation.json` (current build), and
`evidence/buttons-probe.json` / `evidence/buttons-probe-emulation.json` (flashed
first revision). The native flasher admits the current pair, the first-revision
pair and the four earlier known images; both buttons revisions are accepted as
installed baselines. It preserves backups and requires full readback before
version commit/reset.

For another live capture, run `scripts/ble_probe.py buttons --identifier <observed UUID>
--seconds 180` while pressing/releasing buttons. Baseline reception alone is not
a button-transition test. Keep raw captures local and report hardware results
separately from these offline checks.

Battery validation at 21:48 UTC: USB registry was empty. A fresh session received
a baseline plus A press/release, remained connected for **187.951 seconds** with
no keepalive writes, and acknowledged A0 before intentional disconnect. Idle time
after the release was **166.260 seconds**. Evidence: `evidence/buttons-probe-battery.json`.
This does not establish long-term power consumption or iPhone background behavior.
