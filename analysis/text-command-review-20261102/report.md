# Immediate builtin text (mode15) contract review

Pinned G2 commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. This is a read-only source/native-evidence review, not hardware validation or final candidate admission. No production or firmware edits were made. Reference extraction hashes are in [reference-manifest.json](reference-manifest.json).

## Exact wire and rendering contract

`patches/zlib_glue.c:406–427,588–605` masks the high bit before dispatch. Mode `0f` and `8f` have identical single-text semantics; the high bit does not introduce a second coordinate pair.

```
[mode:u8][x:s16LE][y:s16LE][options:u8][byte_length:u8][text bytes]
```

Require **exactly 7+byte_length bytes**, length0..255. Coordinates are signed despite the source comment saying u16. Empty text is valid with a valid framebuffer lease/root font. Extra bytes are rejected. Text length counts bytes, not Unicode scalars, graphemes or glyphs.

`texture_cache.c:287–315,393–471` decodes the complete string before font calls or pixel changes. NUL is invalid. Bytes1..31 move x by `byte-11`, including LF10→-1 and CR13→+2; there is no newline interpretation. Byte11 is a zero-distance control. DEL127 is a glyph. Other text is strict UTF-8: invalid continuations, truncation, overlong forms, surrogate scalars and values above U+10FFFF reject. The next actual glyph skips intervening control tokens before being passed to metrics for kerning.

Options low4 bits are intensity0..15; 0x10 skips original zero-coverage samples **before** inversion; 0x20 inverts coverage. Output is `floor((inverse ? 15-v : v)*intensity/15)`. Bits0xc0 are ignored. Intensity0 is genuinely zero. Signed placement clips to the target raster; clipping does not modify out-of-bounds pixels, the other nibble or row padding. Controls can move subsequent glyphs back onscreen. G2 placement uses root line height/root baseline; advance is whole pixels.

G2's raw glyph format is aligned A4: high nibble first, row stride `floor(width/2)+1`, including a whole pad byte for even widths. `cfw_builtin_glyph` requires format0x14 for nonempty resolved glyphs, supplies a zero28-byte dummy draw buffer, and releases each successful bitmap after preflight and drawing. A false metrics result, null resolved font or zero-area glyph is accepted without a bitmap; descriptor advance still applies. Wrong nonempty format/bitmap failure rejects. Two passes assume a stable font provider; a provider changing between passes can fail after earlier pixels changed. Do not overstate preflight as a general transaction.

## Ownership, scene and bundle behavior

Upstream `image_dispatch` takes over the scene **before** validating a raster mode, so malformed immediate text can stop animation. Memo's established conservative policy validates/renders synchronously before successful takeover, preserving animation on validation failure. This is an intentional hardening difference, not exact upstream failure timing. Successful empty or fully clipped text still takes over and presents once.

Mode15 does not access cached-string assets. Retained text shape15 and inline shape17 are different encodings, with128-byte limits that must remain unchanged. Immediate mode15 needs up to255 tokens (1020 bytes), which must be budgeted owned temporary heap scratch on Memo, not copied from G2's1020-byte stack array. On failure, release scratch once; no bitmap pointer or request pointer survives the synchronous display task call. Native resources are borrowed; never invoke G2 release APIs on them.

Mode8 admits15/8f as a non-nested segment. Run the existing full-batch prepare exactly once, execute segments in order, present once on full success. Earlier effects survive a later failure; there is no bundle rollback or guaranteed pixel isolation from unrelated refresh of shared LVGL memory. Text leaves final cache reply scratch unchanged, so cache→text retains the last cache reply; later cache dispatch can replace/clear it. Outer failure suppresses cache reply. Scene takeover can settle an existing pending tag; text creates no new settled tag. The existing bounded collector and response-before-settled ordering remain applicable. Current native implementation allocates text scratch per segment, freeing it before the next; the maximum is1020 bytes plus allocator metadata, not255 simultaneous text arrays.

## Native ABI and limits

Reuse [native font evidence](../ghidra/font-adapter/report.md) and its `profile.json`/assembly witnesses. Exact APIs: metrics `042d153c(font,out16,codepoint,next_codepoint)`, bitmap `042d14be(resolved_font,codepoint)`. The16-byte descriptor contains font+0, advance+4, width+6, height+8, signed offsets+10/+12 and bpp/placeholder flags+14. Native bitmap ownership is synchronous borrowed mapping; no caller free/release.

Default `0438f77c` is34/7 height/baseline, large `0438f75c`41/9, common resource fallback `04385e7c`27/9. Default/large2bpp and fallback1bpp are continuous MSB-first samples across rows, without row alignment; expand to0/5/10/15 or0/15. Native renderer `042b9c36` uses **root height and resolved-font baseline**. The final dynamic font `0200fb44` is rejected to avoid retaining evictable bitmap pointers. Metrics lookup can still touch that cache's LRU before rejection; resource-only does not mean no native host-state mutations. Cold resource state `0205a048==0` is rejected. Never initialize guessed RAM or bypass native guards.

Concrete compatibility limits are deliberate: native default size/pixels differ from G2's20px font, known resource callbacks ignore next-codepoint kerning, fallback baseline differs, unavailable/dynamic glyphs reject the whole text rather than G2's advance-only skip. The native adapter rejects unknown fonts, subpixel flags, placeholder flags, unsupported bpp, boxes above255 and calculated bitmaps above1000 bytes. Actual c6 font contents were not in the OTA, so supported Unicode repertoire/largest glyph/final-record resource bounds are not fully proved by the OTA analysis. Do not claim full font pixel parity.

Existing ordinary metrics chain176 bytes and bitmap chain144 bytes exclude adapter/callers, native logging, interrupts and error paths; the earlier adapter frame was144 bytes. Recheck the actual new compiled stack frames, total extension size and owned workspace accounting. All font calls stay on the serialized display worker under existing launcher/lease/owner gates, never the Bluetooth handler. No global scratch or dynamic-cache bitmap retention is required.

## Actual tests and extraction

Original `patches/host/shapes_host_test.c:96–112` renames the real builtin functions, then substitutes a10px-per-byte box painter. Existing shape/retained suites remain valuable regressions but do **not** execute the original builtin renderer/font APIs. `demos/object-cache.ts` shape15 is cached-string text, and its helper strips controls/truncates to128; it is not the immediate mode15 encoder. The extracted reference here covers the actual functions rather than repeating that stub.

Run `python3 analysis/text-command-review-20261102/extract_reference.py` to regenerate the exact12-function include after checking pinned source hashes. This extractor itself does not run fonts/rendering. [reference-harness.md](reference-harness.md) documents the minimal explicit ABI shims for the native agent's differential harness.

Meaningful required coverage:

- Exact lengths0,1,128,129,254,255;256-byte input rejected by encoder; missing/truncated/trailing header/data; highbit0x8f; byte-count versus scalar-count.
- All256 option values against the actual G2 renderer with equivalent synthetic coverage; opaque/transparent/inverse ordering, negative and signed-extreme placement, odd widths, row padding and unchanged adjacent nibbles.
- Every control1..31, controls between multibyte glyphs, all-no-op255-byte input, DEL; strict malformed/overlong/surrogate/out-of-range/truncated UTF8 and NUL.
- Multi-glyph preflight failure leaves pixels and dirty state unchanged for stable callbacks; wrong format/bitmap failure; missing-glyph/dynamic-font/fallback-baseline differences separately asserted rather than forced equal.
- Heap failure before rendering, exact scratch frees, no1020-byte stack array, retained128 limit unchanged, native NULL API selection, ordinary owner destruction and allocation accounting.
- Direct/highbit text, text bundles, text→cache/cache→text, late segment failure, one present, pending settled order, no scratch loss or invented per-segment replies. Empty/offscreen success still takes ownership.

The mode15 Swift implementation observed during review preserves raw bytes and validates via strict Foundation UTF8 without re-encoding; its String overload counts UTF8 bytes. The agent's963-case reference and16 focused tests are separate evidence under `analysis/text-swift-20261102`. No concrete wire-contract blocker was found. Resource-only admission and failure-timing differences must stay explicit in capabilities/docs.
