# Exclusive device1 CUS8 replacement: independent native review

**No blocking contradiction was found for the offline six-entry owner-gate candidate.** The gates cover the recognized ordinary owners of device1 physical `[00500000,00800000)` in the pinned app. Mount refusal propagates as an error rather than success with a null context. Separate resource and recording writers remain below this interval on the recovered ordinary caller paths. This is bounded static coverage, **not proof of exclusive physical ownership or hardware admission**.

Reviewed stock app: H001Y 1.0.3.127, body SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`. This review reuses frozen evidence and adds only read-only/noanalysis caller exports in this new directory. No production/test files, earlier evidence, device state, or firmware image were edited. User scope permits dropping stock MemoMind plugin/cache compatibility. The target interval is the entire **3 MiB CUS8 allocation**, not the entire 8 MiB device1 chip.

## Six gates and immediate consequences

Root's inspected `scripts/build_memomind_exclusive_storage.py` returns `-5` at mount and `-1` at the other five entries. Its reset gate covers the full first six instruction bytes; the others cover four. These are immediate `C.LI a0,error; C.JR ra` stubs, with a reset padding NOP. No original prologue runs. Root's retained `analysis/exclusive-storage-native-002/report.json` reports all 96 actual RV32 entry cases passed. I inspected that result, not independently re-executed its harness. Entry emulation establishes immediate return/register/memory behavior; it does not execute downstream callers or hardware.

| Entry | Ordinary stock effect removed | Review conclusion |
|---|---|---|
| `042a43c8`, mount/init | Context allocation, mount, empty-store format, repair/remount, wipe recovery admission, app-header identity read | `-5` is an existing native failure value. All five recognized direct callers require zero before accessing the resulting context. |
| `042a3e20`, read callback | Bounded CUS8 device1 reads | `-1` refuses without writing the caller's output. Prevents interpreting new CFW bytes through this callback. It does not disable all raw reads. |
| `042a40c4`, program callback | Store directory/journal/package programming and verification-cache changes | `-1` prevents both program and cache-state mutation. Core compaction/journal paths use this configured callback. |
| `042a411e`, erase callback | Directory/journal rotation and package/move erases | `-1` prevents these configured erases. |
| `0423e8b4`, full reset | KV6008 wipe intent, full good-sector erase/verify, wipe completion and runtime reentry flags | Immediate `-1` blocks the raw full-region erase route that bypasses store callbacks, and leaves flags/KV unchanged. |
| `042a9dd4`, badmap saver | Persist 116-byte physical badmap record to device0 KV6009 | Immediate `-1` prevents stock badmap persistence. Keep the validated read-only loader/getter for diagnostics; this gate must not be mistaken for an all-good bitmap. |

Callback identities and store config are proven in [native-store-capacity](../ghidra/native-store-capacity/report.md) and [raw callback instructions](../ghidra/app-tail-store/native-store-callbacks.asm). Whole reset instructions and semantics are in [0423e8b4](../ghidra/native-store-capacity/lifecycle/function-0423e8b4.c). The gate table's exact current source hash and inspected evidence hashes are in [sources.json](sources.json).

These entry gates are redundant intentionally: blocking mount prevents ordinary context creation, while callback/reset/saver refusal still protects against recognized work that could otherwise use those entry points. They are not a security boundary against code directly calling the raw flash driver or branching past an entry stub.

## Caller failure handling

The recognized incoming calls to mount are preserved in [store-init-callers](../ghidra/flash-topology/store-init-callers.txt):

- Installer `042a4598` tears down any old context, calls `(0,0)`, and returns nonzero without copying a descriptor or invoking allocation when mount fails. It does not claim installation success.
- Capacity query `042a4628` calls `(1,1)` only with no existing context. It calls the query core and frees the newly mounted context only after success. A `-5` leaves the caller-owned result unused. The worker zeroes its temporary query result; display completion `0426223c` emits status byte `5` and includes the 24-byte capacity payload **only for native status0 or -9**, so this chosen failure does not serialize an uninitialized capacity result.
- Use/select `042a4994`, remove `042a49e2`, and the other package mutation `042a4a2c` all branch around core operations and context dereferences on nonzero mount status. No assertion or forced reset was observed in these direct failure branches.

Sources: [installer](../ghidra/loader/function-042a4598.c), [query](../ghidra/loader/function-042a4628.c), [select](../ghidra/loader/function-042a4994.c), [mutators](../ghidra/loader/function-042a49e2.c), [other mutator](../ghidra/loader/function-042a4a2c.c), [worker](../ghidra/display-adapter/event-api/function-042a90ba.c), [completion](../ghidra/display-adapter/completion/function-0426223c.c).

Reset wrappers `0423eb42` and `0423eb52` forward a0 unchanged back to their callers despite decompiler `void` prototypes. In the worker's `0xfffc` job, reset `-1` maps to native failure `-5` (reset `-2` maps to busy `-3`); it then follows the ordinary completion path. Mount's old reset/retry sequence becomes unreachable because the mount gate returns first. A failure is preferable to returning success and implying the old package store was formatted or cleared.

This does not promise the unmodified phone UI will present graceful messaging or stop retrying an unavailable stock feature. That compatibility is outside the new scope. Existing send/allocation failures and the worker's retry-until-display-queue-accepts loop remain stock behavior. The review did not establish every high-level consumer's UX or liveness under repeated refusal.

Read callback failure leaves destination bytes untouched by design. It must not return0 while doing nothing. Ordinary mount is also gated, so the recognized mount/repair machinery cannot treat an unchanged output buffer as a valid newly read directory. Existing active contexts are handled by the reset boundary below, not by assuming every internal callback failure combination is fully audited.

## Other device1 writers: recovered ordinary bounds

The earlier recognized reference inventory covers program12 references, range-erase6, sector-erase4, RMW7, plus raw CUS8 callbacks without Ghidra function definitions. Lower program/erase references lead to these public routes. This inventory is a recovered-reference boundary; computed or unrecognized instructions are not proven absent. See [tail owner report](../ghidra/tail-reservation-review/report.md).

The acquired bootmap has:

| Allocation | Unified interval | Device1 physical interval |
|---|---|---|
| c6 resources | `[01000000,01400000)` | `[00000000,00400000)` |
| c7 recording | `[01400000,01500000)` | `[00400000,00500000)` |
| c8 old package store | `[01500000,01800000)` | `[00500000,00800000)` |

[Captured bootmaps](../ghidra/boot-validation/captured-bootmaps.json) are the map provenance. The new caller exports close the important distinction between a partition name and the actual caller-supplied address:

**Resources.** `04341354` obtains typec6 and returns its unified start plus `04000020`; `043412ec` obtains c6 size. The only recognized erase caller `0423e1a0` uses that returned base minus32 and the c6 size. Its only recognized program chain calls `0423d4ea` with that same base as fourth argument; the latter calls `043414a6` at four sites. The program wrapper requires nonzero length, offset <=size-32, and length <=size-32-offset, then strips the base to its low24 bits and adds the offset. Consequently the inspected valid-map path ends at physical00400000, below the proposed store. Its low-level erase wrapper accepts an arbitrary base and only compares length to c6 capacity; therefore the caller evidence, not the wrapper alone, supports the exclusion.

Sources: [base getter](native/function-04341354.c), [resource owner](callers/function-0423e1a0.c), [program routing](callers/function-0423d4ea.c), [program wrapper](../ghidra/tail-reservation-review/owners/function-043414a6.c), [erase wrapper](../ghidra/tail-reservation-review/owners/function-043413ae.c), [recognized refs](callers/functions.json).

**Recording.** `0420ff1a` explicitly resolves typec7, derives sector capacity, rejects an out-of-range starting sector or count, then stores the accepted ring base/capacity in `02012804/02012808`. Its initial erase uses precisely that range. `04210120` requires initialized state, checks free space against requested bytes, and splits writes at the ring boundary before calling raw recording program `0420fe3e`. `042105d4` similarly splits pending erase sectors at the end and wraps to the same initialized base. Thus the ordinary initialized ring stays in c7 under its normal ring-state invariants. The lower recording wrappers themselves have no c8 protection. Corrupt ring counters or arbitrary lower-wrapper calls are not covered by this conclusion; this pass is not a full proof of every ring-state producer or malformed-input path.

Sources: [recording initializer](native/function-0420ff1a.c), [program](record/function-04210120.c), [erase consumer](callers/function-042105d4.c), [lower program](native/function-0420fe3e.c), [lower erase](../ghidra/memory-capacity/flash/function-0420fd64.c), [program callers](record-program-callers.txt).

**Other routes.** The known generic sector-mapped OTA backend uses the general SPI0 controller and a separately identified supported endpoint, not CUS8's XIP controller: [topology report](../ghidra/flash-topology/report.md). Its 3 MiB logical map does not become part of this reservation and must not be patched as if it were CUS8 capacity. The static report's electrical-isolation caveat remains; this review did not acquire fresh probe IDs or board measurements. Device0 KV, config, bootmap, staging and app-update owners remain separate physical namespaces.

The six gates do not disable c6/c7 functionality. Keeping those regions intact is also important for the new software's native fonts, display resources, and any surviving recording code, regardless of whether phone compatibility is required.

## Boot, reset, and future images

Ordinary app startup `041eb020 -> 041fb1ec` zeros BSS `[02011878,0205e128)`, including CUS8 singleton `02011e48`, active offset/validated state `02011e4c/02011e50`, before constructing normal task/heap state. The six gates therefore start with no old package context after the normal OTA reset/handoff. They are **not** a hot-unmount protocol for code or callbacks already running from CUS8. Require the ordinary reset boundary before reclaiming bytes. Do not free an active context or overwrite a package that a preexisting runtime could still execute.

No CUS8 mount is called by the captured reset-time app body verifier. The acquired boot image selects the app partition/header and verifies the declared app body on its inspected route; CUS8 contents are not part of that body. The native gate edits still require correct rebuilt app/container integrity fields, which the root constructor handles. This review did not rerun the constructor or validate the full OTA artifact independently.

A separate checker `0423e7f4` remains: it reads KV6008 and the first64 CUS8 bytes through raw `04329ad8` to infer pending reset state. It does not itself erase/program; mount refuses before reaching it and the actual reset entry is gated. Its remaining raw read is a concrete reason not to claim that every stock access to CUS8 disappears. If called independently, it can report the new CFW format as needing old-store reset, which then fails at the gated reset entry. No requirement to zero KV6008 or synthesize a stock-valid directory follows from this review.

[Boot validation](../ghidra/boot-validation/report.md) and [startup lifecycle](../ghidra/flash-topology/report.md) are the scope. Captured ordinary boot evidence does not cover ROM factory paths, arbitrary bootloader/download commands, or all update destinations. Six app-entry gates cannot govern code running before the app or a future image that restores stock ownership. The existing original c8 bootmap entry remains a stock owner declaration. Future CFW constructors must preserve the gates and the exclusive-layout identity; unpatched stock/factory/rollback images invalidate the storage ownership contract and may reclaim the entire region. Do not promise persistence across them.

## Boundaries for the next stage

This review supports proceeding with the **offline candidate and caller tests**. It does not add a live flash writer or prove mutation admission. The physical badmap must remain the validated96-byte map for all768 sectors, with absent/default provenance retained; the old first16-sector bitmap restrictions do not prove those sectors have been tested healthy for a new format. Usable CFW capacity must deduct its own metadata, bad sectors, and any recovery/spare requirements from the 3 MiB physical interval.

The next storage implementation still needs its own range-checked native writer, source lifetime, serialized operation ownership, post-write readback, correct device1 XIP cache maintenance, transactional recovery, and map-epoch reader lifetime. [External XIP review](../ghidra/external-xip-review/report.md) establishes `physical+05000000` and explains why the public program/erase wrappers' `physical+04000000` cache operation alone is insufficient for device1. Removing stock compatibility does not remove those requirements.

No discovered ordinary owner contradicts the six-gate plan under the pinned map and reset assumptions. Remaining gaps are explicit: unknown indirect/raw owners, malformed state outside audited caller bounds, alternate boot/factory paths, future unpatched firmware, chip/cache concurrency, and unperformed hardware lifecycle validation. These are limits on an exclusivity claim, not a request for permission or a reason to block the offline constructor.
