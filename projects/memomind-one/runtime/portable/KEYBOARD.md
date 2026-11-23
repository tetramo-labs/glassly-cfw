# Portable keyboard core

`keyboard.c/.h` ports the keyboard state machine and relay from G2 commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. The source and license pins are in
`tests/g2_compat/UPSTREAM.json` and the verbatim files in its `upstream` directory.

| Upstream file | SHA-256 | Portable boundary |
| --- | --- | --- |
| `patches/keyboard_core.h` | `a706fabf96ea9db37db0b07de5015c1458f0774549efd1b1d1ced1d5da2a4a49` | State, control validation, queue, ownership/timeouts, event routing |
| `patches/keyboard.c` | `d8ad35c09b178ee5a38dec50d5bb7dc2a6fc757091e530ab6b6a234a40912c2f` | `kb_kick`, `kb_schedule`, `kb_tick`; native hooks excluded |
| `patches/host/keyboard_host_test.c` | `defe6b2fe82ddb3b510cfa8be16cfbb820917f337cc0238c8409c3d66a5972e3` | All six scenarios and 86 original assert expressions |

Production has no native G2 addresses, Cordio struct casts, custom-context global,
ARM instructions, allocator imports or mutable globals. The caller owns an
explicit context and supplies callbacks. A native MemoMind HOGP client is not yet
implemented. The file-level suite status is **mixed: portable core tested,
native adapter pending**; fake adapter assertions are not native parity passes.

## Portable API

`mm_keyboard_init(context, platform, timer)` initializes fresh caller-owned
storage. It does not allocate memory or create a timer. The platform provides a
clock, timer start, asynchronous poll posting, synchronous-copy sender, scan and
connection policy, connection open/close, pairing/authentication, ATT requests,
indication confirmation and security/DM callbacks. Every callback is mandatory.
A native adapter must map its connection handles to the preserved logical IDs
1–3 and return the documented KB error codes for resource/security failures.

The serialized BLE worker calls `mm_keyboard_control`, `mm_keyboard_poll`,
`mm_keyboard_handle_event` and `mm_keyboard_lost`. Only its timer consumer calls
`mm_keyboard_tick`. `lost` accounts for an owned event lost upstream of the relay
queue, consuming a sequence and increasing drops. It does not replace a native
allocation-failure hook or the native close-event fallback.

`mm_keyboard_event` is a portable input record, not a Cordio ABI struct. It uses
the preserved compatibility event numbers, connection ID, status and explicit
payload length. ATT and advertisement bytes are borrowed only during the call.
An authentication prompt is exactly two bytes. Numeric comparison is exactly
four little-endian bytes containing a value below 1,000,000. The test adapter
converts G2's 128-bit big-endian confirm value into this normalized value;
production never reads a raw native confirm-value layout. A MemoMind adapter
must map its native event meanings into these compatibility events explicitly.

The public boundary rejects malformed controls, wrong-sized/value prompts, and
context/input overlap before state mutations. Inputs must remain immutable and
readable for their declared lengths. An oversized or null ATT value retains the
original sequence/drop behavior; it is not read. Non-prompt DM payloads, including
bonding-key records, are never exported. Callbacks may need native event metadata
held privately by the adapter; the portable record does not carry native key
structures.

## Preserved semantics

The control grammar is the unchanged `KB`, version 1, 8-byte header plus bounded
operation body, at most 80 bytes. QUERY/ENABLE bypass epoch matching; other
commands preserve epoch checks, connection ownership, encryption requirements,
16 watched handles, one pending ATT request, and timeout behavior. Connection
ownership persists through timeout/disable until close arrives, isolating late
callbacks. There is no renewal lease: enabled keyboard input remains active.

Events retain 24-byte headers, 96-byte chunks, a 512-byte ATT value maximum and a
32-slot queue. Entire events are admitted or dropped, with sequence gaps and
heartbeat drop reporting. Queue indices wrap unsigned. Timers drain at most four
records and schedule every 20 ms while active or queued. Failed sends consume the
record and never replay stale typing. Failed timer starts and poll posts remain
retryable as upstream tests require.

The sender receives the original G2 protobuf field-131 envelope as a **compatibility
payload**. The test-only callback adapter asserts original sid 9/type 1 routing;
production does not open or select any native transport service. A MemoMind app
transport adapter must explicitly carry or translate this payload. Preserving
its bytes is not evidence that MemoMind accepts G2's wire protocol.

## Scheduling and lifecycle

There must be exactly one serialized producer and one timer consumer per context.
The queue indices, timer-armed flag, poll flag and published active snapshot use
32-bit acquire/release atomics. Timer code never mutates BLE connection state.
Platform callbacks must not synchronously reenter the same producer API; timer
start must schedule asynchronously. `post_poll` must queue work for the producer,
not run it recursively on the timer task. `send` must consume/copy bytes before
returning and run on a task where blocking will not deadlock the BLE worker.
The test's deterministic producer injection during drain exercises the original
wake-up race, but is not a scheduler/hardware concurrency proof.

No core teardown function guesses native disconnect or timer ownership. To
release a context, the adapter must stop accepting controls, disable/disconnect,
process close events, quiesce the producer, stop/delete the timer and guarantee no
queued polls or callbacks can reference it. Do not reinitialize or free a live
context. Native lifecycle and task stack verification remain pending.

## Original tests and additional coverage

Run:

```
python3 runtime/portable/tests/run_keyboard_tests.py --output NEW_DIRECTORY
```

The runner verifies upstream hashes, all 86 assert expressions in order, each
scenario's body (only context initialization may differ), and exactly one call
to every original scenario in `main`. It records and requires 966 actual assert
evaluations. Scenario functions are `isolation`, `commands`, `reports`, `prompts`,
`malformed`, and `timers`; the malformed fixture runs its original 20,000 trials.
The original test compiles actual portable production code, not the unchanged G2
reference. G2 event layout decoding and callback ABI remain test-only shims.

Separate public API tests link `keyboard.c` normally and cover independent
instances, invalid initialization, context/input aliases, normalized prompts and
advertisements, key-material non-export, null ATT drop accounting, sender failure
without replay, request allocation failure, timeout ownership and upstream loss.
Both binaries run under ASan/UBSan. Evidence:
`analysis/portable-keyboard-tests-02/report.json` and `assertion-map.json`.

The original ARM emulator's eight scenarios (`dormant`, `pairing_and_routing`,
`io_capability`, `att_requests`, `fragments_overflow_and_oom`,
`timeout_and_disable`, `scan_and_capacity`, `allocation_failure`) still depend on
G2 ARM hooks, donor layouts and import addresses. They are **platform-specific
pending**, not passed by the portable host suite or by compiling RV32 code.
Native HOGP discovery, bond storage/capacity, I/O capability policy, ATT buffer
allocation, DM/ATT allocation-failure fallback, adapter event decoding and actual
MemoMind controller behavior all remain pending. No device commands ran here.

## RV32 resource audit

Pinned xPack RISC-V GCC 15.2.0 compiles production for `rv32imafc/ilp32f` with
freestanding strict-warning settings. Current object is 3916 bytes of text,
no rodata, no undefined imports, and zero writable globals. Context is 4168 bytes,
including the 68-byte callback platform and queue; normalized event is 24 bytes,
queue record 121 bytes. There is no dynamic core allocation. Timer/worker/native
ATT allocations and stack are additional platform costs.

The largest individual core stack frame is 112 bytes. This does not include
nested core frames or native callbacks and is not a task-stack budget. Acquire/
release exchange uses the target's A extension; this build audit is not an
execution or memory-ordering test on the glasses.
