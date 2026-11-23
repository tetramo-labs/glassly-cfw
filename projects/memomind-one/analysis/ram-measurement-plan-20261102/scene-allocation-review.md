# Scene allocation lifetime review

The raw baseline verification passed:13 requests and correlated replies, including10 heap samples, current-free333980..334108 and low-water320068. `baseline-verification.json` pins the capture and independently cross-checks saved data against parsed GM bytes. No display command, OTA command or flash mutation appears in the transmitted stream. The verifier checks checksums/fragments, successful exact TX completions, request order and keys, optional bounded ACKs, app header and complete capability schema. It ignores no service15 business response. Ordinary unsolicited traffic is cross-checked against logs after the reserved-service sequence starts. Raw device-info can contain additional stock fields; the five typed identity fields are cross-checked against `device.json`. Trace-record timestamps and result-sample timestamps are separate captures; both are ordered against the raw response, not incorrectly required equal.

There is no obvious large eager allocation in `mm_scene_session_init`: `scene_session.c:87` adapts callbacks and calls `mm_scene_init`, whose `scene.c:163` implementation zeroes and fills the inline context without allocating. The scene timer adapter returns a sentinel and uses the owner's existing serialized worker pump; it does not create another native timer. The telemetry query itself does not create a scene. Scene improvements therefore do not establish a saving in the measured idle baseline or attribute its existing stock allocations.

The relevant RV32 layout is already measured in `analysis/regression-20261102-04/scene/report.json`:

| Allocation | Bytes excluding adapter/native heap overhead |
|---|---:|
| Inline scene context |1016|
| Retained cache metadata |43420|
| Vector workspace |10752|
| Undo metadata base |45468|
| Each additional saved16-byte granule |20|
| Current native logical store |65536|
| Full intended logical store |262144|

The session allocator adds an8-byte RV32 header to each allocation, enforces a170KiB session budget and48KiB stock headroom, and then calls a fallible allocator. The graphics owner separately allocates a105064-byte palette+600x350GRAY4 canvas. The reference small transaction uses166456 bytes for metadata+64KiB store+vector+undo base+64 saved granules before allocation headers/native overhead; canvas adds105064. These are layout totals, not measured per-owner live consumption. Installed native initialization passes `MM_SCENE_MIN_STORE`; its64KiB limit is existing integration scope, not full G2 capacity. Any future optimization must preserve the full portable256KiB target rather than lower limits to fit RAM.

Potential improvements, ordered by how clearly they avoid unnecessary residence:

1. **Demand-gate vector workspace.** `scene_cache.inc:447–449` allocates10752 bytes for every mode37 PUT or mode38 SHOW, including asset-only uploads and ordinary unrotated primitives. `scene.c:71` already has geometry rendering without workspace, and `vector.c:278` directly draws zero-angle geometry. Path compilation and rendering require the workspace; ROTATE explicitly rejects absent workspace at `scene_cache.inc:1510`. A preflight must inspect paths and rotations, existing active objects, tween trajectories and every ordered bundle segment before deciding no workspace is needed. Do not simply remove allocation: accepted rotation/path commands must remain supported, and late allocation cannot occur after visible mutation or in an unsafe lock context. Preserve all original pixel, rollback, refusal and ordering assertions with both workspace-present and absent paths.

2. **Release scratch on RESET where nothing retains it.** `cfw_cache_reset` at1921–1934 explicitly preserves vector and undo pointers after stopping the scene and clearing objects. This keeps prior peaks resident even though the cache is empty. Releasing those two workspaces at a proven serialized RESET boundary could reclaim10752 plus at least45468 bytes after prior PUT, while retaining store reservation, metadata, exact epoch increment, revision/reset reply and logical capacity. Subsequent commands must allocate at preflight and fail before mutations if allocation fails. This changes residency and future allocation availability, so validate fault-injection and bundle ordering rather than calling it a semantics-free edit.

3. **Shorten transaction undo residence.** Undo consists of a complete metadata snapshot plus saved store granules (`scene_cache.inc:363`), allocated/grown before dispatch and then reused indefinitely. Commit clears `undo_active`; abort restores metadata and bytes. Once abort/commit and all consumers of the snapshot have finished, transaction scratch is a candidate for release/reuse by a later serialized request. This reduces steady residence but not peak transaction RAM and increases allocation churn/failure opportunities. Audit `cfw_txn_abort`'s memcpy restoration of the entire cache, embedded pointer fields and all cached transaction references before freeing. Do not move undo to flash: a fallible abort read would break the current nonfailing RAM rollback guarantee.

The store is also allocated before some commands that do not write assets: `cfw_cache_prepare` admits37..41 except40 and invokes store allocation before RESET. Its RESET reply advertises the obtained store size. Deferring that physical reservation while still promising identical capacity is not an obvious safe optimization. Releasing committed objects/assets or shrinking descriptor/object/journal limits would change retained-scene semantics. Full flash-backed store integration is separate and remains necessary if RAM cannot provide the full intended capacity.

Cleanup/lease loss already stops the scene and frees vector, undo, cache and store under the serialized display ownership boundary (`scene_cache.inc:319–337`, `scene_session.c:239–249`). The framebuffer pointer in cache metadata is borrowed; it must not be freed separately. Do not use cleanup as a silent measurement normalization step because it changes visible/stateful behavior. The baseline helper deliberately did not do so.

No production files or allocation policy were changed. These are source-derived candidates requiring implementation, host differential/fault tests and actual RV32/native lifecycle proof before any RAM-saving claim.
