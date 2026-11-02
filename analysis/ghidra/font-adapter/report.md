# Native font adapter evidence — MemoMind 1.0.3.127

A scene `builtin_text` adapter can obtain native metrics and read packed coverage directly into its existing GRAY4 raster. It does not need an LVGL label, drawing context, render scratch buffer, plugin instance, or new glyph allocation on the normal mapped-font path. The native default is 34 logical pixels high, **not the G2 20-pixel font**; this provides native text semantics, not identical font pixels or line layout.

This is static evidence from the validated stock segment-3 body, SHA-256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, mapped at `041eb020`. [profile.json](profile.json) contains byte witnesses, offsets, tables and signatures. No device writes or firmware changes were made. Exported `.c` files are decompiler aids; `.asm` and stock bytes control when recovered signatures disagree.

## Minimal native interface

RV32 integer/pointer calling convention, with the existing `gp`/`tp` preserved:

```c
struct glyph16 {
    const void *resolved_font; // +0
    uint16_t advance;          // +4, pixels, not 1/16 pixels
    uint16_t box_w, box_h;     // +6,+8
    int16_t ofs_x, ofs_y;      // +10,+12
    uint8_t bpp_flags;         // +14: low4 bpp; bit4 placeholder
    uint8_t reserved;         // +15
}; // sizeof16, align4 on target
int glyph_dsc(const void *font, struct glyph16 *out,
              uint32_t codepoint, uint32_t next_codepoint); // 042d153c
const uint8_t *glyph_bitmap(const void *resolved_font,
                            uint32_t codepoint);           // 042d14be
int32_t font_line_height(const void *font);                  // 042996d6
```

Zero the complete descriptor first. Both `font` and `out` must be non-null: null paths log then loop indefinitely. At `042d1662..042d1678`, the wrapper loads `font[0]`, forwards `a0=font,a1=out,a2=codepoint,a3=next_codepoint`, and restores a2/a3 around the callback. Ghidra's three-argument prototype is incomplete. `042d14be` tail-dispatches `font[1]`; use the **resolved** font from the descriptor, not necessarily the root font.

`042d153c` traverses the fallback pointer at font+24. A successful non-placeholder callback records the resolved font. Missing glyphs return false with a synthesized advance (`root line_height/2+2`), zero resolved font, and placeholder dimensions. Preserve this advance and skip bitmap for G2-style missing-glyph handling. Zero-area glyphs, including special spacing/control codepoints, also need no bitmap. Never pass a null resolved font to `glyph_bitmap`.

The SDK table at `04366168` has default-font pointer at +0x58, large-font at +0x5c, line-height function +0x60, text-size +0x64 and next-line +0x68. The latter two are `042b3812` and `042b3448`. Their signatures are in the pinned SDK `GlassSDK/include/gm_plugin_lvgl_api.h:435`; these operate on NUL-terminated text and native wrapping, so they do not directly implement scene's control-byte encoding. The table's font pointers are documented host-owned/immutable. Offsets were compiled for RV32 in `offsets.c/.o`.

| Font | Metrics callback | Bitmap callback | Height / baseline | Coverage / backing |
|---|---|---|---|---|
| default `0438f77c` | `042d1ec6` | `042d1d5e` | 34 / 7 | 2bpp, resource `1001` |
| large `0438f75c` | `042d1a0c` | `042d18a4` | 41 / 9 | 2bpp, resource `1002` |
| common fallback `04385e7c` | `042d05cc` | `042d0472` | 27 / 9 | 1bpp, resource `1003` |
| final fallback `0200fb44` | `0425c492` | `0425c288` | 30 / 1 initially | 1bpp, runtime glyph cache |

Native font object is 32 bytes: callbacks +0/+4, signed32 height +8, signed32 baseline +12, flags +16 (renderer checks low2 for subpixel), fallback +24. Other fields need not be interpreted. The first two fonts both point to `04385e7c`, whose fallback is `0200fb44`, whose initial fallback is null. The last object resides in startup-copied RAM; its values are startup evidence, not proof they remain unchanged live. No 20-pixel built-in root was established in this bounded pass.

## Bitmap packing and placement

Stock renderer `042b9c36` proves the coverage interpretation and placement:

```
gx = text_x + descriptor.ofs_x
gy = text_y + root_font.line_height - resolved_font.baseline
     - descriptor.box_h - descriptor.ofs_y
next_x = text_x + descriptor.advance
```

Notice the **resolved-font baseline** and **root-font line height**. G2's original adapter uses its root baseline; blindly retaining that formula would misalign MemoMind fallback glyphs.

For these fonts the coverage is tightly bit-packed, MSB first, with **no per-row byte alignment**:

```
bit = bpp * (row * box_w + column)
sample = (bitmap[bit >> 3] >> (8 - bpp - (bit & 7))) & ((1 << bpp)-1)
```

For 1bpp expand sample to GRAY4 0 or15. For 2bpp expand to 0,5,10,15. Initial RAM tables at `02011460` and `02011464` contain `[0,255]` and `[0,85,170,255]`; native 4bpp table `043859c0` contains multiples of17. All are witnessed from stock startup-copy bytes, not live RAM. The descriptor's full byte is not an enum: mask its low4 bits. Reject subpixel fonts or unsupported bpp rather than interpreting them as 4bpp.

The native renderer allocates a coverage scratch region up to `min(box_w*box_h,600)` through `042b3ad0`. Calling the glyph APIs and expanding bits directly avoids this renderer allocation. It also avoids LVGL blending state; the scene callback applies its own G2 intensity/transparency/inverse semantics.

## Resource format and ownership

Default/large cmap helpers `042d1c24` / `042d176a` binary-search sorted 32-bit little-endian codepoints. The callbacks ignore next-codepoint; their normal paths use stored advance with no kerning. Resource structure established by callbacks:

- count `N`: u32LE at +12; sorted codepoints at +16, four bytes each;
- glyph records: +16+4*N, nine bytes each;
- record fields: bitmap offset u32LE +0, advance u8 +4, height u8 +5, width u8 +6, ofs_x i8 +7, ofs_y i8 +8;
- bitmap region: +16+4*N+9*N; offsets are relative to this region.

Bitmap byte count usually comes from the next record's offset. The last-record fallback uses `ceil(width/8)*height` even in the 2bpp callback. This is an observed oddity, **not a generally correct 2bpp size calculation**. The callbacks reject derived byte counts above1000. Do not treat that check as a proof of the reader's required byte count for every possible resource record.

`042d13a4(resource_id,offset,length)` resolves a 32-byte directory record using `042d12a0`, then tail-calls `042d0a52(record,offset,length)`. The latter checks requested bounds against the resource and global mapped data area and returns `mapped_data_base + record.offset + offset`, incrementing a read counter. No copy or allocation occurs. Per-font last-codepoint caches replace pointers but do not free resource memory. **Do not free/release these bitmap pointers.** They remain host-owned mapping addresses; do not retain across resource reinitialization/firmware changes.

Lazy initialization `042d127a` calls `042d0c5e` if state byte `0205a048` is zero. Initialization finds partition type `c6`, uses its address+32+XIP alias `04000000`, validates FONT magic `544e4f46`, a 128-byte header, and 32-byte directory records. It copies metadata into static host state. There is no direct allocator in this initializer, but its partition lookup/logging callees were not exhaustively bounded here. For a strict no-cold-initialization callback, a read-only check of the **proved** initialized flag can reject while zero; do not set it or initialize guessed RAM.

The captured OTA's partition metadata declares type `c6`, start `01000000`, allocation4MiB and body_size0. The update contains no c6 body. Thus exact available characters, actual largest glyph, resource content integrity and final-record bitmap size cannot be proved offline from this OTA. Codepoint range checks are eligibility checks, not proof a glyph exists.

## Final fallback cache

`0425c03c(codepoint)` searches existing nodes from `0200fb38`, following node+20. Its returned node is in a0, despite Ghidra's `void` annotation. `0425c492` reads width+4, height+5, advance+6, signed offsets+7/+8; `0425c288` returns the bitmap pointer at node+12. Both call `0425c250`, which uses `0425c05e`/`0425c096` to unlink/relink an existing node at the head. These functions allocate no memory and do not request missing glyphs. They do mutate host cache ordering.

The separate insertion path `0425c2b6` validates dimensions1..50, checks `ceil(width*height/8)` against supplied bytes, and may call `0425c108` to allocate a28-byte node plus bitmap through `042b3a3c`. Eviction `0425c1f2` and reset `0425c4fe` remove/free entries. None of those allocating/evicting operations is called by the lookup/metrics/bitmap path. Initializer `0425c638` changes this font's line height and subpixel flags from its input, so30/1 must not be treated as immutable live geometry.

Unlike mapped resources, this pointer's lifetime ends when its cache entry is evicted/reset. No release operation belongs to the caller. Do not keep cache pointers between scene calls, worker yields or native callbacks that may update the cache. Cross-task cache mutation has not been established safe by this pass. A conservative first adapter can reject descriptors whose resolved font is `0200fb44`, while still allowing normal missing-glyph advance, or restrict all rendered bitmaps to the three proved resource-backed font addresses. This restriction is policy, not a stock limitation.

## Scene callback contract

`runtime/portable/scene.c:80` builds `[x:s16LE,y:s16LE,options:u8,length:u8,text...]` and provides caller-owned token scratch (128 entries). Inline clip bounds are reflected in the passed raster's width/height; preserve its stride/bytes and validate raster geometry. `scene.h` requires prevalidation. The caller currently discards the callback return, so a failure must leave pixels/dirty rectangles unchanged.

Preserve upstream `tests/g2_compat/upstream/patches/texture_cache.c` semantics:

1. Require exact `length == 6 + src[5]`, within scene's128 text bytes and token capacity. Decode all input before native calls or raster writes. NUL, malformed/overlong UTF-8, surrogates and >U+10FFFF reject; raw bytes1..31 are x shifts `byte-11`, not line breaks. Pass the next actual glyph, skipping shift tokens, as `next_codepoint`.
2. Preflight each descriptor and each nonzero bitmap before writing. Reject unsupported coverage/font/subpixel formats or unavailable nonempty bitmaps. Missing glyphs preserve native advance without drawing. Preflight does not make transient cache pointers permanent; prefer mapped-resource-only support until cache ownership is separately admitted.
3. Expand native coverage to 0..15. `top=options&15`; inverse bit0x20 changes source to15-source, then output=`source*top/15` (integer floor). Transparent bit0x10 skips **original zero coverage before inverse**, matching upstream. A top value0 really means zero; it is not a default15 shortcut.
4. Place using the native baseline formula above; advance in pixels; clip signed coordinates to `[0,width)×[0,height)` with wider arithmetic. Write owned packed-GRAY4 pixels and add clipped dirty rectangles. No native LVGL object, task queue or framebuffer ownership change is involved.

The old G2 `CFW_FONT_GET_BITMAP(dsc,draw_buf)` and `CFW_FONT_RELEASE(dsc)` ABI is incompatible. MemoMind's bitmap function takes `(resolved_font,codepoint)` and returns borrowed bits. Do not carry the G2 raw-A4 flag/dummy draw buffer/release calls into this adapter.

## Stack / heap boundaries

Proved frames on the default successful path: descriptor wrapper48B; default metrics callback32B (`042d1ed6`); cmap search48B; resource helper32B; directory lookup16B; mapped-read32B (tail-called after the helper releases its frame); LE word reader16B. The deepest ordinary metrics path through directory lookup is176B excluding the adapter/caller; default bitmap callback48B plus cmap48B+helper32B+lookup16B is144B. Cache lookup has16B frame; callback/list-touch frames are small and no allocation occurs in those lookup functions. This is not a bound on logging, error paths, lazy partition initialization, interrupt use, or external cache mutation.

Normal resource lookup/dereference does not allocate. The adapter can reuse supplied tokens plus one descriptor and a16-byte LUT, avoiding a large per-character stack array. Verify actual compiled callback frame/call chains and failure behavior before hardware admission. Display worker is the established serialized drawing context; do not invoke these mutable font caches from the BT handler. Native fonts/resources may coexist with normal notifications/calls through the parent's existing display ownership gate; the text callback must not bypass that gate.
