# Storage diagnostic implementation review

Reviewed `runtime/graphics/storage_diag.{c,h}`, `storage_diag_native.c`, the
`MM_STORAGE_DIAGNOSTICS` branch in `flash_read.c`, and
`scripts/memomind_storage_diag.py` against
`analysis/ghidra/flash-topology/diagnostics.md` and
`analysis/ghidra/badmap-acquisition-review/report.md`.

No blocking ABI, request-ownership, malformed-input or disclosure mismatch was
found in this optional fixed diagnostic. This is a source/emulation review;
no device action or storage mutation was performed.

## Fixed interfaces and ownership

The one-byte opcodes 2 and 3 admit no key, address, length, command or pointer
parameter. Other lengths/opcodes take the invalid path before diagnostic reads
or allocation. The normal request adapter and fixed service/command dispatch
are retained. The handler copies its selector, releases the borrowed request,
checks free-memory headroom, then allocates a 1024-byte owned workspace. Its
116-byte record lies in that workspace; actual length is a separate aligned
32-bit local. Native calls retain neither borrowed request nor output pointers.
JSON construction copies the owned record before the workspace is freed once.
Allocation failure and malformed inputs execute no diagnostic helper.

The badmap ABI is precisely `04235032(0x6009, owned, 116, &actual)` once.
`042a9c84(record)` checks CRC32 over 112 bytes and `042a9cca(record+16)` validates
the full 96-byte physical bitmap. Success additionally requires length 116,
magic `474d4231`, version 1, physical base `01500000`, and size `00300000`.
No logical reservation capacity is substituted for physical identity. The
getter runs in the existing ordinary BT service task, without a custom critical
section, display lock, recursive KV lock, initializer or saver. The real native
getter can wait/assert in its RTOS mutex path; host deadlines do not cancel it.

Status 7 is explicitly `absent`, with a cleared effective default map and no
stored record. Status 0 plus failed identity/length/integrity is `invalid`.
Other statuses remain `unavailable`. Only a validated present record emits
record bytes; invalid/unavailable never emit partial buffers. The host validates
these envelopes, fixed fields/types, CRC and identity again and retains the
absence distinction. `tail_unavailable_map()` intentionally returns the effective
32-byte tail map for both present and absent; callers must retain `recordState`
and must not treat that return value alone as proof that a stored record was
acquired. A valid error-state diagnostic remains telemetry, not authorization
for a subsequent storage mutation.

## Passive topology and disclosure

The native snapshot reads only the 21 reviewed RAM slots plus one initialized
reserved local. It never dereferences the CUS8 context, mutex or function-table
pointers. Driver/table pointers become bounded enums/booleans; UID-derived low
bits of the probe word are omitted and only the high 16-bit legacy ID is exposed
when the device-specific probe and driver match. No general RAM view or bus
transaction is introduced. Two scalar samples detect changes but cannot prove
atomicity or exclude ABA changes. `consistent=0` remains visible to the host;
the validator does not promote it into a successful storage preflight.

One documentation nit: the leading comment in `storage_diag_native.c` says
"No native function ... is invoked". That is true of the snapshot function but
not the file's three badmap veneers. Scope that comment to the snapshot when
next editing the parent-owned source; the executable behavior is as intended.

## Bounds, stack and headroom

The bounded serializer reserves its terminator, emits no output on overflow,
and has 768 JSON bytes in the owned workspace. Native unsigned values and
fixed field names cannot introduce arbitrary strings. The handler requires
34816 reported free bytes for a diagnostic, then uses the existing checked
try-allocator. This is a point-in-time headroom check, not a largest-block or
concurrency guarantee; later stock response allocation retains its documented
OOM/assert risk.

`runtime/build/storage-diag-001/*.su` reports handler 96 bytes, badmap serializer
80, topology serializer 224 and field helper 16; native diagnostic veneers and
snapshot use zero-frame tail calls/direct loads. The observed native getter
chain is 128 bytes with RTOS mocks. Thus the badmap getter branch accounts for
304 bytes (96+80+128), and the topology field path for 336 (96+224+16), before
parent task frames, native response construction, real RTOS frames and
interrupts. These are constituent path sums, not measured worst-case task
bounds. The owned record avoids the native loader's additional local-record
frame. The separate 43-case loader harness observes 272 bytes for its deepest
native path and must not be mistaken for the complete diagnostic stack.

## Verification

Reviewed runtime sources exactly match the input hashes in the emulated
`runtime/build/storage-diag-001/build.json`, blob SHA-256
`265f8837b2b939930434253f7be63a1155190fef701c57d8c123d482a66725eb`.

- ASan/UBSan serializer suite passed: 65536 UID exclusions, 22 changed snapshot
  fields, both 768-capacity sweeps, 116 record corruptions, all 768 bitmap bits,
  119 wrong lengths, absence/errors and normalized pointers.
- Eight Python client tests passed, including profile/type/envelope/CRC checks,
  correlation, failure poisoning and no automatic retry.
- Actual diagnostic RV32 suite passed 11 test groups / 170 handler calls,
  including request release before native getter, fixed-slot reads only,
  malformed TLVs, failure/OOM branches and no invalid-byte emission.
- Promoted native KV/badmap suite passed all 43 preserved cases with exact
  frozen results and original predicate/harness integrity checks.

Artifacts: `/tmp/memomind-storage-diag-review-host-01/report.json`,
`/tmp/memomind-storage-diag-review-rv32-01.json`, and
`/tmp/memomind-badmap-promotion-01/report.json`. The diagnostic RV32 suite mocks
native KV/CRC/bitmap calls; the separate 43-case suite executes those native
paths with synthetic KV pages. Neither proves real topology, physical mutex
behavior, simultaneous writers or interrupt-inclusive stack limits.
