# Notification and connected-idle experiment

Hardware result: flashed/read back successfully on 2026-11-05; all four one-byte
echoes arrived as matching FF13 notifications with USB connected. See
`evidence/notification-probe-flash.json` and `evidence/notification-probe-gatt.json`.
Battery idle policy without host writes remains to be tested.

This complete experimental image builds on the successfully flashed BLE visibility
probe. It is not the queued/debounced button stream. It answers two hardware
questions: does radio command `09`, with the dynamically registered FF13 handle
followed by one byte, produce a notification; and does firmware-side idle/watchdog
maintenance keep a BLE connection alive without host keepalives?

## Changes and behavior

- The complete BL instruction at `0x01019918` is replaced with a call to
  `0x01029c04`. The stock dispatcher has already copied the event and compared
  its handle with the registration result at `0x20648`. Its watchdog cancellation
  call remains unchanged. The new routine first performs the original idle reset,
  then only echoes events containing exactly a two-byte handle and one value byte.
- The complete BL at `0x0101be36` is redirected to `0x01029cc0`. When BLE state
  `0x20682` equals 2, it clears idle and cancels the watchdog. Otherwise it calls
  the original idle increment. This is an explicit experimental policy for **any
  BLE connection**, even without a subscription. It does not claim CCC ownership.
- Both old call targets remain intact. Hook sizes and returns are unchanged;
  no input-reader or GPIO mapping changes, persistent RAM, startup scatter changes,
  unbound stream/input objects, or GD32 modifications are included.

The echo descriptor and three-byte payload live in a 48-byte local stack frame.
It preserves r4–r7 and LR. It saves PRIMASK, masks CPU interrupts, checks the
radio-sleep flag, then checks capacity and synchronously submits. Capacity must
exceed six bytes (header plus payload), retaining a spare byte against the known
exact-fill ambiguity. Any nonzero sleep flag causes a drop, avoiding the stock
wake/delay path inside the critical section. PRIMASK is restored on both paths.
There is no retry, wait for command acknowledgement, queue or delivery claim.
The radio consumer may free space while interrupts are masked; this is not a
lock against the radio processor. Local producers cannot preempt through ordinary
maskable interrupts during check/copy. Interrupt nesting is not emulated.

## Placement decision for this probe

The 220-byte tail interval is `[0x01029c04, 0x01029ce0)`, inside the existing
73,216-byte section and unchanged flash extent. It was zero in the pinned OEM
image and in complete readbacks following both official stock and our probe
flashes. The original device's nonzero tail remains preserved in its earlier
backups. This does not establish its original purpose; the flasher rejects
unknown baselines before erasing. This experiment deliberately reuses only the
now-known, stock-cleared tail, not original unknown device data.

The compressed initializer ends before this interval. The zero initializer's
scatter source points to its start, but the pinned routine at `0x01023342`
overwrites r0 with zero and uses only destination r1 and length r2. Executing
actual startup with the patched tail produces exactly the stock RAM and makes
no data reads from the tail. A conservative halfword-position scan across the
pre-radio code region finds no direct branch candidate into the stock tail;
an aligned pointer scan finds only that scatter source. These checks cannot
exclude arbitrary computed references or undocumented ROM/bootloader behavior.
Tail execution therefore remains an experimental hardware question, not a
general declaration that this memory is free for production components.

The idle wrapper has an 8-byte local frame. Full event dispatch plus echo and
actual FIFO/IPC callees uses at most 904 bytes of stack in the synthetic cases;
adding the known 24-byte main frame gives 928 before exception/caller effects.
This is an observed isolated bound, not a proof of whole-firmware worst-case
stack usage. No persistent state is reserved in the unproven RAM interval.

## Offline checks and hardware procedure

`tools/inspect_notify_probe.py` executes actual patched startup, event dequeue,
dispatch, capacity check, ring copy, timer cancellation and idle routines with
no instruction stubs. Synthetic NVIC and radio pages are ordinary RAM. Cases
cover all 1,024 ring cursor pairs with each initial interrupt-mask state, wrap,
exact-fill rejection, malformed/nonmatching requests, sleeping-radio skips,
several dynamic handles and the host's four echo values. It verifies packet
bytes/cursors, IRQ restoration, stock idle-reset behavior and watchdog state.
It neither runs radio ROM nor simulates CCC handling or on-air delivery.

```
python3 tools/build_notify_probe.py
.venv/bin/python tools/inspect_notify_probe.py
python3 scripts/check.py
python3 scripts/flash.py notify-probe --location 0x02100000 --apply
python3 scripts/ble_probe.py echo --identifier OBSERVED_UUID --seconds 30
python3 scripts/ble_probe.py subscribe --identifier OBSERVED_UUID --seconds 180
```

The host echo mode waits for both a successful write acknowledgement and the
matching one-byte notification before issuing the next request. Values are
`31`, `a5`, `00`, `ff`; no byte is labeled as a physical button. The following
subscribe-only run checks idle handling without any vendor value writes. Battery
testing still requires USB unplugged; reconnect/subscription cycling and sleep
must be reported separately. If no notification arrives, retain the exact image
and transaction data and investigate; do not describe local ring insertion as
successful radio delivery.
