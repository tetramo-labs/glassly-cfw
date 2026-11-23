# Implemented mode8: independent source review

**No concrete implementation blocker found** in the pinned source/build reviewed here. This is read-only inspection; no production/test changes, test reruns, image changes or device actions were performed. Exact hashes and findings are in [implementation-review.json](implementation-review.json). Reviewed production sources match `runtime/build/bundle-commands-001/build.json`:63200-byte blob SHA256 `deeddff1533fc36c5468394a1fbbd612d3a2ec096dc864d963fa3cc30148f450`, inside the unchanged65536-byte limit.

## Ownership and collector

`graphics.c::begin_bundle` allocates `2*count*sizeof(uint16_t)` with the existing native try allocator before session prepare/dispatch. Count is the input byte, so capacity is at most510 tags/1020 bytes; uint16 counts/capacity avoid uint8 wrap. Count0 uses NULL storage with capacity0 and never dereferences it on the valid no-segment path. The overflow branch sets an explicit error; `scene_present` suppresses presentation if this invariant is violated.

Collection is attached before `mm_scene_session_dispatch`, so prepare/reap notifications are captured. `scene_settled` preserves insertion order and duplicate tags. The count+1 bound established in the design review includes an existing pending tag and any prepare/reap consumption. SHOW can create one new pending tag, HIDE can directly emit one; other paths consume existing state. No timer/reentrant dispatch may interleave on this worker.

`glassly_graphics_display` always reaches its result-send and `flush_settled(executed)` after bundle admission, including malformed/unsupported subcommand, capacity failure and JSON-response failure paths. Flush sends the correlated result first, then the captured tags using the same saved request event, resets all borrowed collector fields, and frees storage once. Native sender copies response bytes before returning; TLVs are released after each call. The stock worker retains envelope ownership and frees it after the display gate returns. No pointer into the envelope or collector survives dispatch.

The DELETE callback does not free a live collector itself. This is consistent with the explicit synchronous/no-reentry contract: callbacks, native send and presentation must not delete the owner while a display dispatch holds it. The inspected native paths do not pump LVGL recursively; future callback changes must preserve that rule. The ordinary four-tag collector is used only outside bundles and is flushed after every ordinary dispatch/timer tick, so no prior ordinary tags should remain on bundle entry.

The1020-byte buffer is outside the170KiB scene allocation accounting, but native admission explicitly checks32KiB transient free headroom plus its requested bytes. Later scene allocations still apply the48KiB policy. These are snapshot policies, not an atomic reservation/largest-free guarantee. No large collector was placed on the task stack.

## Prepare, parse, scratch and presentation

`scene_session.c::bundle` calls `mm_scene_prepare(...,8,data+1,size-1)` exactly once. Segment dispatch never calls the top-level session recursively and never repeats per-segment prepare. Input/session/core/pixel/owned-cache alias rejection occurs before prepare; each subrange lies in the immutable stock-owned envelope already checked. New allocator blocks must remain disjoint as required by the existing callback contract.

The parser checks two-byte segment headers and positive lengths against remaining bytes. The cursor cannot exceed size before a subtraction. Both outer and child modes are masked with127. Count0 and trailing bytes are accepted; unsupported15, nested8 and other control modes return failure explicitly. **Whole-batch preflight was not adopted:** as in the pinned sequential model, prepare can allocate/reap and earlier segments can mutate before a later rejection. This is documented in source comments/tests and is not a hidden all-or-nothing claim.

Session entry clears reply scratch once. Each37–41 dispatch resets/replaces it internally. Mode3/6/9 and normalized19/20/36 do not clear it, so cache→raster preserves the final cache reply, whereas cache→STATE-no-page leaves no reply. `graphics.c` wraps the final scratch only after a successful outer dispatch; a failed later segment returns ordinary failure and suppresses prior successful cache scratch. Embedded cache REFUSED/CAPACITY statuses are still handler-success replies, matching the original core contract.

`mm_scene_immediate_mode` separates normalized child mode from the unchanged payload buffer. Normal `mm_scene_immediate` still supplies its original first byte, preserving legacy caller behavior. Native bundle callers only pass19/20/36 after mode selection; no mutable scratch copy or borrowed input rewriting is introduced.

Raster3/6/9 validation precedes takeover as established Memo hardening. Cached immediate19/20/36 retain the existing Memo draw-then-successful-takeover ordering. Cache dispatches use `present=0`; immediate/raster segments never call the final presentation hook. Only complete success, including count0, invokes it once. The image canvas is shared with LVGL: failure suppresses this explicit call but cannot guarantee earlier pixel mutations stay invisible on unrelated future refresh. No rollback claim is supported.

## Evidence checked and remaining limits

Existing agent-produced reports reviewed, not rerun:

* `analysis/bundle-commands-001/host/report.json`: sanitizer suite passed with no source drift. Tests cover255 segments plus an initial pending tag,256 ordered duplicate-capable settled callbacks, count0, collector OOM/headroom, response JSON failure, late failure, cache→raster preservation and STATE scratch clearing; all unsupported byte modes tested through the sequential adapter.
* `analysis/bundle-commands-001/rv32.json`:124 actual compiled-code calls/7 groups passed with native mocks.
* `analysis/bundle-commands-001/gates.json`:7955 actual RV32 gate cases passed; gate/native/C boundaries are explicitly mocked as described in that report.

These establish offline behavior for the pinned artifacts, not hardware delivery or visual update. `P.send` still discards native queue-admission return; native JSON/TLV allocation can fail or assert. Up to256 notifications flushed on the display worker can incur substantial retry delays. The implemented guarantee is bounded ordered local collection with existing best-effort GM sends, not an acknowledged persistent outbox. Native8192-byte ingress,64KiB asset store, current lease/UI rules and unsupported mode15 remain unchanged.
