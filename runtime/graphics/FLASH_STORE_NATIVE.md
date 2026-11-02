# Fixed native flash callback adapter

`flash_store_native.c/.h` binds the portable COW store's callbacks to the pinned
H001Y1.0.3.127 native interfaces. It is independent of scene integration and is
not linked merely by adding these files. No task, queue, allocator, singleton,
raw-XIP reader or physical-reservation mechanism is introduced.

## Initialization and caller obligations

```c
mm_flash_native native = {0};       /* stable, owned SRAM */
mm_flash_callbacks callbacks;
int rc = mm_flash_native_init(&native, acquired_real_tail_bitmap);
if (!rc) rc = mm_flash_native_callbacks(&native, &callbacks);
```

Both operations perform no native I/O. `init` requires a non-null32-byte acquired
and validated genuine bitmap slice for device1 physical `[0x700000,0x800000)`:
bytes64..95 of the original96-byte physical CUS8 map. A legitimate native
absence/effective-default decision must preserve its provenance outside this
adapter; init cannot distinguish acquired zero bytes from invented ones.
No implicit all-zero map is supplied. The map is copied before caller storage
can be released, and is not subsequently modified. Every sector bit is checked
before native I/O. Private spool/metadata ownership exclusions belong in the
portable cache's separate unavailable bitmap; never persist those as native
bad bits or pass them off as the acquired real map.

The context is300 bytes on RV32, including256 bytes of readback scratch. It must
be zeroed or previously initialized, aligned, stable and exclusively owned.
Init rejects map/context overlap before clearing the context, and rejects a
busy initialized context. All source/destination/callback spans must be valid
owned memory. Production admits only nonwrapping spans inside
`[0x02000000,0x02100000)` SRAM; this numerical check does not establish allocation
ownership. It rejects XIP/unified-flash pointers and context overlap, including
its readback scratch. Bind rejects an output callback table overlapping the
context. Reinitialization/map updates require the caller to quiesce all users;
there is no synchronization or teardown magic in this API.

One normal worker serializes every callback, map change and teardown. The busy
byte is a reentry guard, **not a thread-safe lock**. Call outside observers, ISR,
LVGL callbacks and caller-held critical sections; do not acquire the native
flash mutex around public wrappers. Source bytes remain stable and owned until
program plus cache maintenance plus readback comparison returns. The native
FIFO copy alone does not end this adapter's source lifetime.

Binding does not prove exclusive reservation. The parent must establish the
owner-disabled profile, full-region backup/preflight, real bitmap and runtime
owner lifecycle before mutation. The adapter uses only the1MiB tail of the
proposed exclusively reserved3MiB region. It does not claim ownership of either.

## Exact operations and failures

| Callback | Admission |
| --- | --- |
|read|1..256 bytes; wholly within one256-byte page|
|program|Exactly256 bytes; page aligned|
|erase|Exactly4096 bytes; sector aligned|

All operations force device1, stay entirely inside physical
`[0x00700000,0x00800000)`, and reject zero, overflow, misalignment, bad sectors,
null/invalid spans and aliases before native calls. No request supplies a device,
function pointer, cache index or CPU alias. The portable store handles its own
zero-length logical operations without invoking these callbacks.

- Read: `04329ad8(1, physical, owned_out, length)`. Its return bits are preserved
  as signed32-bit C status. A failed read can partially fill output: discard it.
- Program: `04329b1e(1, physical, stable_RAM_source, 256)`.
- Erase: `04329a14(1, physical, 4096)`.
- After **every admitted mutation**, including native failure, call
  `04324bea(0, 0x05000000 + physical, length)`. This is the additional device1
  XIP-alias maintenance used by stock CUS8. The public wrappers' own
  `physical+0x04000000` step is insufficient for the device1 alias.
- On mutation failure, preserve that status and stop; no automatic readback or
  retry masks it. On success, native copied readback verifies the whole page
  for program or all16 pages of an erased sector. Program compares every byte
  against its still-owned source; erase requires every byte to be`ff`.

A readback native error is preserved. A successful read with wrong bytes returns
`MM_FLASH_NATIVE_VERIFY`, distinct from native failure. Context diagnostic
`last_native_status` records the last native result and `phase` identifies
read/program/erase/readback; it is0 on a byte mismatch. Invalid admission leaves
previous diagnostics untouched. Negative adapter errors are listed in the
header; native codes are returned directly, so consumers must retain phase and
native status rather than assume every negative number came from the adapter.

The adapter performs no badmap save, no package-state callback, no retry and no
active-map publication. A failed mutation may have changed its target physical
sector; only the upper COW owner can decide whether that sector was unowned and
whether the old active logical mapping is still intact. A newly discovered
permanent fault needs a separate authoritative policy; this module does not
invent a persisted bad bit.

## Native evidence and limits

`analysis/ghidra/external-xip-review/report.md`, its raw store callback witnesses,
and `byte-witnesses.json` establish the physical/cache sequence for stock app
body SHA-256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
Device1 physical tail maps to CPU XIP`[0x05700000,0x05800000)`;
unified`[0x01700000,0x01800000)` is not a proven CPU-readable uncached alias.
No direct loads from either flash mapping occur in this adapter.

The public native wrappers own device locking, wait for flash completion and
may invoke stock callbacks. Their waits and cache-maintenance polling have no
cancellation deadline here and may assert or hang. Explicit readback proves
only the values returned under the mocked/live operation's ordering, not
universal stock-writer exclusion, same-chip read-while-write behavior, cross-core
coherence, power-loss durability or worst-case latency. Correct-alias maintenance
is performed exactly as witnessed; no new long critical section is added.

Measured adapter frames are48 bytes maximum (read32, init/bind0). The300-byte
context owns readback scratch instead of adding a256-byte stack array. Native
call frames, portable COW frames, task/RTOS/interrupt stack and real heap/queue
costs are additional. No native worker stack size is inferred from this audit.

## Required reproducible tests

From the repository root, choose a new output directory:

```sh
python3 runtime/graphics/tests/run_flash_store_native_tests.py --output analysis/native-flash-adapter-next
```

This required runner executes host ASan/UBSan with strict warnings, compiles the
production module with pinned xPack GCC15.2.0 RV32IMAFC/ilp32f, checks ELF/imports/
writable globals/stack/layout, then executes the actual production RV32 bytes
with Unicorn2.1.4. Output includes source/build/binary hashes, exact commands,
logs and failure reports. Existing output directories and Python`-O` are rejected.
No missing dependency becomes a skipped pass. The separate machine runner is:

```sh
.tools/rv32-tests-venv/bin/python tests/rv32/flash_store_native_emulator_test.py \
  --build analysis/native-flash-adapter-next --output /tmp/native-flash-machine-new
```

Host tests use a compile-time link seam for the four native APIs and host
addresses; that seam is absent from production RV32. Actual RV32 executes fixed
address call bindings and numeric SRAM checks. Only read/program/erase/cache
are mocked; native firmware bodies/controller/RTOS do not execute. Mocks verify
device, physical range, source/output ownership and exact maintenance/readback
order. Register checks cover callee-saved registers, gp/tp/sp. Target stores may
write only owned context/output/callback/stack memory; no writable globals exist.

The final validation covers78,655 host assertion evaluations, all256 sectors,
all4096 program pages, all256 bitmap bits,16 readback failure positions, status
and mismatch branches, no-I/O alias/init/range gates and reentry. Actual RV32
has1,877 named checks, all256 erase sectors and first/last page of each sector,
all256 bitmap bits, SRAM/XIP/overflow admission, native errors, cache ordering,
readback failures, register preservation and no-import/no-global audit. The
binary is1,298 bytes with SHA-256
`a2c79a2e62f4d997d69687488a51963ca94b29e53e3719bd79d3b55824042a4a`.
These are offline adapter results, not a claim of hardware writes or complete
flash-backed scene integration.
