# Graphics native interface review

Reviewed `runtime/graphics/native.c`, `graphics.c`, `graphics.h`, and `entry.S`
read-only. Exact reviewed hashes are in [source-snapshot.json](source-snapshot.json).
Root modified the source during review; both findings below were re-read as fixed
in that snapshot. No implementation or device changes were made by this reviewer.

## Findings and status

1. **Fixed:** display gate initially dereferenced envelope byte1 without a NULL
   guard. Current `entry.S` branches NULL to stock dispatcher before reading it,
   preserving the ordinary path's stock assertion behavior.
2. **Fixed:** initial metadata margin check did not preserve margin after the
   105064-byte image allocation. Current `create()` checks free snapshot again
   after image/event/timer creation and requires pixels+65536 before attempting
   pixels. Failure deletes the owned image and its callback releases timer/owner.
   This remains conservative admission policy, not an atomic reservation or
   contiguous-memory guarantee.

No further source ABI/ownership defect was found in this bounded pass. This is
not approval of an older compiled artifact: `graphics-initial-002` still has the
pre-fix gate. `graphics-gates-003` is a stub fixture (three handler bodies are
just ret), not the complete implementation. A final rebuilt binary requires its
own gate/section/relocation/frame review and the parent's host checks.

## Contracts checked

- Native function argument order and pointer width match the pinned profile.
  The request reader requires one node, type1 and little-endian internal u24
  length; portable validation handles geometry lengths/types. Event byte is
  copied before request release. Immediate success stays NULL; queue silent drops
  produce no fabricated success. The display response copies JSON synchronously,
  sends with original event/service15/command0x7d/route1, then frees caller TLVs.
- `try_alloc(size,0)` uses the verified locked lower allocator, while generic free
  is compatible. No global OOM hook is altered. Getters take no arguments and
  report free-total/summed per-pool low-water, not largest contiguous space.
- Native image header uses cf9,600×350; descriptor12B and allocations4-byte
  aligned. Palette integer0xffRRGGBB becomes BGRA8888 in RV32 little-endian;
  all16 entries are opaque grayscale. Pixel data is300-byte tight stride,
 105000 bytes, plus64-byte palette. This is intentionally distinct from native
  scanout stride320. Both borrowed descriptor and pixels live in owned heap.
- `on_delete` returns whether event-add returned its descriptor pointer; the
  callback itself correctly returns void. Stock event dispatcher
  [0x042c766a](function-042c766a.c) invokes it for side effects, not a return
  value. Event user_data offset12, filter0x21 and child event-record search match
  stock layout; [0x042c7604](function-042c7604.c) independently implements the
  same record-index calculation.
- Delete callback clears magic/timer first, deletes timer, invalidates descriptor,
  frees pixels, then owner. Stock image destructor
  [0x042bd790](function-042bd790.c) only frees stored source for filename/symbol
  source types1/2; variable descriptor type0 is not dereferenced/freed afterward.
  This supports freeing descriptor/pixels in the earlier DELETE callback.
- Timer callback calls image deletion and immediately returns; owner and current
  timer may already be freed. Native timer handler checks its deleted flag before
  further access. Same display task serializes create, image update, deletion and
  callbacks; timer creation cannot run its callback concurrently within create.
- Current-screen lookup/launcher gating/20ms periodic expiry yield eventually,
  not atomically on stock UI transitions. An inactive old-screen object may live
  until its timer callback; there is no promise of zero-frame overlap.

## Task stack evidence

[0x04235ea0](function-04235ea0.c) creates main app/BT dispatcher task
[0x0423590c](function-0423590c.c) with0x400 words. Native task creation multiplies
by4, so allocation is4096 bytes, not1024. Default priority6 may be overridden by
native task-name configuration. The worker invokes dispatcher0x04235770, which
uses registered callbacks. Handler0x042dfc8c is registered by0x042db4aa and calls
stream parser0x042e8350, which calls service dispatcher0x042e70a4 and then our
service hook. See [transport handler refs](transport-handler-refs.txt),
[stream callers](stream-callers.txt), [service callers](service-dispatch-callers.txt).

Known frame sizes on this receive path are64+48+192+48+96 bytes before the C
probe. The inspected complete initial build's probe is304 bytes, giving752 bytes
of these frames combined. Native JSON/TLV allocation calls, wrapper frames,
interrupt handling and other branches are not included; no complete worst-case
stack high-water measurement is available. The diagnostic buffer is bounded and
this review found no immediate stack-size contradiction, but allocation4096 is
not equivalent to4096 currently free stack bytes.

## Admission limits retained

The passive probe makes no LVGL objects or large pixel allocation, but producing
JSON still uses stock TLV allocation and may invoke native OOM policy. Drawing
still invokes native image/event/timer/scratch allocations with assertion paths.
Free snapshots and a64KiB policy margin reduce demand; they neither prove
concurrency safety nor reserve future LVGL scratch capacity. Keep these limits
explicit in hardware admission and collect passive heap observations first.

Stale nonfunctional comments: graphics.c says one owned allocation although
owner and pixels are now separate; graphics.h says ticks are deliberately not
milliseconds although the pinned native rate is now proven1ms.
