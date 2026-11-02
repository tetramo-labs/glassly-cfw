# Optional cooked input observer

Build with `scripts/compile_memomind_graphics.py --scene-session --input-observer NEW_DIRECTORY`.
The option leaves existing no-input builds byte-identical and does not change
the platform-table ABI. Probe command0x7e advertises
`inputObserver:{"command":124,"capacity":32,"leaseTicks":30000}` only in this profile.
The feature observes and preserves stock handling; it does not consume input,
enable sensors, change settings, or claim raw-HID subscriptions.

## Endpoint and messages

Service15 command0x7c carries exactly one BYTES TLV. The stock service dispatcher
at0x042e4680 treats0x7c as unsupported: its default releases the request and
returns status2. See [native dispatcher](../../analysis/ghidra/dispatch/function-042e4680.c).
The optional service gate replaces only that new command's route;0x7d/0x7e keep
graphics behavior. This is allocation within this pinned firmware's command
space, not a universal reservation for other firmware versions.

| Operation | Exact BYTES payload |
| --- | --- |
| Passive status | `[1,0]` |
| Subscribe/renew | `[1,1,mask,nonce:u32LE]` (7 bytes) |
| Poll/ACK | `[1,2,nonce:u32LE,ack:u32LE]` (10 bytes) |
| Stop | `[1,3,nonce:u32LE]` (6 bytes) |

Mask1 selects cooked buttons/navigation; mask2 selects cooked IMU gestures;
mask3 selects both. Nonce must be nonzero and fresh for each new subscription.
An existing session accepts only the same nonce and mask as a renewal. Other
nonces or masks return `session-conflict`; they never replace the owner.
Stopping or polling absent/expired state returns `no-session`. Status always
returns metadata with `records:[]` and never renews the lease.

The BT handler validates and copies a version2 job, releases original TLVs
before queueing, and frees its temporary job after the native queue copies it.
Only execution on the display worker emits a correlated completion on command
0x7c. Queue drop/timeout has no immediate success response. The existing graphics
display gate dispatches version2 to the input implementation; version1 remains
graphics. Original envelopes remain owned by the stock worker.

Success JSON always includes:

```json
{"glassly":"input","abi":1,"result":"ok","active":false,"nonce":0,"mask":0,"capacity":32,"leaseTicks":30000,"sequence":0,"ack":0,"drops":0,"exhausted":false,"records":[]}
```

Active replies report current session values. A poll returns up to8 oldest
retained records, each with unsigned `tick`, `sequence`, `id` and `class`.
Subscribe/status/stop return no records. Errors use `invalid`,
`session-conflict`, `no-session`, or `allocation-failed`; allocation/validation
failure JSON may omit metadata. If even native JSON creation fails, the existing
status4 fallback is used. A reply-allocation failure can occur after a successful
state transition; retrying the same subscribe identity preserves that state.

Polling discards records with sequence≤ACK, then returns the next page without
discarding it. Save the page durably before acknowledging its last sequence.
Repeated/stale ACK≤stored ACK is accepted idempotently; ACK beyond the last
generated sequence is invalid and does not renew. Acknowledging unseen records
explicitly discards them. Lost replies can be polled again with the prior ACK.
The32-record ring drops its oldest record on overflow and increments a saturating
drop count. Sequence starts at1, accepts UINT32_MAX once, then sets `exhausted`;
further eligible events only increment drops, never wrap sequence. Stop and use
a fresh nonce for a new session.

## Ownership and observation

An independent hidden LVGL image child stores the callback tag for finding the
owner on the current screen. It has **no image source, palette, or owned pixels**.
Creation immediately calls the proven native hide operation before yielding.
Hidden creation/hiding can still invalidate an area, adjust focus/layout, and
participate in normal child/ancestor deletion. It is not a no-op native object.

A20-tick timer removes the child after screen replacement or a30,000-tick lease
(stock ticks are1ms). DELETE owns timer and owner cleanup. Subscribe and valid
poll renew; status, invalid/conflicting requests and observation do not. Tick
subtraction handles a32-bit wrap under the30-second lease interval. A change of
stock app on the same screen does not terminate this passive session; there is
no launcher guard. The timer and explicit commands clean expired state; the
observer merely ignores it. Graphics and input owners use distinct DELETE tags.

Only zero-payload class2 identifiers1f7b..1f7f and1fb0..1fb9, and class3 IDs1..8
are copied. The observer allocates nothing, sends nothing, waits on no sensor,
does not delete, and never retains the envelope. It performs native screen/
child lookup and tick reads; child lookup is linear in the screen's children
and event records, not a proven constant CPU deadline. Cooked events can have
multiple physical sources and may subsequently be consumed by stock routing.
These records do not identify temple versus ring, raw reports, head-up settings,
or G2 wake-session semantics.

The actual gate saves caller integer/FPR/fcsr state in a144-byte aligned frame,
calls the observer and restores original arguments, return address and stack
before stock dispatch. Normal stock FP legality is supported by
[startup/task-context evidence](../../analysis/ghidra/input-adapter/fpu-context.md).
The stock context excerpts do not establish per-task fcsr isolation. Own state
is display-task serialized. A64KiB creation reserve and32KiB transient queue
reserve are policy snapshots, not atomic reservations or fragmentation/native
OOM guarantees. Native LVGL/JSON/event/timer allocation may still assert.

## Reproducible checks and candidate

* `runtime/graphics/tests/run_input_tests.py --output NEW_DIRECTORY` compiles
  actual input C and scene-enabled version2 integration under ASan/UBSan. It
  exhausts16,777,216 class/id pairs and all nonzero payload lengths, tests masks,
  copied request/queue ownership, ACK retention/repeated/stale/future ACK,
  overflow/exhaustion, nonce conflicts, lease wrap, screen/ancestor cleanup and
  creation failures. Each emitted JSON is checked by the production Python
  decoder, with protocol errors fatal. Sequence exhaustion uses explicit
  internal test injection, without a production mutation endpoint.
* `tests/rv32/input_gate_emulator_test.py --build BUILD --report REPORT` runs
  7,955 actual RV32 gate/callsite cases with mocked C boundaries, including
  hostile caller integer/FPR/fcsr clobber and stock continuation preservation.
* `tests/rv32/input_runtime_emulator_test.py --build BUILD --report REPORT` pins
  input-004 and executes actual linked C/native wrappers. Six groups and1,710
  calls cover native hide/send, ACK/ring semantics, cleanup, graphics coexistence,
  native failure contracts, and4-mod-8 owned allocations. External firmware
  functions remain synthetic mocks. Measured stack is464 B BT and800 B display
  for these cases, excluding native helper frames, interrupts and the separately
  measured observer gate frame. This is not a whole-task worst-case proof.

Final candidate build `runtime/build/input-004` is49,248 bytes, SHA256
`3f8e637dff1f9da760b8842d1041eb88579cabc1b864bb5605d21bb9205167b4`.
The separate `captures/firmware/input-observer-001` candidate contains the
constructed OTA, runtime blob, exact manifest and verification report. See
`analysis/input-gate/` for host, gate and actual-runtime evidence. Compilation,
host tests and mocked-native execution do not establish physical input or native
OOM behavior. These offline runners do not operate a device.

## Hardware validation

The parent installed input-004 through the independent OTA driver. All3,796
chunks across543 blocks and the18-byte header reconstruct the complete2,221,167B
candidate with SHA256
`bbc777895ef3c56af8ff3b5cbac85c8e7acb429eadfdc194cd407f5255c12f85`.
The device acknowledged reboot and advertised the new input capability.

Live status/subscribe, conflicting nonce rejection, future-ACK rejection,
scene reset/put/show/state/clear coexistence, explicit stop and abandoned-session
lease checks passed. Stock capabilities and heartbeat remained unchanged. Free
bytes were333,912 before,333,900 after stop, and333,932 after the lease interval
before querying input status. These observations are not a direct heap-object
or worst-case allocation proof.

The Python logger completed180 seconds of polling with0 observed events and0
reported drops. No user action confirmation was received during that window;
physical input semantics and stock forwarding under real input remain unverified.
Two separate RFCOMM connection failures occurred before any business-frame write;
fresh connections succeeded and no OTA/mutating command was retried. The prior
one-microsecond HCI timestamp reversal remains in the historical prefix, with
no truncated records. General traffic losslessness is still unproven.

Evidence: `analysis/input-hardware-verification.json`,
`analysis/protocol/input-runtime/whole-image-proof.json`, and
`captures/input-runtime-20261031/`. The32-file capture manifest was verified after
graceful collector shutdown and restoration of the official app.
