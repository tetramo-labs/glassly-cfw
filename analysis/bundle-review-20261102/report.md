# Mode 8 native design review

Read-only review of G2 commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce` and the Memo display/session adapter. No production/test/device changes. Source paths under `upstream/` below mean `tests/g2_compat/upstream/`. This report separates lossless local notification collection from native transport delivery; the latter is not guaranteed by the existing API.

## Contract and preparation boundary

`upstream/patches/zlib_glue.c:310–402,406–427,613–639` establishes this sequence:

1. Receiving worker acquires the image mutex, clears `cache_reply_len` once and sets reply capacity.
2. For a shadow message, it calls `cfw_cache_prepare(ctx, src[0]&127, src+1, size-1)` **once for the top-level message**, before acquiring the display gate.
3. Under the display gate it calls `image_dispatch(..., present=1)`. Mode8 walks its segments, dispatching each with `present=0` and shared dirty accounting. On complete success it calls `present_shadow` exactly once.
4. Worker copies the final reply scratch once, then releases the mutex. A failed presentation changes the handler result to failure.

The wire format is `[08 or88][count:u8][length:u16LE][submessage]...`. Both outer and submessage modes are masked with127. Count0 is valid and still presents; trailing bytes after the counted segments are ignored. Each segment length must be positive and fit the remaining message. Nested08/88 is rejected. Allowed submodes are3,6,9,15,19,20,36,37–41. The older comment naming only37/38 is less complete than the actual condition. Control and cleanup modes5/7/10/11/16/17 are not allowed.

`upstream/patches/scene.c:403–442` / portable `scene_cache.inc:420–459`: prepare traverses a syntactically framed bundle and prepares only37–41. STATE40 exits without allocation. Other cache modes may reap lost state, check the lease, allocate the descriptor/store; PUT/SHOW may allocate vector workspace and grow transaction undo storage. It is a **void** function, and neither successful parsing nor successful allocation is guaranteed by its return. It may have already allocated or reaped when a later segment is malformed. Existing core handlers must still return capacity/stale/refused status normally.

The bundle prepass can build a sufficiently large undo workspace for later segments before execution. Do not replace it with a loop of top-level `mm_scene_session_dispatch`, which resets reply state, prepares separately and presents each segment. Native Memo does not acquire the G2 display semaphore; its already-serialized display worker and reviewed allocator callbacks remain the applicable ownership model. The old G2 lock-order explanation is not permission to add that semaphore to Memo.

A framing/admitted-submode preflight before any prepare is a reasonable explicit Memo hardening. In particular reject nested08/88 and unsupported15 before preparation/execution if15 has not been implemented. Do not advertise immediate text support simply because G2's allowed set includes it. Preflight should not pretend it can validate all semantic dependencies: a later draw may depend on an asset uploaded by an earlier PUT in the same bundle.

## Failure effects and raster ownership

There is no transaction spanning the entire bundle. A later malformed/refused subcommand can follow earlier successful mutations. Syntactic/handler failure stops the walk and suppresses the final presentation; earlier shadow/cache/timer/settled effects remain. Native code must not report rollback unless it actually implements it. Individual PUT/SHOW transactions retain their own rollback/refusal contracts. A cache status such as CAPACITY can return handler0 with a reply: that is not automatically a bundle abort. Test return-code semantics separately from embedded status bytes.

Raster subcommands retain normal takeover behavior even inside a bundle. Original takeover occurs before their mode-specific validation, stops animation, freezes and unpins active objects without clearing the canvas or destroying cache, and can emit a pending settled tag. Memo modes3/6/9 intentionally validate first; preserving that hardening is acceptable when explicit. SHOW→copy and copy→SHOW have different results. A following SHOW may repaint over prior raster mutations. The pinned resync-shadow function is a no-op because retained framebuffer aliases shadow.

Subcommands with `present=0` must still perform their actual rendering/metadata work and accumulate dirty bounds. Do not defer all drawing until the final present: that breaks dependencies and ordered compositing. Native intermediate `image_source`/cache-invalidate calls must be suppressed, with one final presentation after successful dispatch. A failed bundle may have mutated the shared LVGL image buffer: suppressing the explicit present is **not proof that pixels can never appear** during a later unrelated LVGL refresh. This is another reason not to call failure atomic rollback.

## Exact cache reply semantics: one final scratch

This is the critical correction to the earlier idea of collecting every subcommand reply:

* Top-level `image_worker` clears scratch at `zlib_glue.c:327`.
* Every cache dispatch37–41 clears it at `scene.c:1839` before executing the cache handler.
* Raster3/6/9/15/19/20/36 does not clear scratch in the original dispatcher.
* Thus PUT→copy retains PUT's reply; PUT→STATE replaces or clears it according to STATE; PUT→bad raster leaves scratch in memory, but the outer failed handler does not send it.
* Worker copies scratch at `zlib_glue.c:356–360`. `message_transport.c:206–211` sends that one reply only when the handler returns success; otherwise it sends the handler NACK path and invalidates stream compression context.

The Memo adapter should clear scratch once at bundle entry, use normal cache dispatch resets, and preserve scratch across raster segments. On success return the final scratch using the existing scene `replyHex` response when nonempty, otherwise ordinary graphics success. On failure send ordinary failure, not an earlier successful cache reply. Do not manufacture an all-subcommand reply stream; that would be a new protocol extension. Rendering success and a final cache REFUSED/CAPACITY response can coexist according to the original return convention, and the host must inspect the cache status.

## Settled notifications: bounded collection proof

Source: `scene.c:300–304,1638–1647,1669–1674,1757–1761` and `settings_ext.c:207–221`.

`cfw_scene_settled` only emits when `settle_pending` is set, then clears that bit. A tagged SHOW creates at most one new pending tag. HIDE may consume a pending tag and directly notify its own request tag once. RESET, raster takeover and prepare/reap can consume a pending tag but do not create a new one. No other direct settled producer occurs in these admitted dispatch paths.

Assuming the established no-reentry, single-display-worker execution contract and no animation timer interleaving during one bundle, there is at most one pending tag on entry. Therefore for N admitted segments:

`callbacks <= tagged_SHOW_count + direct_tagged_HIDE_count + initial_pending <= N+1`.

This includes a pending tag consumed by preprepare/reap: it is the same one-entry allowance, not a new independent tag. With N>=1, conservative capacity `2*N` is sufficient; maximum510 uint16 tags/1020 bytes for255 segments. Count0 causes no prepare/subcommand settled callback and needs no bundle collector. A single tagged HIDE with an existing pending tag realizes the two-callback case. Repeated equal tag values are legal separate callbacks: **preserve duplicates and insertion order**.

The current four-tag array and uint8 count are insufficient. Use at least uint16 capacity/count/cursor for the bundle collector. Allocate it before preparing or executing any segment; attach it before preprepare so reaped tags are not lost. Prefer a separate bounded try-allocation only for bundles over a1020-byte task-stack array or enlarging every persistent owner. Check free-space/headroom policy including this extra allocation and all incoming/queued data. If collection memory cannot be obtained, reject before bundle side effects; the owner may already have been created, so do not incorrectly claim zero allocation anywhere in the request path.

A safe local lifecycle is:

1. Validate outer framing/admitted submodes and pointer disjointness; compute bounded capacity.
2. Allocate collector, initialize count/cursor, attach to the live display owner, then preprepare and execute.
3. Build/send the single correlated execution result. Flush collected settled tags in original callback order after that result, matching the existing Memo response-before-settled policy, on both success and partial-failure paths.
4. Detach/reset collector state and free it exactly once on every path. Timer notifications outside a bundle retain the ordinary small collector. No callback may destroy the owner or synchronously reenter dispatch while this attachment is live.

Original G2 sends settled callbacks immediately through settings field129 and can do so before its eventual reply/ACK. Memo already deliberately buffers them until after its correlated response; keep that documented ordering rather than calling it identical wire timing. Each collected tag must carry the original bundle request event, not a later command's mutable event.

Collector capacity is a proved invariant under the stated sources, but still guard it at runtime. An unexpected overflow must become an explicit internal failure, never silent `if(count<4)` truncation. A guard cannot undo prior mutations or recreate a dropped callback; tests must prove the bound and no-interleaving contract. Use synthetic255-segment inputs and existing pending tags, not only a two-segment raster batch.

## Native send behavior and limits

Existing evidence: `analysis/ghidra/display-adapter/report.md:258–297,393–409`; native veneer `runtime/graphics/native.c:31–34`.

`0x042e866e(event,15,0x7d,tlvs,1)` serializes/copies TLV content and queues independent packets; caller releases its response after return. Return1 means packet copies were queued, not received. Return0 can mean disconnected or failed admission. Existing `P.send` is void and discards that result. Response JSON/TLV construction also uses native allocation and can fail or assert under native OOM policy; the try-allocated tag array does not eliminate this separate risk.

The route1 non-BT sender retries at most five times per packet, with up to20 explicit sleep ticks total (configured20ms), plus allocator/scheduler/logging costs. As many as256 settled notifications can therefore request about5.12 seconds of retry sleeps if flushed inline; this is not a hard wall-time bound. It can delay display timers, scene lease checks and UI handling. Most settled JSON records fit one packet, while the final cache `replyHex` may exceed503 payload bytes and need more than one.

For the current minimal scope, the truthful guarantee is **bounded, ordered, lossless local collection with best-effort existing GM sends**. Failed sends remain timeout/transport-loss behavior; no automatic command replay, since the bundle may already have mutated state. Mock tests can prove exact calls/freeing/order but cannot prove Bluetooth delivery or UI latency.

If the product requires lossless delivery or bounded display-worker stalls, a larger collector alone is insufficient. A separately owned paced outbox must retain records across send failure and owner/UI deletion, expose checked admission, preserve per-request ordering, and define acknowledgment/deduplication or explicit loss reporting. Queue-admission success alone is not end-to-end acknowledgment. Do not add unbounded retry or retain a pointer into a deleted LVGL owner. That is a separate lifecycle/transport design, not required to claim the existing best-effort protocol semantics accurately.

## Required acceptance checks

* Framing:08/88, count0,255, every truncated length/payload, zero-length segment, trailing bytes, all high-bit submode variants; nested bundle and unimplemented15 reject explicitly before preparation under the chosen hardening.
* Preparation: one full prepass; cache-only segments prepared, STATE40 does not allocate; mixed PUT/SHOW sizing; allocation failures leave valid owned state and ordinary capacity responses; no allocations solely from unsupported15/nesting.
* Reply scratch: cache→raster retains; raster→cache replaces; cache→STATE-no-page clears; multiple cache segments return only last scratch; partial handler failure suppresses scratch; positive embedded refusal is not confused with handler failure.
* Present and failure: zero batch presents once; successful raster/cache mix presents once; late failure preserves earlier modeled mutations but no explicit final present; nested unsupported controls do not execute; mode9 and3/6 regressions unchanged.
* Notifications: existing pending tag, tagged SHOW/HIDE/RESET/takeover combinations, repeated equal tags,255 segments, preprepare reap, count width, exact insertion order, response-before-settled even after partial failure. No local drops; no timer callback during dispatch.
* Ownership: collector allocation failure before side effects; every early return/free path; preexisting ordinary tags cannot be overwritten; owner deletion/expiry after dispatch; native JSON failure and send failure mocks; no duplicate release or input retention. Test final cache reply plus large settled batch under bounded heap accounting.
* Actual compiledRV32 service/display gates and source pin checks remain required; visual one-publish behavior needs a separate captured hardware test. This read-only review did not run those tests or operate the device.

## Reviewed source identities

```json
{
  "tests/g2_compat/upstream/patches/zlib_glue.c": "94722d8cace415d9e6edb160e282ea654befca75d6d376499d7aa1c627e3d3f6",
  "tests/g2_compat/upstream/patches/scene.c": "3792ddb1b2b42814d9e77aeabc60cf6ed4b53e05a17cef54d46075cf733d1b5f",
  "tests/g2_compat/upstream/patches/settings_ext.c": "bbf61304a2895a55ed68cc0650b0e2b44af4e3afc3846341804cfbc95764ff74",
  "tests/g2_compat/upstream/patches/message_transport.c": "386ec85a05fbfd21ac370d85f5765d8dd570690a27aa530b6f4f66c8611c86b3",
  "runtime/portable/scene.c": "c394162f5bb3cd3623e5550029aed5edd02d1631e5b0ea3d593c14446605fa03",
  "runtime/portable/scene_cache.inc": "233fa9550cf00d3684291ae8c8c7ee9627ab1a8a96628eee121febef71599d7e",
  "runtime/graphics/graphics.c": "2da70a4d52b9c5ca8091b1f88ce53f2b0fdb7dc648d60f6101993f374d1992af",
  "runtime/graphics/scene_session.c": "c3bcd105514b1112bf0ba2391f7ff47ac1cff14c0cb8faa7b8ee8ef1affa8f6f",
  "runtime/graphics/native.c": "29cc3ec56a6f8bdd03b61d5ae55cbce55a8cddcc4c8844b835bee4890163c899"
}
```
