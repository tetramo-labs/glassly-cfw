# Display and scene command gap review

2026-11-01. Read-only source review; no runtime, test, image, or device changes. Baseline is the pinned G2 commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce` in `tests/g2_compat/UPSTREAM.json`. All G2 paths below are relative to `tests/g2_compat/upstream/`. Bluetooth keyboard is outside this parity plan.

## Conclusion and recommended next implementation

Implement the missing raster dispatcher around the existing RAM scene and portable RLE codec: modes **6, 3, 9, then 8**. This enables the original keyframe/delta video and copy-plus-delta scroll behaviors without requiring a flash asset store or new stock display API. Add **15** using the existing resource-font callback, but cover the original 255-byte immediate-string limit rather than silently calling the current 128-byte adapter complete. Existing retained scene opcodes 37–41 are already implemented; their native admission, capacity and lifecycle limitations are separate gaps.

The immediate implementation can reuse the current 600×350 packed GRAY4 owner buffer (105000 bytes), current serialized display callback and presentation hook. It must preserve scene-to-raster takeover semantics, define one-lens handling explicitly, and validate complete messages before writes where possible. This recommendation does not claim arbitrary 65535-byte ingress, 256KiB asset storage, display ownership parity, physical frame rate, or hardware validation.

## Exact command map

| Mode | Original semantics and source | Current Memo status |
|---|---|---|
| 3 | Bounding-box RLE delta: `[3][left/4][top/2][width/4][height/2][fidLE16][RLE]`. The whole box must be in bounds; frame ID is diagnostic only. High-bit variant has left/right boxes and shared RLE, equal box dimensions. `patches/zlib_glue.c:682–739`. | Rejected by `runtime/graphics/graphics.c:38–44`; absent in `runtime/graphics/scene_session.c:93–117`. Bounded decoder already exists in `runtime/portable/rle.c/.h`. |
| 6 | Full headerless packed-4bpp RLE frame; seeds persistent shadow for later deltas. Exact geometry comes from display, not payload. `patches/zlib_glue.c:667–680`. | Rejected/absent in same two dispatchers. No extra full framebuffer is inherently needed. |
| 9 | Rect copy `[9][srcL,T,W,H:u16][dstL,T,W,H:u16]`, same positive dimensions, both in bounds, overlapping 2D memmove semantics; odd x/width must preserve neighboring nibbles. High-bit variant carries two rect sets. `patches/zlib_glue.c:641–661`; implementation `patches/draw.c:163–200`. | Rejected/absent. No portable rect-copy equivalent found. Pure RAM operation, no allocator/stock helper needed. |
| 8 | `[8][count:u8][lenLE16][submessage]...`; no nested bundles; admitted submodes 3/6/9/15/19/20/36/37–41. Submessages use `present=0`; one final present. `patches/zlib_glue.c:613–639`. | Rejected/absent. `runtime/portable/scene_cache.inc:423–435` already prepares embedded cache operations, but this is not a bundle executor. |
| 15 | Builtin UTF-8 text `[15][xLE16][yLE16][options][byteLen:u8][text]`; signed positions, strict UTF8, bytes1–31 are x adjustments -10..20, kerning uses next real glyph, up to255 bytes. `patches/texture_cache.c:389–480`. | Rejected/absent as top-level command. `runtime/graphics/native_text.c:88–145` provides native glyph rendering for retained/shape text but caps128 bytes (`native_text.h:8`); Memo resource fonts and formats intentionally differ from G2. |
| 19/20 | Immediate cached image/cached-font text. `patches/zlib_glue.c:588–605`, `patches/scene.c:1886/1894`. | Present through `scene_session.c:105` and `scene_cache.inc:2062–2084`; limited by actual RAM asset availability. |
| 36 | Immediate shapes, including geometry, cached assets, text and paths. `patches/shapes.h:49–67`, `patches/zlib_glue.c:588–605`. | Present. Native scene build uses full portable shape enum1–18; non-scene build only advertises1–13. Empty `[36,0]` is intercepted as lease renewal in `graphics.c:280`, unlike original raster takeover. |
| 37 | PUT asset chunks/objects, version replacement, same-version reassertion, per-message transaction. | Implemented: `scene_cache.inc:2004` dispatches `cfw_cache_put`. |
| 38 | SHOW active order + flags and visibility/move/glide/tween/freeze/finish/rotate operations; repeated request handling; missing assets refusal. | Implemented: `scene_cache.inc:2005`; op handlers near1474–1561. |
| 39 | HIDE, optional present/tag; freeze and empty active list while retaining cached objects. | Implemented: `scene_cache.inc:2006`. |
| 40 | STATE revision/page query, unchanged/delta/snapshot responses, queries do not touch recency. | Implemented: `scene_cache.inc:2007`. |
| 41 | CONTROL reset/drop-inactive/animation-period10..250ms. | Implemented: `scene_cache.inc:2008`. |
| 11 | Full custom-session cleanup; original permits reserved extra bytes. `patches/zlib_glue.c:577–583`. | Native requires exactly1byte and deletes only current graphics owner (`graphics.c:41,274`). Other independent adapters have their own lifecycle. Do not equate this to whole-G2-session cleanup. |

Modes5/7/10/16/17 (sound, diagnostics, compass, ALS, ring battery) are assigned to the separate control-command review.

## Important implementation distinctions

* G2 masks `src[0]&0x7f` globally (`zlib_glue.c:412`); current native admission uses exact bytes. The high bit is ignored by most original modes but selects per-eye boxes/rects for3/9. A single Memo display cannot truthfully implement two independent lenses. Choose and advertise a deterministic supported lens policy rather than dropping the flag unnoticed.
* Bundle presentation atomicity is **not** full transaction rollback: the original executor dispatches sequentially and can return after earlier submessages changed the shadow/cache. It also tolerates trailing bytes after its counted segments. Preserve or explicitly document validation hardening; do not describe the original as all-or-nothing message rollback. PUT/SHOW have their own transaction semantics.
* Existing scene session immediately presents every19/20/36 operation. A bundle executor needs a `present` parameter all the way through, plus a single final presentation and ordered reply/settled handling. Merely looping `mm_scene_session_dispatch` would present intermediate frames and lose all but the last cache reply.
* Original raster entry takes over/freeze-hides the retained scene before drawing and resynchronizes stale shadow except full keyframe (`zlib_glue.c:415–427`). Current scene session takes over after successful immediate drawing. Define/test ordering for invalid raster requests, existing animation and bundle mixing.
* `mm_rle_decode` prevalidates complete input and rejects overlap before writing; this is appropriate for preventing partial malformed-frame writes. Its surface includes rowbytes/rows/stride, so a delta can target the proper subrectangle without a temporary full-frame allocation.
* Native fonts are not G2 pixels: existing Memo callback only accepts proved mapped default/large/emoji font resources and1/2bpp. Increasing immediate text length to255 should use bounded owned scratch (1020 bytes of tokens) or a demonstrated stack budget; do not silently put it on the display task stack. Retained inline128-byte semantics need not change.

## Remaining native limits, separate from opcode completion

`graphics.h:15` admits8192 bytes; the portable scene limit is65535. Native scene initialization requests64KiB (`graphics.c:145`), although portable RAM/cache/backend tests cover larger capacity. `scene_session.c:90` caps reply payload250 bytes; `graphics.c:147–173` translates replies/settled into JSON, not the original SID0xf0 kind5 envelope. A graphics owner expires after1000 ticks and requires launcher/current-screen ownership (`graphics.c:66–77`, `graphics.h:21`). These are explicit protocol/capacity/lifecycle differences, not missing parser opcodes. Raw keyframes whose encoded size exceeds8192 still need a separately designed ingress path; compression does not guarantee every framebuffer fits.

## Existing evidence to retain and new tests needed

Existing exact source/fixture tests:

* `runtime/portable/tests/test_rle.c` + `g2_rle_reference.c` compare the bounded codec to pinned G2 decoder and upstream TypeScript encoder; runner `runtime/portable/tests/run_tests.py` also cross-compilesRV32. It covers1,048,560 count/color combinations, malformed streams, odd/padded geometry and full600×350 surfaces. This tests codec behavior, not native mode3/6 dispatch.
* Original sender `demos/video-bench.ts:201–260,295–344` emits mode6 keyframes and mode3 deltas. Use its byte generation as the dispatch differential source; `demos/video-test.sh` is a hardware workflow, not an offline passing fixture.
* `patches/host/shapes_host_test.c:936` tests scene dispatch with `present=0`; `:1356–1370` covers bundle preparation only. Neither proves missing mode8 execution works on Memo.
* `runtime/portable/tests/run_scene_tests.py` replays exact `vector-fixture.bin`, `gif-300.bin`, `svg-300.bin` supplied via `--fixtures-from`. These retained-scene fixtures and their original pixel probes remain required regressions; they are not evidence for modes3/6/9/8.
* `runtime/graphics/tests/run_native_text_tests.py` already tests the native text adapter; extend for129..255-byte mode15 payloads, not just existing128-byte shape strings.

New bounded dispatcher tests should compare original semantics and framebuffer results for: full frame→delta→overlap scroll; all copy directions and even/odd nibble boundaries; malformed/truncated/overflow boxes with unchanged target; mixed bundles with exactly one present, no nested bundles, proper cache replies and settled ordering; raster takeover during animation; both high-bit variants under the documented lens policy; text empty/255/control/kerning/invalidUTF8/missingglyph cases. Add actual compiledRV32 handler execution with existing native mocks, allocation/headroom failure, queue ownership and presentation counts. Continue unchanged retained fixtures and public API tests. No tests were rerun for this read-only review, and no new runtime support is claimed.
