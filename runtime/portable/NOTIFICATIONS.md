# Portable notification relay

`notifications.c/.h` ports the queue, chunking, framing, lease and control logic
from `patches/ancs_relay.c` at G2 commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. Source pins are recorded
in `tests/g2_compat/upstream`; `tests/g2_compat/UPSTREAM.json` pins their hashes.
The host test source pin is
`8a0a8fcb276ce308ad907150ed83f43ab151466b47cda2f26b6a5acf64e91b5c`;
the relay source pin is
`23ef712b8095c9ca79759f2d4ba1cbaad2e06112ef3eba0df7cf3188f0bdc4ac`.

The production module has explicit per-instance state and platform callbacks.
It contains no G2 memory addresses, G2 context accessor, ANCC struct layout,
stock-call wrappers, global mutable state or firmware imports. It does not
subscribe to notifications, bypass an operating-system permission, or connect
a transport. Native MemoMind notification integration is not yet implemented.

## API and preserved behavior

Initialize fresh storage with `mm_notifications_init(context, platform)`.
The platform supplies allocator/free, monotonic millisecond clock, eligible
endpoint/side, timer lifecycle, synchronous-copy sender, action dispatch and
queue serialization. All callbacks are required; a platform that cannot perform
notification actions may supply an explicit no-op callback. Callback `side=1`
is the eligible endpoint policy inherited from G2's right lens, not a claim
about a MemoMind lens identifier.

- `control` accepts the original `AN`, version 1, operation 1–5 records.
  ENABLE/RENEW use the original 90,000 ms lease and fresh-ENABLE epoch.
  QUERY/ENABLE/DISABLE send the original status. ACTION validates its 9-byte
  minimum and action 0/1, then delegates connection/handle validation to the
  platform; it does not require an enabled relay, matching upstream.
- `source` accepts exactly eight notification-source bytes.
- `attribute` takes UID, attribute ID, immutable bytes and length up to 1024.
  A zero-length attribute still emits one record. No native struct is read.
- `app_response` takes at most 1024 accumulated ANCS response bytes, validates
  the complete bundle-ID/name record, and chunks its name. The bundle-ID maximum
  remains 64. Caller controls when accumulated responses are delivered; the core
  does not deduplicate a complete response supplied twice, matching upstream.
- Timer `tick` drains at most two current-epoch records, sends the unchanged
  G2 protobuf field-125 envelope, and schedules 20 ms or 100 ms pacing.
  A failed send consumes that record, increments a saturating error counter,
  and delays subsequent records; it does not replay the failed record.
- The internal 4096-byte queue, 150-byte payload maximum, full-record rejection,
  stale-epoch filtering and wrapping 16-bit counters are retained.
- `cleanup` disarms and stops/deletes the timer while retaining the ring.
  `destroy` frees the ring only after successful timer deletion. A deletion
  failure retains valid state for a later retry.

The additional portable boundary rejects invalid/null inputs, inputs overlapping
context/ring, and lengths outside each API's limit. Buffers must remain immutable
through the call. The allocator must return disjoint, aligned owned storage.
Init applies only to fresh storage; destroy a live instance before reinitializing.

## Scheduling and lifetime contract

The original volatile SPSC ring is serialized here through `queue_enter` and
`queue_leave` around each operation. These callbacks must serialize producers,
control and timer consumer for the same instance. A single-threaded event loop
can use no-op gates if it guarantees no reentrant calls. Two independent
contexts have no shared core state.

No platform callback may synchronously reenter this instance. `send` must copy
or consume its bytes before returning, and must run on a task where its blocking
behavior cannot prevent the queue gate owner from completing. Timers must be
asynchronous; start must not synchronously invoke the callback. Timer stop/delete
must not wait for another callback blocked on this gate. A native adapter must
prove these properties or marshal all operations onto a serialized worker.

For destruction the caller must detach notification producers and quiesce timer
callbacks first. A successful delete must guarantee no future callback; the
context itself remains caller-owned. Cleanup alone is not permission to free
storage. No native scheduler/concurrency proof is claimed by host tests.

## Original assertions and test adapter

Run:

```
python3 runtime/portable/tests/run_notification_tests.py --output NEW_DIRECTORY
```

The runner checks pinned upstream hashes, compares all original CHECK expressions
in order, requires the same nine scenario functions, builds with ASan/UBSan, and
writes an assertion mapping plus command/source/binary hashes. Production code is
included in the original white-box suite; separate public API tests link the
production translation unit normally.

The test-only shim decodes fake G2 ANCC structs into bounded core calls and
chains fake stock callbacks. The original `test_action` asserts G2 SRAM pointer
validation in this shim. Those assertions establish the preserved G2 adapter
policy and correct portable action dispatch; they do not establish MemoMind
ANCS handle addresses. Original scenario bodies and CHECK expressions remain
unchanged. Setup now initializes explicit contexts and frees prior allocations,
and CHECK instrumentation counts evaluations without changing predicates.

`analysis/portable-notification-tests-02/report.json` records all nine scenarios,
76 CHECK sites / 266 evaluations, plus public ownership/bounds tests, passing.
The latter include 6000 source records crossing the 16-bit ring index boundary,
two independent instances, maximum/empty attributes, app-name chunking, invalid
inputs/alias rejection, allocator/timer/send failures, saturation, clock wrap,
and retryable teardown failure. This is core compatibility evidence, not a
native notification integration pass.

## RV32 and memory

The same runner compiles production with pinned xPack RISC-V GCC 15.2.0,
`rv32imafc/ilp32f`, freestanding, strict warnings, and audits symbols/sections.
Current build: 2472 bytes text, no rodata, zero undefined symbols, zero writable
global bytes. Context is 272 bytes (including 52-byte platform callbacks), plus
a lazy 4096-byte ring: 4368 bytes before allocator and native timer/queue costs.
Maximum individual core stack frame is 128 bytes; this is not the complete
native callback/task stack bound.

## Pending native integration

MemoMind's ANCS discovery/subscription, native notification callbacks and
attribute lifetime/ordering have not been located or wired by this port. Its
connection/action API, queue/task serialization, allocator/timer adapter and
outbound app envelope must be established separately. G2's sid 0x09 protobuf
field 125 is preserved as a compatibility payload; it is not a MemoMind transport
channel. If notifications instead originate from a phone companion, that
companion must supply the same bounded records through an explicit authorized
transport adapter. These boundaries remain pending, not skipped tests counted
as passes. No device commands were performed for this implementation.
