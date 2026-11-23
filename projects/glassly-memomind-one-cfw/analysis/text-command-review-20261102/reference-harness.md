# Exact G2 reference harness dependencies

`g2_text_reference.inc` is generated unchanged from pinned functions, with file/function hashes in `reference-manifest.json`. The function bodies need no synthetic parser. Build a host-only translation unit around it; never execute original firmware addresses.

Provide standard fixed-width types, `cfw_rectlist` from pinned `patches/debug.h`, a bounded `rl_add` shim, and `cfw_fb_lease_active()` true/false. Define the constants/macros from `texture_cache.c:20–55`, replacing only the four native API/root macros with explicit synthetic callbacks. Rename `bzero` with a preprocessor alias if libc declares its incompatible public signature. Include the exact function fragment after mocks/prototypes.

- `CFW_FONT_GET_DSC(font,dsc,cp,next)` fills a32-byte zeroed descriptor: resolved font nonzero **32-bit marker** at0; u16 advance4/w6/h8; signed16 offsets10/12; format14=0x14; raw flag20. A64-bit host pointer is unnecessary because the source checks only its32-bit nonzero value.
- `CFW_FONT_GET_BITMAP(dsc,draw_buf)` receives a nonnull zero28-byte draw buffer; raw flag bit0 should be set. Return a borrowed synthetic A4 bitmap.
- `CFW_FONT_RELEASE(dsc)` records releases, with no host allocation required. Every obtained bitmap is released once in preflight and once in draw; null bitmap failure also invokes release.
- `CFW_FONT20_ROOT` is a byte array with signed32 height+12 and baseline+16. Memo's analogous mock has native offsets+8/+12, so do not share the same raw struct.

Concrete shared fixture: height4/baseline1, advance3, box3x2, offsets0. Memo2bpp bytes `1b90` give samples `[0,1,2;3,2,1]`; G2 A4 bytes `05a0fa50` give `[0,5,10;15,10,5]`, row stride2. A default-font same-baseline comparison should match pixels across all256 options, clipping, controls, validUTF8 and255-byte text. Add an even-width fixture to exercise G2's full extra pad byte versus Memo's continuous packing. Dirty lists may merge differently after capacity16: compare covered bounds rather than demanding identical rectangle partitioning.

Keep missing-glyph handling and fallback-baseline differences as explicit policy tests. The real source handles missing glyph by advance-only success; Memo resource policy rejects. G2 supports fullA4 coverage while the current native font has only2/1bpp levels. Synthetic tests prove command/control/coverage math for equivalent glyphs, not hardware fonts/repertoire/kerning/lifetime concurrency.
