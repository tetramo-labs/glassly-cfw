# Portable transactional flash store

This is an offline production core for a **256 KiB logical asset store backed by an exclusively reserved 1 MiB physical region**. It is not linked into the installed runtime. The portable scene backend now binds this core through `scene_flash_store.c`; native ownership, writer binding and device testing remain separate work. A live diagnostic acquired the native effective badmap as an absent-record zero default, preserving that provenance. Exclusive use of the full 3 MiB plugin region is now the platform direction; this core can occupy a 1 MiB subregion while ingress and other workspaces use the remainder.

The geometry is fixed: 64 logical sectors, 256 physical sectors, 4096 bytes per sector and 256 bytes per page. The caller supplies exactly 4096 bytes of scratch space and a small context (320 bytes on the measured RV32 build; 344 bytes on the host). The core has no allocation, imports, writable globals, timers, locks, native addresses or device identifiers. One serialized owner must perform every operation, including reads and views. Callbacks must be synchronous and must not reenter the store or mutate its context.

## API and lifecycle

`flash_store.h` exposes `mm_flash_store_init`, `begin`, `read`, `write`, `commit`, `abort` and `view`, all with the `mm_flash_store_` prefix. Return zero means success; the named negative errors distinguish arguments, geometry, state, range, I/O, poisoned transactions, insufficient space and forbidden aliasing.

1. `init(store, geometry, callbacks, unavailable, workspace, 4096)` copies configuration and the mandatory 32-byte unavailable-sector bitmap. Bit N excludes physical sector N relative to the supplied base. Init performs **no callback or flash mutation**, does not initialize scratch, and sets all logical bytes to zero without inspecting old physical contents. Successful reinitialization deliberately starts a fresh empty epoch, even if old maps existed; failed init leaves the old context unchanged. The geometry must exactly match the constants, the base must be sector aligned, and the exclusive physical end must fit in `uint32_t`.
2. `begin(store)` copies the active map to the staged map. Nested begin fails and poisons the transaction.
3. `read(store, offset, out, length)` reads staged data during a valid transaction and committed data otherwise. Staged bytes of the open sector (below) come from scratch without native reads. Unmapped sectors produce zeroes without native reads. Arbitrary logical offsets and lengths are accepted when their entire range fits. A zero-length read or write at the logical end is valid, including a null data pointer.
4. `write(store, offset, data, length)` requires an open, unpoisoned transaction. It supports a full 65,535-byte message effect and the entire 262,144-byte logical range. The transaction keeps one **open logical sector** in scratch: the first write to a sector reads its staged bytes into scratch, and later writes to the same sector change only scratch. A write that touches a different sector first writes the open one back: it is copied into a different physical sector, erased once and programmed in 16 page operations, and the staged map is published only after the complete sector succeeds. Previously staged sectors can be replaced repeatedly in the same transaction. No active sector is ever erased or programmed.
5. `commit(store)` writes the open sector back the same way, then copies the staged map into the active map. A write-back failure fails and poisons the commit with the active map unchanged. Commit does not erase old sectors; those become eligible for later reuse, always after a fresh erase. `abort(store)` drops the open sector and all staged changes, clears poison and performs no I/O.
6. `view(store, offset, max_length, &data, &length)` returns a borrowed **const scratch view**, ending at the next logical sector boundary or `max_length`. Inside a transaction a view of the open sector points into it directly, and a view of any other sector first writes the open sector back. The requested maximum range must fit and be nonzero. The view is valid only until the next store operation. It is neither an XIP pointer nor writable storage. Output metadata must not alias each other, the context or scratch.

All nonzero input/output spans must be valid caller-owned memory for the duration of the call; wraparound spans and overlap with the context or scratch are rejected. Buffers and callback configuration must remain stable while an operation runs. A borrowed view cannot be passed directly back to `write`; copy it into separate caller memory first.

After a transactional operation fails, reads, views, writes, begin and commit refuse further work with `MM_FLASH_POISONED`. `abort` is the recovery operation. An I/O failure outside a transaction returns `MM_FLASH_IO` without poisoning the store. Failed reads may have partially filled their destination, so callers must discard it. A view's I/O failure leaves its output pointer and length cleared; no output from any failed call may be used. No operation retries a failed callback.

The guarantee is **logical rollback within a live serialized epoch**, including partial native read, erase and program failures. Physical scratch sectors can change during a failed transaction. RAM mappings are not persisted and commit has no journal: there is no reboot or power-loss durability. A new init loses all logical contents by design. The map copy also assumes the stated serialization; interrupt/concurrent readers must not observe it in progress.

## Capacity and unavailable sectors

Init requires at least **129 usable physical sectors**. A fully committed store can occupy 64 sectors, a full replacement another 64, and one further sector is needed to replace an already-staged sector without overwriting it before success. This extra sector is exercised by the minimum-capacity test after all 64 staged sectors are occupied. At most 127 unavailable sectors are accepted. Thus the 256 KiB logical capacity does not include or hide transaction overhead inside the same 256 KiB physical allocation.

The allocator scans the fixed 256-sector region, excluding both maps and every supplied unavailable bit. It rotates its next-candidate hint for reuse; it is not a wear-leveling policy or wear-life guarantee. The read path also rejects flagged mapped sectors defensively before calling the reader. Failed unowned sectors are not automatically marked bad or retried; a later transaction can reuse them after another erase. Permanent native errors need a platform policy and an authoritative map update, not an invented persisted bad bit.

A future MemoMind binding must obtain the actual native bad-sector map and select the 256 corresponding bits for the independently reserved region. If acquisition, mapping, reservation or bounds cannot be established, **fail closed**. An erased managed-store directory is not evidence of an all-zero bad map. The stock 768-sector map and its genuine bad bits must remain intact; fake bad bits are not a reservation mechanism. If native badness changes during an epoch, the binding must stop/reinitialize safely or reject newly unavailable accesses before the hardware operation.

The 1 MiB region must also be excluded from every other native allocator, eraser and writer for the entire store lifetime. This core does not establish that reservation. The relevant ongoing native evidence is in `analysis/ghidra/native-store-capacity/report.md` and `analysis/ghidra/app-tail-store/report.md`.

## Native callback boundary

Callbacks receive physical byte offsets including `geometry.physical_base`, and an opaque caller context. Success is zero. The adapter is responsible for accurate success/failure results and for keeping all operations inside the genuinely reserved, currently usable region.

| Callback | Per-call bound |
| --- | --- |
| `read(user, offset, destination, length)` | 1–256 bytes; never crosses a 256-byte page |
| `erase(user, offset, length)` | Exactly 4096 bytes at a sector-aligned offset |
| `program(user, offset, source, length)` | Exactly 256 bytes at a page-aligned offset, once per page after successful erase |

Only the write-back of an open sector erases or programs: a transaction write that moves to another sector, commit, or a view of another sector inside a transaction. Init, begin and abort make no callbacks; reads never erase or program. Writes that stay in one sector cost one 16-page load and one write-back however many there are, so a message's per-line and per-chunk writes into one sector erase it once. A full replacement of an already mapped store performs 1024 bounded reads, 64 erases and 1024 programs. Callbacks may block according to their underlying driver; there is no native timeout, watchdog, throughput or 30 fps claim.

The measured RV32 core has 48-byte maximum individual frames. The write/read/view caller plus `read_map` can consume 96 bytes before entering a platform callback. Callback frames, lower native calls, interrupt context and the full task stack are excluded. The 4096-byte workspace is caller memory, not a stack allocation inside this core.

## Scene integration remains required

The existing scene store expects contiguous memory in several paths. It cannot safely receive this scratch view as a permanent asset pointer. Integration must replace those accesses with bounded read/view/write callbacks, make retained references logical offsets, and wrap each complete message effect in begin/commit with abort on every parse, bounds, allocation or I/O failure. Rendering must consume views before another store operation invalidates them. No current scene/profile/compiler/flasher source was changed by this implementation.

## Reproducible validation

Run from the repository root, using a new output directory:

```sh
python3 runtime/portable/tests/run_flash_store_tests.py --output analysis/flash-store/validation-next
```

The runner builds the actual core with host ASan/UBSan and `-Werror`, then compiles it freestanding for actual RV32IMAFC / ilp32f with the task-local pinned toolchain. It checks ELF architecture/endianness, no undefined imports, no writable global symbols/sections, bounded static frames, exact RV32 context layout and source hashes before/after the run. It saves the native object and disassembly; it does not execute that object on hardware.

`analysis/flash-store/validation-001/report.json` passed:

- 2,112 callback boundaries in a full replacement, each failed twice: once without effects and once after partial effects. All 4,224 runs refuse commit and preserve **every prior logical byte** after abort. This includes 2,048 read failures, 128 erase failures and 2,048 program failures.
- Full logical capacity, unaligned 65,535-byte writes, repeated staged-sector replacement, 300 committed reuse cycles, and 240 deterministic randomized multiwrite transactions checked against an independent RAM reference with both commits and aborts.
- Bad first/last/interior sectors, corrupted-map defensive read refusal, copied bitmap ownership, exactly 129 usable sectors under full replacement/churn, and rejection at 128 usable sectors.
- Init/read-only/no-op behavior, nested begin, integer/range/pointer overflow, invalid geometry, context/workspace aliases, borrowed-view invalidation and failure, and no callbacks after poison or during commit/abort.
- Instrumented callbacks assert every erase/program targets a sector outside both maps, every program sees erased bytes and no second program occurs on a page before its next erase.
- Revision 27's open-sector write-back (`test_open_sector_write_back`): line-sized writes into one sector make one load and no erase until a sector switch or commit; reads and views of the open sector touch no flash; the active map is unchanged through every write-back before commit; abort makes no callbacks; every failed erase/program of the commit write-back, a failed switch write-back and a failed load leave the committed bytes after abort. The 2,112 exhaustive boundaries now span the write and its commit. The reference model also checks random reads between writes.
- RV32: 1990 executable bytes, zero readonly data bytes, zero imports/writable globals, 320-byte context, 4096-byte workspace and 48-byte maximum individual stack frame. The host context is 344 bytes. The large reported assertion-evaluation count includes repeated byte/ownership checks; it is not a count of independent scenarios.

These are new portable backend tests, not a claim of additional upstream G2 test scenarios, native flash reservation, scene integration or hardware execution.
