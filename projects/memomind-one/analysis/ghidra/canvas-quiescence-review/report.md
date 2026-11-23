# Canvas detach/quiescence: bounded native result

**The pinned software indexed4 path supports a source-detach handoff without
waiting for physical scanout.** On the display worker, hide the owned image and
set its source to NULL, then publish ownership only after those calls return.
Existing reads of the image source are synchronous and feed separate LVGL draw
buffers; the flush path copies those buffers into separate scanout slices.
Subsequent ordinary traversal skips hidden objects, and the image no longer holds
the source descriptor. This is a conditional single-owner contract, not a global
LVGL lock or proof that all native callers are serialized.

The remaining native evidence gap is concrete: six recognized callers can invoke
immediate refresh outside the timer entry. Their complete task/reentrant provenance
has not been closed in this narrow pass. Therefore do not promote `hidden==1`,
sourceNULL, a cache-invalidate return, or a single idle snapshot into an unconditional
cross-task quiescence guarantee. No asynchronous reader of the original indexed4
canvas was found in the inspected default path.

No production/device changes or hardware execution occurred. New work consisted
of nine selected function exports and three callsite exports from the existing
app DB using `-readOnly -noanalysis`; no new import or project analysis was run.
All addresses refer to H001Y1.0.3.127, stock app body SHA256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.

## Exact detach behavior

- [`042bd7fa`](../display-adapter/native-image/function-042bd7fa.c) is the image
  source setter. It calls [`042b412e`](../display-adapter/render/function-042b412e.c),
  which returns3 forNULL. On that branch it frees the old source only when its
  old source type is1/2 (owned string/file/symbol representation), not type0
  variable image. It then clears image+0x2c and sets low source-type bits to3.
  Assembly witnesses: `042bd858 sw zero,0x2c(s1)`, `042bd85c ori a5,a5,3`,
  `042bd860 sh a5,0x4e(s1)` in the adjacent `.asm` export.
- Existing CFW descriptors are type0: the setter stores their pointer without
  copying descriptor or pixels. Detaching this exact type does not free the
  worker's descriptor, palette or raster. It does not zero width/height; therefore
  hide as well to avoid the image's no-source warning/placeholder draw behavior.
- [`042cde58(obj,1)`](../input-adapter/function-042cde58.c) invalidates the old
  region and sets bit1-at-value1 in object+0x24. It does not wait for readers or
  acquire a cross-task drawing mutex. Its ordinary layout/invalidation effects
  must still run on the display task.
- New [`042cba00`](endpoints/function-042cba00.c) tests that flag before drawing
  an object. At `042cba26` it calls `042cd9cc(obj,1)`; `042cba2a` branches directly
  to return on true. [`042cd9cc`](endpoints/function-042cd9cc.c) is exactly the
  masked flag comparison. The occlusion search
  [`042cb856`](native/function-042cb856.c) also rejects hidden objects before
  traversing their children. Hiding prevents later ordinary traversal from
  starting a read; it does not stop a read already executing on another task.
- [`042b68c8`](../display-adapter/completion/function-042b68c8.asm), currently
  named `cache_invalidate` in the CFW adapter, is a twelve-byte prologue/epilogue
  with no side effects. **It is not a fence, reader drain or decoder cleanup.**

Prefer detach over changing `descriptor.data` toNULL: the latter changes the
borrowed descriptor while LVGL still holds it, and is not the native setter's
ownership transition. No direct raw writes to native image fields are needed.

## Why pending scanout does not borrow this canvas

The chain for the existing untransformed indexed4 source is:

1. [`042bd9f2`](../display-adapter/render/function-042bd9f2.c), native image event
   handler, invokes `042b4172` with image+0x2c as source during draw event0x15.
2. [`042b4172`](../display-adapter/render/function-042b4172.c) opens the decoder,
   loops over clipped rows, calls read-line synchronously and passes a temporary
   row to the draw backend. It releases the row and invokes decoder close before
   returning. Error/clip paths also close; this is not a deferred job submission.
3. [`042b5dda`](../display-adapter/render/function-042b5dda.c), cf9 read-line,
   reads packed pixels from `decoder.source->data +64 +row*300`, expands into
   the supplied row buffer and returns. It does not enqueue the original source.
4. [`042cfeea`](native/function-042cfeea.c) installs `042bd374` as drawing-context
   initializer. [`042bd374`](../display-adapter/render/function-042bd374.c)
   installs software image callback042b77ce and blend042b8b58. Their inspected
   row/scratch paths are synchronous; see
   [existing indexed4 audit](../display-adapter/render/report.md).
5. [`042abd06`](../display-adapter/render/function-042abd06.c) supplies primary
   draw memory020162b0/60000bytes and secondary02024d10/36000bytes, installs
   primary flush042abb04 and secondary042aba28. Those are distinct from the
   owned105000-byte indexed4 canvas and palette allocation.
6. New [`042abb04`](native/function-042abb04.c) and
   [`042aba28`](native/function-042aba28.c) call
   [`042ab728`](endpoints/function-042ab728.c). It synchronously reads their
   supplied draw buffer and converts/copies into pixels from0425f7fa, advancing
   the destination by320bytes per scanout row. Subsequent submission passes
   scanout rectangle/mask state, not the original image descriptor/canvas.
7. Both flush functions call [`042d0246`](endpoints/function-042d0246.c), which
   clears the draw-buffer flushing flags at(driver+0x18)+0x10/+0x14.

Actual panel-transfer completion can remain pending after this point, but its
source belongs to the copied scanout pipeline. Reusing a detached *image source*
does not require taking its raw slice semaphore or waiting for panel completion.
This conclusion excludes changed drivers, custom decoder/backend callbacks,
source sharing with another image/display background, and alternate formats.

Decoder lifetime has one subtlety: `042b6832` uses global decoder state02058e18.
[`042b66ca`](../display-adapter/render/function-042b66ca.c) closes it and
[`042b5d8a`](../display-adapter/render/function-042b5d8a.c) frees palette/state and
zeros decoder+0x24. The variable source pointer at decoder+4 may remain stale
after close. Pointer equality alone therefore does **not** mean an active reader;
an instrumentation design must track actual open/read/draw lifetime.

## Scheduling and deletion boundary

The main display loop [`0425bd9e`](../display-adapter/deeper/function-0425bd9e.c)
executes the queue dispatch gate at0425c00a/0425c00e before processing timers.
[`timer-callers.txt`](timer-callers.txt) finds one recognized direct call to
timer handler042b288c at0425bfbe. The timer handler calls callbacks inline and
uses02011eb1 as a recursion/busy byte; that byte is not a demonstrated mutex
against preemptive unrelated tasks. Default display initialization installs
refresh042cc63c as a timer callback.

There is also immediate-refresh entry042ccc20, which can call042cc63c directly.
[`immediate-refresh-callers.txt`](immediate-refresh-callers.txt) records six
recognized caller functions:042821fa,0428227a,04291670,042957c6,0429b384,0429b476.
This pass did not close all their upstream task paths, or rule out indirect
refresh calls. Do not claim the timer's single recognized caller alone proves
every refresh is display-task-only.

Native delete042cf61c→042cf4de sends DELETE0x21 **before** recursive destruction
and class teardown. The stock SDK and current CFW use that callback to release
source resources on the serialized display task. This is a useful stock lifetime
witness, but the start of DELETE is not an independently callable cross-task
fence. The current CFW callback frees pixels/core, so it cannot be reused unchanged
for worker-owned buffers. Publish a handoff after the outer detach/delete call
returns; on deletion retain worker ownership until the full serialized view
destruction has completed. Do not let a callback free the owner and then read it
to publish an acknowledgement.

## Conditional safe sequence for the new profile

The narrow implementation may use these facts only with explicit invariants:

1. Descriptor/data are private to one CFW image, with native indexed4/default
   software backend pinned. No other image, background, decoder or task receives
   them. The existing scene timer is disabled/replaced so it cannot mutate pixels
   or dispose the worker context concurrently.
2. A normal display-queue action hides the view and calls source setterNULL.
   After return it publishes a generation-tagged worker grant using the reviewed
   short critical publication mechanism. It does not wait or render in critical.
3. The normal worker owns the stable SRAM allocation, not an LVGL owner pointer.
   It acts only after that exact grant, and performs no LVGL/native glyph-cache
   operations. Flash read/write blocking still follows its separate contract.
4. After rendering, the worker stops all mutation before publishing FRAME_READY.
   The display action checks generation/lease and shadow validity, reattaches
   the stable descriptor while still hidden, then unhides through a separately
   pinned native API. No exact unhide entry was admitted by this pass.
5. A stale/missing queue action is not a grant. New screen/DELETE cannot free the
   backing allocation or permit a second worker. Firmware/profile reset starts
   a new epoch, not reuse of a previous native pointer.

These invariants make the observed path logically sufficient; an unproven
concurrent immediate refresh that was already reading the source would violate
them. That specific remaining provenance/reader-depth gap should be resolved
before admitting the normal-worker mutation path.

## Minimum observation if static caller closure is insufficient

A pure read-only snapshot command cannot prove quiescence: an observed zero
reader count or hidden/sourceNULL state says nothing about a future reader, and
the existing firmware has no exposed source-specific reader count/fence.

The smallest useful **observational** profile would add bounded counters around
the exact source-reader interval, with no pixel, flash, display-control or driver
mutations of its own:

- Wrap042b4172 entry/return for one fixed owned descriptor (source is its fourth
  argument); count active/max readers and any read while the CFW handoff state
  says WORKER_OWNED. Cover all return paths via a reviewed wrapper, not a sample
  at one instruction. Record current execution-context identity only through a
  separately verified getter, or classify known call origins; do not guess a TCB.
- At the existing display gate record a fixed small snapshot: generation, source
  attached/NULL, hidden boolean, reader depth, refresh generation, and any
  violation count. Report categories/counters, not arbitrary RAM/pointers.
- Optionally count decoder read042b5dda and classify flush source as the two
  known draw buffers versus the owned canvas. The latter should never occur.
  No synchronous logging, allocation, Bluetooth send, waiting or large copy
  inside reader/refresh instrumentation. Saturate counters and fail closed on
  mismatched entry/exit; export copied scalar snapshots later.
- Observe normal refreshes, user-driven hide/delete/screen transitions and
  ordinary normal-task scheduling while the canvas remains immutable. Then a
  separately reviewed handoff exercise can acknowledge detach but leave the
  worker read-only, verifying depth stays zero until reattach. Mutation is not
  needed to test the exclusion protocol. Existing plain immutable observations
  alone cannot test a handoff that has not been implemented.

Such instrumentation would require a separately built/validated observation
profile (or an already available debugger trace); it is not present on the device
and was not installed here. Successful observations establish the exercised
paths, not universal absence of unknown readers. In parallel, a bounded static
closure of the six immediate-refresh caller chains can eliminate the known gap
without installing instrumentation. Neither route requires arbitrary RAM access,
raw slice waits, suppressing stock locks, or scanning panel DMA completion.
