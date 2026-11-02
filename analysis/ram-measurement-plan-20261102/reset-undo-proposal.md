# Proposal: release undo scratch after a top-level RESET

This is a narrow optional Memo runtime memory policy, **not** a drop-in change to upstream `cfw_cache_reset`. No source has been changed. The measured baseline remains frozen in `baseline-verification.json`.

## Exact ownership and retained fields

`cfw_cache` owns `undo` and `undo_capacity` (`scene_internal.h:303–304`). `cfw_undo` contains a complete43420-byte cache snapshot, a2048-byte saved-granule bitmap, and a flexible array of20-byte saved granules (`scene_cache.inc:363–367`). Thus its RV32 base is45468 bytes. It is allocated by `cfw_cache_prepare_undo`, through `mm_scene_allocate(ctx, MM_SCENE_PERSISTENT,...)`, before transaction dispatch. The native adapter prepends an8-byte allocation header, charges `live_bytes`, and delegates to its platform allocator (`scene_session.c:15–31`). Free must go through `mm_scene_deallocate` with the same owning context/kind; the adapter subtracts header.bytes and frees the original header pointer. Freeing `sc->undo` directly with the native heap function would be wrong.

The allocation is presently preserved on RESET (`scene_cache.inc:1916–1936`): stop animation, queue any pending settled notification, save period/work/undo/capacity/store size, zero the metadata, restore those fields and owner, advance/adopt the epoch. The original array-backed store remains allocated and its logical capacity is reported by RESET. A transaction is embedded in `sc->txn`; successful RESET zeros it and all objects/assets/journal/active lists. Cleanup/reap, by contrast, frees undo, vector workspace, metadata and store (`scene_cache.inc:319–337`).

On PUT/SHOW, `cfw_txn_snapshot` copies all metadata into undo before changes. Abort copies the snapshot back, including the owning pointers (`scene_cache.inc:1036–1058`). Commit clears `undo_active` (`1368–1371`). `undo_active` is not a reliable free-standing lifetime guard after all paths because abort restores the prior transaction snapshot. A trim must rely on the completed RESET boundary, not an arbitrary observation that `undo_active` is zero.

## Two reasons not to free inside RESET

The original pinned test `patches/host/shapes_host_test.c:1355` asserts:

```
CHECK(send(41) == 0 && sc->undo == undo);
```

The same predicate remains in the portable suite at1312. It tests RESET retention intentionally. Keep this assertion and the original default production behavior. If the Memo native policy opts into trimming, document it as a platform memory-policy difference and test it separately; do not edit that predicate or relabel the changed native policy as identical retention.

Bundle prepare (`scene_cache.inc:425–438`) allocates scratch for all embedded PUT/SHOW segments **before** any child is dispatched. An embedded RESET can precede a PUT in the same bundle. Freeing inside RESET would destroy scratch already promised to that later PUT, which then runs without another prepare. Existing array-store `cfw_txn_snapshot` permits missing undo and revision50 fallback can retain evictions on a rejected transaction (`966–972`, `1630–1635`). This would silently weaken rollback compared with the pre-trim execution. Freeing vector workspace there would also invalidate later prepared path/rotation commands.

## Minimal scoped implementation

1. Leave `cfw_cache_reset` and every upstream assertion unchanged. Add one explicit portable API that discards **undo only** immediately after the caller has completed a successful whole-request RESET. Keep vector, metadata, store, limits, epoch, revision, reply bytes, timer and pixels unchanged. This API is policy opt-in; normal portable tests never call it.
2. Require the caller to own the serialized scene worker, be outside `mm_scene_dispatch`/all bundle execution, and invoke it immediately after the top-level mode41/subcommand0 RESET returned APPLIED. A safe implementation validates context/cache ownership and an empty reset state before detaching anything. In particular, no active objects, pending mutation, pending render or nonempty descriptors; no arbitrary midtransaction use. Pointer ownership uses `sc->owner==ctx` and the normal scene magic. Reset status must be checked from the freshly produced cache reply, not inferred from `rc==0` because CAPACITY/STale replies also return0.
3. Save `old=sc->undo`, set `sc->undo=NULL` and `sc->undo_capacity=0` **before** invoking the paired deallocator, then free only `old` through `mm_scene_deallocate(ctx, MM_SCENE_PERSISTENT,old)`. The adapter requires synchronous nonreentrant callbacks. Detaching prevents later cleanup from double-freeing. If no undo exists, do nothing and report zero saved bytes. The API need not return a native largest-block or promise actual allocator coalescing.
4. Call this only from the unbundled mode41 branch of `mm_scene_session_dispatch`, after `mm_scene_dispatch` has returned and its reset reply is complete. Do not call it from `bundle_segment`, generic core dispatch, `cfw_cache_reset`, or a timer. Initial narrow scope should skip every bundle, including a bundle whose final child is RESET. That rule avoids having to infer prior effects or later prepared scratch from final reply bytes.
5. Leave the next command's existing prepare path in place. A subsequent PUT with entries will recreate undo before mutation; an empty PUT or SHOW without puts does not need byte rollback and can stay allocation-free. Ordinary SHOW after a successful newly prepared PUT must still allocate nothing. A second RESET after trim is idempotent with respect to scratch allocation.

### Allocation-failure contract needs an explicit decision

Releasing retained undo necessarily trades residence for future reacquisition. A later allocation can fail where reuse previously succeeded. Current upstream array-store behavior allows no-undo execution and nonrollback eviction on rejection; its original suite explicitly tests that behavior (`shapes_host_test.c:1332–1341`, portable1289–1300). Therefore a claim that this optimization preserves every previous allocation-failure outcome is false.

Recommended native policy if preserving strong rollback is required: mark the native trimming policy explicitly and, after the next mutation's prepare, reject CAPACITY **before mutation** when required undo could not be reacquired. Do not enable this guard in the default upstream-compatible path; otherwise the original no-undo assertions change. Cover mixed bundles too: either retain prepared workspace throughout the bundle and apply the native guard per mutating child, or reject before affected child mutation while retaining earlier child effects, as mode8 already specifies. The external-store path already requires undo for metadata rollback. Do not replace RAM undo with fallible flash reads.

If exact upstream no-undo fallback is required on Memo as well, preserve it and explicitly document that trimming makes that resource-pressure path more reachable. This is a real semantic/resource tradeoff, not an invisible refactor. Parent should choose the policy before implementation.

## Requested-byte saving, precisely bounded

For an existing allocation of capacity `C` saved granules, undo payload freed is `45468 + 20*C` bytes on RV32. The native adapter releases another8-byte header from its budget: **45476 +20*C requested bytes**. Native heap alignment/metadata may make allocator accounting differ; no guessed extra savings are claimed.

- Existing minimum/fallback capacity0:45476 requested bytes (44.410KiB).
- Typical first small PUT capacity64:46756 requested bytes (45.660KiB).
- After larger transactions: the same formula, using actual current `undo_capacity`.
- Fresh cache that never allocated undo: **zero**.

This change does not reduce peak transaction RAM or the logical256KiB target, and it cannot improve an already idle/no-undo baseline. Its useful measurement is same session after a known PUT followed by explicit RESET, with matched display/connection state. Compare before/after heap samples and adapter `live_bytes`; keep probe overhead and native asynchronous traffic in mind. Preserve metadata/store/canvas so the comparison measures this allocation rather than whole-scene teardown.

## Required tests before a candidate

Retain all upstream predicates unchanged: `test_transaction_rollback` workspace retention, no-allocation ordinary SHOW, full-cache overwritten-byte rollback, small-undo refusal, no-undo revision50 fallback, prepare-before-gate and no gate allocations; `test_cache_basic` RESET epoch/empty state/session epoch; `test_state` journal/snapshot/reset semantics; `test_lifecycle` cleanup/lease loss; vector path/rotation/tween/bundle fixtures.

Add opt-in native-policy tests that (a) create real undo through PUT, (b) compare exact RESET reply/epoch/journal/capacity/pixels with unchanged core, (c) call trim and assert only undo/header released using the formula, (d) repeat trim and cleanup with no double-free, (e) recreate via next PUT and verify ordinary SHOW remains allocation-free, (f) force every reallocation failure under the chosen explicit policy and check descriptors/store/revision/pixels/settled effects, (g) exercise bundle RESET→PUT, PUT→RESET→PUT and malformed late children while verifying no trim inside a bundle, (h) assert no trimming on stale/malformed/CAPACITY control replies, (i) test an outstanding settled tag and timer stop without freeing queued caller-owned state, and (j) ASan/UBSan and actual RV32 allocator/header/lifecycle checks. Hardware savings require the opt-in native candidate and measured allocation history, not a standalone source arithmetic claim.
