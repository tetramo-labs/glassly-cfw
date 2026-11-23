# Candidate text integration and smoke-template review

Read-only snapshot hashes: [review-source-pins.json](review-source-pins.json). This review observes a concurrent candidate implementation, not a final frozen ELF or hardware result. No concrete blocker found in the inspected source paths.

## Text integration

`runtime/graphics/scene_session.c:103` admits exact7+count, allocates at most255 u32 tokens through existing session workspace accounting, invokes the checked synchronous callback, frees once, and propagates callback failure. Empty input allocates one token (4 bytes) to preserve a nonnull scratch contract. Allocation failure returns-3 and is mapped to native no-memory. Successful direct text presents once; bundled text leaves presentation to the enclosing bundle. Retained128-byte limits and scratch remain unchanged despite conditional immediate255 maximum. Native callback selection is explicitly NULL→firmware API in graphics.c; the scene owner is not miscast as a glyph API.

The existing source/input aliases are validated by scene dispatch and by native_text. Request/token/pixel pointers are independent owned lifetimes. No glyph pointer is retained after return; no native bitmap release is attempted. The callback preflights every glyph before drawing, subject to the existing stable-resource-provider assumption. A callback changing between two passes is outside that assumption and can produce partial writes; the current mapped-resource path avoids the known evictable dynamic bitmap.

## Why draw-before-takeover does not compose onto stale pixels here

This conclusion is specific to the current serialized display-task RAM scene adapter:

1. `scene_cache.inc:299` obtains `sc->fb` from `mm_scene_shadow`; `scene.c:21` uses the platform shadow callback; `scene_session.c:45` returns the same `s->raster` used by text. `graphics.c:166` constructs it from the owned image palette+64 pixels. There is no second scene framebuffer.
2. `scene_cache.inc:726` is an explicit no-op resync because scene frame aliases shadow. A set shadow_stale flag is not evidence of an unrendered separate surface.
3. Ordinary scene presentation (`cfw_scene_present`,875) clears render_due and renders synchronously into that same framebuffer.
4. The only assignment of render_due=1 is scene_tick at2129. Its immediate present callback reaches `scene_session.c:63`, which calls `mm_scene_render_if_due` before native image_source; this clears/render_due synchronously before the timer pump returns. Native timer registration here only arms fields, and `mm_scene_session_pump` invokes the tick on the same display worker.
5. `cfw_scene_takeover` at895 stops the timer, freezes/deactivates objects, clears active_count/last_show_valid, and reports pending settled. It does not rewrite pixels or request a new frame. Native settled callback only collects tags during dispatch, without a yield or render.

Consequently successful text can draw then stop scene animation without a later queued scene frame overwriting it in this adapter. This preserves malformed-input animation state, unlike G2's takeover-before-validation. It is not a claim that arbitrary reentrant font hooks, a future asynchronous renderer, external-store worker or display-thread detachment is safe. Tests should include retained SHOW/animated tick→text, verify composed background, zero undrained frame and stopped animation, plus malformed text preserving the prior scene state.

## Smoke templates

Reviewed `analysis/text-native-20261102/smoke.swift.in` and `verify-smoke.py`. The maximum string is exactly248 control11 bytes plus7 ASCII bytes; highbit text uses0x8f without extra coordinates; two text segments in mode8 present together; signed-extreme empty text with options255 is valid. The six raw malformed forms test NUL, overlongUTF8, surrogateUTF8, missing payload, trailing payload and short header. They all require invalid, rather than a repaired or silently truncated command. Options31 give full-intensity transparent glyphs over the black background. No native font pixel or character-size equality is asserted.

No retained scene/pending tag is created by this smoke, so an empty expected-settled list is appropriate after a clean new owner. The response filter distinguishes settled JSON from the correlated primary response; unsolicited non-custom services are durably recorded, and unexpected custom messages fail the run. The verifier independently parses byte framing/checksums, reconstructs exact text/bundle/black commands and business correlation, verifies invalid/ok/cleared responses and notification absence. Lease renewal remains a scheduled-presentation acknowledgment, not proof of continuous displayed pixels; the output states this correctly.

Two improvements were sent to root (who owns the templates): require capabilities `textFont=native-resource` and `missingGlyph=reject`, and independently validate exact probe/header/capability sequence and pinned header/capability reply content in the offline verifier. At the reviewed snapshot those checks exist in the live Swift program only (font policy fields are not decoded). Thus the existing verifier alone does not prove which candidate booted. Root is preparing synthetic verifier cases. No hardware actions were performed by this review.

No control-flow or pointer-length blocker was found in the Swift encoder. It preserves raw Data bytes after using Foundation solely as a strict UTF8 validator; its String overload emits that String's UTF8 without truncation. Caller-defined unsupported glyphs can still fail native admission as explicitly documented.
