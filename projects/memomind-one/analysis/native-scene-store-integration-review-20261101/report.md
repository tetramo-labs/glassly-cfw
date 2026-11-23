# Native scene/flash integration boundary

The smallest useful next implementation is a **persistent, registry-owned normal
worker**, binding the existing native adapter and portable COW scene backend,
with an explicit display-buffer handoff. It is not a new flash allocator. Do not
wire the callbacks straight into the current display-owned `scene_session` or
raise its message macro and call the result full capacity. Two concrete blockers
are task/lifetime ownership and the native envelope's 16-bit payload length.

This review made no production, test or device changes. The fixed hardware canary
passing is a prerequisite for the proposed native writes, not evidence that this
new scene lifecycle, every sector, or full-capacity performance has passed.

## Reuse and precise source boundaries

| Boundary | Existing source and required change |
| --- | --- |
| Physical callbacks | Reuse `runtime/graphics/flash_store_native.{c,h}` unchanged for device1 `[0x700000,0x800000)`: 256-byte copied reads/programs, 4096-byte erases, correct alias maintenance and readback. `busy` is reentry protection, not an intertask mutex. |
| COW assets | Reuse `runtime/portable/flash_store.{c,h}`: 256 KiB logical, 1 MiB physical, 320-byte RV32 context plus4096-byte caller scratch, >=129 usable physical sectors. |
| Scene binding | Reuse `scene_flash_store.c:mm_scene_flash_store_bind` and `scene.c:mm_scene_init_with_store`; compile `MM_SCENE_EXTERNAL_STORE`. The current compiler does neither: `scripts/compile_memomind_graphics.py:106` links scene/session/vector/text; only the canary links native flash callbacks. Add a separate explicit full-store profile with the three portable store implementation files. |
| Scene execution | `scene_session.c:mm_scene_session_init` currently calls RAM `mm_scene_init`, and every dispatch/pump/dispose is documented display-worker-only. Introduce a worker-owned adapter; keep the portable scene core's single-owner contract. All reads, writes, transactions, render, tick and release must use that same owner. |
| UI lifetime | `graphics.c:deleted` frees session and pixels; `tick` can trigger deletion at lease expiry/screen change. `initialize_scene` gives the core the same pixels referenced by the LVGL image. Replace this coupling in the new profile: LVGL owns only its view/descriptor/timer; the registry-rooted worker owns core/store/workspace/raster. |
| Ingress | `graphics.c:glassly_graphics_command` copies a complete TLV into a four-byte-header job, releases the TLV, then `P.post` copies it again. Native queue envelope+6 is u16. 65535+4=65539 truncates to3. New ingress must use bounded chunks/record leases, not this raw job path. |
| Publication/reply | `graphics.c:scene_present`, `cache_response`, `flush_settled` currently call LVGL/native reply helpers on the display worker. Keep that execution context; marshal bounded immutable completion data/generation to it. Native `post` can drop despite return0: enqueue does not mean presented or acknowledged. |

The portable backend is already exercised by
`analysis/regression-20261101-05/scene-flash-store/report.json`: full262144-byte
assets,65535-byte input, fixture differentials,528 transaction callback faults,
cached-font/path sector crossings and explicit render failures. Its measured
RV32 cache is43420B, undo base45468B, vector workspace10752B, context1056B.
`runtime/portable/FLASH_STORE.md` contains an older paragraph saying scene pointer
conversion remains required; the actual external asset/reader implementation and
the retained regression supersede that paragraph. **Message-source** pointer
conversion still remains required; these are different boundaries.

## Concrete initialization and ownership

1. On explicit adoption, validate the active owner-disabled/carved image and
   current heap descriptor. Acquire a single validated native badmap record with
   status7/absent provenance kept distinct from a present record. Preserve the
   full96 genuine physical bits; tail adapter gets bitmap bytes64..95 (record
   bytes80..111). A previous allFF backup is not a substitute for this acquisition.
2. Claim a versioned registry state under the short native critical pair before
   allocating/creating a worker. Current `mm_canary_registry` is a40-byte scalar
   once-per-boot record, not an existing persistent scene schema. A new profile
   must explicitly allocate registry fields and arbitrate canary/scene ownership;
   never overwrite a running canary or infer that spare bytes are initialized
   heap. The reviewed256-byte boot carve can hold ownership metadata, not buffers.
3. Try-allocate stable aligned native context, COW context,4096B workspace and
   scene resources. Call `mm_flash_native_init`, `mm_flash_native_callbacks`,
   `mm_flash_store_init` with fixed geometry and mandatory unavailable bitmap,
   then `mm_scene_flash_store_bind`, then `mm_scene_init_with_store`. These steps
   perform no flash I/O. First scene prepare starts an empty logical epoch via
   the backend reset; it does not erase the physical pool.
4. Create one persistent ordinary task using the proved entry-alignment veneer
   and native task ABI, not one task per message/frame. Publish fully initialized
   context ownership before create: the task may run before create returns.
   Treat the native return as success/nonzero only; it is not a durable task
   handle. The task wrapper does not free the worker argument. Keep registry
   state live across screen/phone disconnects until explicit serialized cleanup.
5. Give this worker the only mailbox/queue access to scene/store mutation. Bounded
   ingress copies or record handles become worker-owned only on actual admission.
   No original TLV/envelope, LVGL owner pointer, font bitmap or stack pointer may
   survive its documented owner. Reject additional work when the bounded mailbox
   is occupied; preserve event/epoch/sequence separately from a wrapping8-bit GM
   event. A host timeout does not cancel a native flash wait or authorize reuse.

Native task allocation still has an assertion-producing generic OOM path;
free-byte snapshots do not guarantee a contiguous stack. The8192-byte canary
stack is a starting measured allocation, **not** a verified full-scene call-chain
bound. Preserve gp/tp and handle incoming SP modulo16 both0 and8. Do not hold the
short IRQ critical section across allocation, queue wait, flash/cache operations,
LVGL, logging or sending. Reuse the exact evidence in
`analysis/flash-worker-lifecycle-20261101/report.md` rather than inventing a new
queue/task ABI.

## Smallest display bridge and its admission gaps

Prefer one worker-owned105000-byte raster plus64-byte palette initially, with a
generation-tagged exclusive handoff:

`DISPLAY_BORROWED -> DETACH_REQUESTED -> WORKER_OWNED -> FRAME_READY -> DISPLAY_BORROWED`.

Before any worker render that mutates shared pixels, the display task must hide
or detach its source and invalidate relevant image decoder/cache references,
then publish acknowledgement only after no LVGL reader can use the pixels.
The worker renders only after that acknowledgement. It stops all mutation before
publishing a ready frame. The display worker validates generation, lease and
`shadow_invalid==0`, attaches/shows the frame, then acknowledges the new borrow.
The worker cannot touch it again while borrowed. Display deletion only relinquishes
its borrow; it must not free worker memory. Generation mismatch drops stale
presentation without releasing a newer frame. Queue drop leaves an explicit
pending state; a bounded scalar polling/reconciliation path is needed, not an
unbounded wait in the display task or a manufactured success.

This is the **minimal-memory design proposal**, not an already-proved native
handoff. Existing hidden flag `042cde58(image,1)` is used by input, but hiding
alone is not the proof that all decoder/cache borrowers have quiesced. Exact
source clearing/cache lifetime and unhide calls need a focused witness/test
before admission. A display detach can cause visible gaps during writes/render;
measure and report that behavior. If uninterrupted old-frame presentation is a
requirement, use a separate display-owned snapshot and copy/publish on the display
task; budget an additional105064B instead of pretending single-buffer rendering
is concurrent-safe.

Another explicit blocker: `mm_native_builtin_text` invokes native metrics/bitmap
wrappers `042d153c/042d14be`. The resource-backed path still updates per-font
last-codepoint caches; rejecting dynamic fallback does not make it cross-task
safe. `analysis/ghidra/font-adapter/report.md` establishes the display task as the
serialized context. Do not move these calls to the new worker implicitly. Resolve
them with a separate bounded display-side glyph preparation/copy interface or
prove/cache-isolate the native implementation before advertising builtinText in
the new full-store profile. A temporary cached-assets/geometry-only smoke profile
is useful but must not be called full drawing parity.

## 65535-byte ingress and actual memory constraint

Keep full capacities as the target. A large raw GM TLV is structurally accepted
by the native parser, but it creates large native allocations before our handler
can apply its try-allocation policy. Raising the limit therefore neither fixes
envelope truncation nor proves native OOM safety.

The existing `analysis/full-ingress-review/report.md` is the relevant concrete
next implementation: bounded outer packets, explicit spool roles, sealed record
readers, then reader-based scene dispatch with stable reassert offsets. The current
portable scene accepts a contiguous message pointer; `mm_scene_bytes` solves asset
reads, not command ingress. Add a RAM-reader wrapper to preserve current fixtures
and a flash-reader implementation for the same parser. Avoid introducing a second
independent scene parser. Keep max wire/decoded length65535 and the overflow
observation/rejection at65536. Portable transport still has two origin histories;
host zlib evidence does not establish a native inflater binding.

A lower-bound illustration with current RAM undo is284339B:105064 canvas,
43420 cache,45468 undo,10752 vector workspace,4416 COW state/scratch,300 native
adapter,1056 scene context,65535 record,8192 task stack,124 TCB,12 wrapper.
Adding the existing48KiB reserve gives333491B, only585B below the historical
334076-byte idle sample, before allocator headers, queue/context/job/reply/LVGL
costs. Two full inflater contexts add79888B. This is not hardware admission.

Thus the full-capacity path should not grow a65535B RAM record and double canvas
under the old170KiB session policy. Implement spool/readers and measure a new
whole-owner budget. The stronger metadata-authority approach in the ingress
review is needed if moving45468B RAM undo to flash: a fallible restore read cannot
be called infallible rollback. Keep active immutable metadata and active asset
map authoritative until a joint no-I/O publication; abort discards staged state.
Do not silently shrink capacities or drop a history to meet the budget.

The old ingress plan packs spools inside the1MiB tail. Full3MiB exclusive adoption
allows separately owned spools in `[0x500000,0x700000)`, simplifying competition
with the existing COW pool. However the current native adapter **must reject**
that range. A distinct bounded spool binding/geometry and real96-byte-map slicing
review is required; do not loosen its tail bound globally. No fake native badmap
bits or KV saver calls are required. Partition ownership and unusable sectors are
separate maps. All stores sharing device1 use the same worker and mutation policy.

## Failure, reset and required tests

- COW commit/abort are RAM-map operations. A failed transaction preserves active
  logical assets after abort, but its unused physical sectors may have changed.
  Stop on native error, retain phase/status, never auto-retry or mark bad sectors.
  Real badmap changes invalidate admission; don't reinitialize under active
  readers. Map/config acquisition provenance must be in status/evidence.
- Rendering may partially modify a raster before external-read failure. Never
  publish it while `shadow_invalid`; detach or retain a separate previous frame.
  Do not map `MM_SCENE_STORAGE_IO` to a successful cache reply. Return distinct
  unavailable/failed status and retain authoritative state for explicit recovery.
- Physical data is not a reboot journal. Reset/new boot begins an empty logical
  epoch even when old sectors contain bytes. Never scan stale data into trusted
  descriptors, resume an old spool or report durable commit. Lease/delete only
  changes display ownership; cleanup must be serialized after readers/jobs drain.
- Timers must advance the core on its owner, not concurrently from LVGL. Preserve
  settled/command ordering; queueing a frame is not completion. Flash calls have
  no established cancellation deadline or30fps guarantee; host timeout, UI lease
  and flash completion need independent states.

Required new tests, beyond rerunning existing backend tests:

1. Actual RV32 linked worker+registry+native binding, preserved registers/entry
   alignment, all init failures, task runs-before-create-return, short critical
   boundaries, one-owner admission and no calls on unadopted/map-invalid profile.
2. Deterministic two-task lifecycle model: deletion/expiry/disconnect during
   erase, decode, render and presentation; dropped/duplicate/stale envelopes,
   delayed ACK, generation reuse, cleanup only after reader release. Assert no
   LVGL callback touches worker-mutating pixels and no callback retains freed
   owner/TLV/envelope/record memory.
3. Full65535 command across every parser/header/page boundary;65536 rejection;
   bounded native packets/envelope sizes; both origins/sequence wrap/history;
   no full-record native TLV copies in the new path; native heap/stack high-water.
4. Existing unchanged G2 fixture/assertion suite against RAM and new source reader,
   full256KiB assets, cross-sector fonts/images/paths, repeated staged replacement,
   >=129 usable COW sectors, scattered bad maps and genuine-map immutability.
5. Inject failures at every native callback and metadata/record read/seal/commit
   boundary. Verify old authoritative metadata+asset map unchanged, no invalid
   frame publication, coherent failure reply, exact once-only buffer release,
   and explicit empty-epoch reset. Include a second failure during recovery.
6. After the fixed canary and offline gates: measured native small/full writes,
   independent readback, frame/lease behavior, free/largest-available evidence,
   stack high-water, timing and repeated epochs. A single-sector canary cannot
   replace these full-scene acceptance tests.

Recommended implementation order: worker/registry state and display handoff
offline first; native COW bind with small explicit jobs next; bounded spool and
shared reader conversion; metadata authority/full-record tests; then a separately
advertised full-store candidate. Each intermediate capability remains accurately
scoped until its full-capacity native test passes.
