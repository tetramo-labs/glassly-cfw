# Mode 9 rectangle-copy contract review

Read-only review of pinned G2 commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`, against the installed mode3/6 adapter's source boundary. No firmware, implementation, tests or device changes. Paths under `upstream/` below mean `tests/g2_compat/upstream/`. This is source evidence and an acceptance plan, not a hardware or completed implementation claim.

## Exact wire and pixel behavior

`upstream/patches/zlib_glue.c:406–427,641–662` and `upstream/patches/draw.c:163–200` establish:

* Ordinary command: `[09][source x,y,w,h:u16LE][destination x,y,w,h:u16LE]`, at least17 bytes. Coordinates are unsigned full16-bit values, not the scaled bytes used by mode3 and not signed shape coordinates. Width/height must be nonzero and identical between source and destination. Both rectangles must be completely inside the raster; **there is no clipping**. Exact right/bottom-edge equality is accepted. Casts to32-bit occur before sums; `65535+65535` must not wrap to16 bits.
* High-bit command: `[89][left pair:16B][right pair:16B]`, at least33 bytes. `FW_SIDE()==2` chooses the first pair; all other values choose the second. Only the chosen pair is validated or used. The unchosen pair may be out of bounds, empty or dimension-mismatched without affecting this lens. Unlike mode3's two-box variant, mode9 does **not** compare dimensions between the two lens pairs. A33-byte minimum is still required even if only the first pair is selected.
* The high bit is the only flag. Original dispatch masks `mode&0x7f`; both09 and89 select mode9. No options byte, color, frame ID, scene ID or compression is carried by the copy command.
* Both forms accept arbitrary trailing bytes. There is no `srclen == required` check. This is a minimum-length wire contract; a canonical sender should emit exactly17/33 bytes, but changing native acceptance to exact length would be a compatibility change.
* Source pixels remain intact except where the destination overlaps them. Pixels in the destination are replaced by the corresponding **pre-copy** source values. Source equals destination is an accepted no-op but still performs raster takeover and requests presentation. This operation does not clear the source region or slide the complete canvas automatically.
* GRAY4 uses high nibble for even x/left pixel, low nibble for odd x/right pixel. Whole-byte path requires source x, destination x and width all even; each row uses `memmove`, with bottom-up row order when destination y exceeds source y. Otherwise a per-pixel path copies bottom-up under the same condition and right-to-left when destination x exceeds source x. Reverse directions are chosen even for disjoint rectangles; that is harmless.
* Bytes/nibbles outside the destination rectangle must remain unchanged, including a shared boundary nibble, the unused final nibble on odd raster widths, row padding and allocation sentinels. Original dispatcher uses tight `(width+1)/2` stride. The portable public raster can have a larger validated stride and must use that stride, without copying padding.
* On valid copy, dirty accounting adds only the destination rectangle. Top-level `present=1` then publishes the complete shadow through existing presentation; `present=0` changes pixels/dirty state without publishing. `rl_add` records a hint rather than proving a partial physical panel refresh.

Memo's existing high-bit mode3 policy selects the first/left box. The planned mode9 first/left pair policy is consistent and should be advertised explicitly. It is a single-display compatibility choice, not two-lens support. Rejecting malformed unused second-pair fields would differ from original first-lens behavior and is unnecessary for memory safety if the complete33-byte input is present.

## Scene takeover and ordering

Original raster entry calls `cfw_scene_takeover` **before** mode9 length/dimension/bounds checks. Consequently even a short or rejected mode9 request can stop a running scene. This is an upstream side effect, not a desired safety invariant.

`upstream/patches/scene.c:294–306,722–730,845–858` defines takeover precisely:

1. Stop the scene timer and clear `anim_active`. `render_due` is not cleared by this function; Memo’s synchronous display callback drains it when presenting a deferred scene frame.
2. Advance each active object's tween and rotation to the current clock, then freeze it; clear its ACTIVE flag.
3. Clear `active_count` and `last_show_valid`; objects/assets remain cached and become evictable. Do not delete the cache, reset its epoch, blank the canvas or finish all tweens at their endpoints.
4. Emit a pending settled notification once. Timer stop does not itself destroy the timer.

`cfw_scene_resync_shadow` at `scene.c:678` is explicitly a no-op in this pin because retained scene framebuffer aliases the persistent shadow. The old dispatcher comment does not imply an extra canvas allocation or actual resync copy. Freezing object metadata at current time does not rerender it: mode9 copies the existing raster pixels, potentially from the last rendered animation tick, not a new future frame reconstructed from those frozen values.

Current Memo mode3/6 session (`runtime/graphics/scene_session.c:93–121`) intentionally validates complete syntax, target and aliases before takeover. The same policy for mode9 is reasonable **explicit hardening**: a malformed command neither mutates pixels nor freezes the animation. This must be documented as a difference from G2 and tested at the session level, not silently claimed byte-for-byte side-effect parity.

All successful copy/takeover/present operations belong on the existing serialized display worker. No flash worker, new LVGL entry point, global scratch buffer, heap allocation or new native lock is needed. Existing request lifetime must keep the command immutable through validation and copy. If an API accepts arbitrary caller pointers, preserve rejection of input/raster/session/context aliasing before any state mutation. `runtime/graphics/graphics.c:130–176,323–329` buffers settled notifications and flushes after the correlated request response; mode9 should preserve that ordering.

## Minimum meaningful acceptance matrix

These are proposed tests, not new execution results. An independent expected image should snapshot the complete source raster **before** the operation, then assign destination pixels from that snapshot. Comparing only to the new copy loop would duplicate its mistakes.

| Boundary | Required cases and observations |
|---|---|
|Wire|Canonical17B09 and33B89; truncate at every earlier byte; accept extra trailing bytes; reject wrong modes; unsigned65535 coordinates/dimensions reject without arithmetic wrap. Swift emits exact LE16 and rejects negative/out-of-range host integers before narrowing.|
|Bounds|Zero width/height; source/destination dimension mismatch; each left/top/right/bottom overflow separately; exact last-pixel/last-row edges; 1×1 and whole canvas identity. No target bytes or session state change on rejection under Memo hardening.|
|Overlap|Left/right/up/down, all diagonal directions, identical rectangles, disjoint rectangles, one-pixel shifts and maximum overlap. Test even/even/even fast path separately from every source-x/destination-x/width parity combination.|
|Padding|Odd raster width, padded stride, poison neighboring nibbles and prefix/suffix canaries; verify untouched regions and all row padding. Use nonuniform deterministic source patterns that differ between adjacent rows/columns.|
|Lens policy|First pair valid + second invalid still succeeds for first-left policy; first invalid + second valid rejects; differing valid pairs copy onlyfirst;32B89 rejects; trailing bytes accepted. No same-size constraint across lens pairs.|
|Session|Active tween + valid copy stops timer, clears active flags/list, preserves cache/assets/epoch, invalidates last SHOW, emits settled once and preserves unrelated pixels. Pumping afterward must not redraw the old scene. A new SHOW may reactivate retained objects. Malformed copy preserves animation/timer/active-list/pixels and does not settle.|
|Presentation|One successful top-level copy invokes one present; invalid copy none. Identity copy still takes ownership/presents. Source pixels outside destination are unchanged; copying itself does not cause extra framebuffer allocation.|
|Native integration|Actual compiled RV32 service/display path: command admission/capability, bounded request queue copy, correlated success/error, response-before-settled, owner UI/lease denial, first-owner allocation failure, cleanup/expiry, no stock gate/register regression. Existing mode3/6 and retained fixtures remain unchanged.|
|Physical smoke|Seed checkerboard/asymmetric markers with installed mode6/3; copy an odd-x overlap region and an edge-disjoint marker, visibly confirm source/destination and preserved border; verify subsequent delta updates and clear. ACK alone is not visual proof.|

The pinned `patches/host/` corpus contains no direct `rect_copy_4bpp` or `image_dispatch` call/test match in this bounded search. `demos/vector-protocol.test.ts`'s `rotate(...)[9,...]` is a **retained-scene operation9**, not image mode9. Do not count that test or mode36 shape type9 (filled quad) as rectangle-copy coverage. Existing RLE/retained-scene passes provide regressions but do not substitute for the above copy cases.

## Future mode 8 interactions

`upstream/patches/zlib_glue.c:613–639` provides `[08][count:u8][lenLE16][submessage]...`. `88` also works after mode masking. Count0 is accepted and still calls final presentation; trailing bytes after the counted segments are ignored. Segment length must be at least1 and wholly inside input. Nested08/88 and control modes5/7/10/11/16/17 are rejected. The actual allowed set is3,6,9,15,19,20,36,**37–41**; the older comment that names only37/38 is incomplete.

Each subcommand is dispatched sequentially with `present=0`, then one final `present_shadow`. This guarantees one publication for a wholly successful batch, **not transactional rollback**: an earlier copy/cache command can mutate memory before a later segment fails; failure suppresses the final present but leaves prior changes. Metadata/timer/settled sideeffects are likewise not rolled back automatically. Mode9 within a bundle retains its takeover behavior; a preceding SHOW can render a scene into shadow, mode9 then freezes/copies it, while a later SHOW can overwrite the copied raster again. Input order is meaningful.

Do not implement mode8 by repeatedly calling today's top-level `mm_scene_session_dispatch`: that would present intermediate frames. It also resets/replaces the single cache_reply buffer, while graphicsowner's `settled_tags[4]` assumes an unbundled command can produce at most two events. A255-segment bundle could overflow that assumption or lose earlier cache responses. Future work needs an explicit deferred-present API, bounded response/settled collection or streaming policy, cache-prepare allocation strategy and failure semantics. Mode9 itself needs no such new queue now, but its low-level draw primitive should remain separable from presentation to avoid a rewrite.

## Integration risk conclusion

No new native-memory or device-interface question is needed for bounded mode9 over the current owned GRAY4 raster. Main risks are semantic: nibble preservation/overlap order, accidental clipping, wrong high-bit tuple offsets, validating both lenses instead of selected one, integer narrowing on host, and clearing/freeing a retained scene instead of freezing its active objects. Follow the already established validation-first Memo policy explicitly, keep original trailing acceptance, and ensure feature advertisement reflects the optional build flag rather than claiming every profile supports mode9.

## Reviewed source identities

```json
{
  "tests/g2_compat/upstream/patches/zlib_glue.c": "94722d8cace415d9e6edb160e282ea654befca75d6d376499d7aa1c627e3d3f6",
  "tests/g2_compat/upstream/patches/draw.c": "3837f975ccfac23481ba2be3811a94c7e091361672b53ad2108f7794e9ea1e07",
  "tests/g2_compat/upstream/patches/scene.c": "3792ddb1b2b42814d9e77aeabc60cf6ed4b53e05a17cef54d46075cf733d1b5f",
  "runtime/portable/raster_commands.c": "c7d9f8cf72b3a92a0d8b51626a6208093535ae8b6ecc5ec8c76ab90fcaccac7e",
  "runtime/graphics/scene_session.c": "f1463d62b37711227e38978adc15833a7e7cfb2019f8c0c992f2304b432ad81c",
  "runtime/graphics/graphics.c": "2da70a4d52b9c5ca8091b1f88ce53f2b0fdb7dc648d60f6101993f374d1992af"
}
```

## Bounded implementation review addendum

After the contract review, the implementing agent added `runtime/portable/rect_copy_commands.c/.h` and the optional `MM_RECT_COPY` branch in `scene_session.c`. Read-only inspection found no concrete blocker in that version: widened16-bit decoding, subtraction-based bounds, minimum17/33-byte lengths, first-left selection, ignored trailing bytes, alias rejection, directional byte/nibble copying and validation-before-takeover agree with the documented Memo policy. The implementation allocates no scratch memory. This inspection does not substitute for its host, compiled RV32 or device tests, and is not a review of later changes.

Addendum source hashes:

```json
{
  "runtime/portable/rect_copy_commands.c": "effeceea0b14098844ac1352a596f6e2f6a75ddf04a7a64208bbcc9e799d0e2a",
  "runtime/portable/rect_copy_commands.h": "6ef6103b490f1294df4570b23088ba3b2d1420cff6e79f237859ee6f0e37d070",
  "runtime/graphics/scene_session.c": "f1463d62b37711227e38978adc15833a7e7cfb2019f8c0c992f2304b432ad81c"
}
```
