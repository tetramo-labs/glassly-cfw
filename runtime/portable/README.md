# Portable graphics and retained scene core

`geometry.c` is a synchronous, allocation-free memory renderer for G2 mode36
geometric types1–13. It has no firmware addresses, global writable state, device
transport, presentation, scene cache, fonts or display ownership. The origin is
local to the supplied buffer. See `PROVENANCE.md`, `UPSTREAM.json` and `LICENSE`
for the pinned source and MIT license.

```c
#include "geometry.h"

/* The buffer must actually own at least stride * height bytes. */
mm_raster target = {
    .pixels = owned_pixels,
    .bytes = owned_bytes,
    .width = 600,
    .height = 350,
    .stride = 320
};
int result = mm_geometry_mode36(&target, packet, packet_bytes);
```

Do not substitute width/2 for hardware stride: MemoMind evidence currently shows
600 visible pixels with320-byte rows and175-row synchronization slices. A tight
private600×350 shadow instead has300-byte rows/105,000 bytes. The module supports
both. It does **not** locate or lock a device framebuffer; the caller must supply
an owned/synchronized buffer and serialize all writers. A physical slice has a
local origin; a future display adapter must translate/clip logical coordinates
correctly and present through the proven stock display task. That adapter has
not been implemented here.

## Contract

`mm_geometry_mode36` accepts the complete packet:

```text
[36:u8][count:u8][records...]
record = [type:u8][flags:u8][color:u8][width:u8][p0..p7:signed LE16]
```

Each record is exactly20 bytes. Types1–13 preserve the G2 line, rounded rectangle,
circle, triangle, quad, quadratic/cubic Bézier, arc and pie semantics. Geometric
coordinates clamp to -1024..1023, dimensions to2047, color to its low4 bits;
stroke interpretation and integer sampling match upstream. Immediate record flags
are ignored as upstream. Paths, textures and text are unsupported. The stereo
high bit on the mode byte is rejected. An empty packet `[36,0]` is a valid no-op.

The maximum count is255 (5102-byte full message). A device integration should
advertise/enforce its own smaller command/time budget; this is not evidence that
255 complex primitives fit a display deadline. Dimensions must be1..4096, stride
must hold `ceil(width/2)` bytes, and `stride*height` must fit both the supplied
buffer and32-bit offset arithmetic. No allocation or recursion occurs.

The entire packet's shape/length/type validity is checked before any pixel is
written. Trailing bytes, truncation, unknown types and framebuffer/input overlap
are errors with no writes. The caller must keep input and target metadata stable
during the call. Return values distinguish target/message/unsupported/alias
errors. Rendering into caller memory does not promise atomic presentation.

GRAY4 pixels use even x in the high nibble. Row padding and an odd width's unused
low nibble are unchanged. Buffers need only byte alignment. Public pixel/span
helpers clip signed coordinates; `mm_raster_clear` changes visible pixels only.
The module assumes the two's-complement, arithmetic signed-right-shift targets
used by the pinned upstream algorithms and the tested RV32/host compilers.

## Verification

```sh
python3 runtime/portable/tests/run_tests.py --output /tmp/memomind-geometry-check
```

The output directory must be new. The runner defaults to the bundled pinned
`tests/g2_compat/upstream` snapshot, verifies its revision and45 source/license
hashes, and writes only to the output directory. An explicit external
`--g2-source` checkout must match both the revision and hashes.
`--g2-source`, `--cc` and `--rvcc` select explicit local tools/sources. Defaults
use host Clang and the already installed task-local xPack RISC-V GCC15.2.0-1;
no downloads or global upgrades occur.

Latest geometry + RLE evidence: `analysis/portable-geometry-rle-tests-02/`.
The source-only geometry validator is exercised by every valid/malformed
geometry case; it requires no framebuffer and is shared with the renderer.

- **828 byte-for-byte comparisons** with unchanged G2 geometry, under AddressSanitizer
  and UndefinedBehaviorSanitizer: every type, widths0/1/2/17/255, representative
  geometry,500 deterministic varied/extreme coordinate cases,255-record batches,
  and empty input.
- Dimensions include600×350 stride300,600×350 stride320,600×175 stride320,
  601×351 stride311,31×23 stride21, and a640×480 batch. Tests check leading/trailing
  guards, row padding and odd-row unused nibbles with deliberately unaligned buffers.
- Negative tests cover every truncation of a two-record packet, trailing data,
  unsupported second record (no partial writes), stereo/wrong mode, aliasing,
  null/short/overflowing/invalid target metadata, and extreme clipped pixel/span
  coordinates.
- Freestanding RV32IMAFC/ILP32F compilation passes with strict alignment and no
  relaxation. The object has no undefined symbols and zero `.data`/`.bss`.
  Its `.text` totals3740 bytes and `.rodata`210 bytes (3950 bytes before linker
  layout/alignment). Largest compiler-reported individual stack frame is224 bytes;
  cumulative call-chain, caller and interrupt stack still need integration review.

The initial `tests-01` host comparison passed but Apple Clang lacked an RV32
code-generation backend; the runner was corrected to use the installed cross GCC.
`tests-02` passed before adding175-row slice coverage; geometry-only `tests-03`
preceded the shared validator and RLE addition. No renderer or RLE code has been
flashed or executed on glasses by this work.


## Pure preallocation geometry validation

```c
int status = mm_geometry_validate_message(message, length);
if (status != MM_GEOMETRY_OK) { /* reject before allocating a framebuffer */ }
```

This checks full mode36 framing, exact count/length and types1–13. It has no target
or side effects. Rendering repeats validation and retains target bounds and alias
checks; the caller must keep message and target metadata stable throughout.

## Packed 4bpp RLE

`rle.h` exposes an allocation-free boundary for G2 mode3/6 token streams:

```c
mm_rle_surface target = {
    .pixels = owned_pixels, .bytes = owned_bytes,
    .rowbytes = 300, .rows = 350, .stride = 320
};
int valid = mm_rle_validate(tokens, token_bytes, 600u * 350u);
int decoded = mm_rle_decode(&target, tokens, token_bytes);
size_t required;
int sized = mm_rle_encode(&target, NULL, 0, &required);
/* Allocate output independently, then encode with an explicit capacity. */
```

Unlike the geometry API's visible pixel width, this API exposes **whole packed row
bytes**. It consumes both nibbles, including any odd-visible-width padding nibble;
stride padding remains untouched. Cached image assets instead encode exactly
width×height pixels, so their acceptance boundary uses that expected count with
`mm_rle_validate`. No asset header parsing, cached image drawing or modes3/6 wire
routing is implemented here.

The token parser accepts all original positive count forms: a one-byte count1–15,
a two-byte count1–255, or a four-byte little-endian count1–65535. Wider noncanonical
forms remain valid. Zero counts, incomplete tokens, underfill, overflow and trailing
bytes are rejected. Runs cross row boundaries. The encoder emits the shortest form
and splits runs at65535, matching the original TypeScript encoder byte-for-byte.

Decoding validates the entire input before changing pixels and rejects input/output
overlap. Encoding first measures the exact output size; insufficient capacity
returns that size with no output changes. Metadata/result-pointer aliases are
rejected. Surface products and offsets must fit32-bit arithmetic; the backing
buffer must own at least stride×rows bytes. APIs do not allocate, clip or present.

RLE evidence in `analysis/portable-geometry-rle-tests-02/`:

- 378 padded/unaligned surface cases match the original C decoder, round-trip
  exactly and encode byte-for-byte identically to the unchanged extracted
  `demos/video-bench.ts::rleEncode`. Includes600×350 and600×175 stride320,
  random/alternating data and run boundaries crossing65535.
- All1,048,560 positive16-bit count/color combinations validate, plus applicable
  shorter and noncanonical forms;20,000 deterministic adversarial byte streams
  match original decoder acceptance. Invalid decodes leave output unchanged.
- The original shape suite's24×24 image fixture and malformed-byte mutation are
  compared against its original cached-image validator. This ports the RLE
  acceptance boundary, **not** the surrounding cache transaction/refusal/lifetime
  assertions. An odd3×3 asset explicitly distinguishes9 pixels from12 packed row
  nibbles. No standalone RLE CHECK predicates exist in the upstream transport suite.
- RV32IMAFC/ILP32F object:1212 text bytes, no data/bss or undefined symbols;
  maximum individual compiler-reported stack frame96 bytes. Call-chain and device
  scheduling budgets remain integration work. Clang ASan/UBSan run with recovery
  disabled; Bun is used only for the extracted pure encoder and needs no packages.

## Paths and rotated primitives

[`VECTOR.md`](VECTOR.md) documents the caller-owned10,752-byte workspace,
bounded path compiler, fill rules, transforms, rotated primitives and exact
original assertion mapping. The portable runner now also executes its separate
vector suite and RV32 import/stack audit. Full geometry/RLE/vector regression:
`analysis/portable-complete-tests-01/`. The subsequent scene core is tested by the
separate runner below; native integration remains separate.

## Retained scene and assets

[`SCENE.md`](SCENE.md) covers the complete modes37–41 cache/transaction/asset/state
core and explicit platform adapter API. Its separate runner now passes all334
original shape and90 vector CHECK sites (42,466 evaluations), plus original media
replays and public multi-context/stride/budget tests. Evidence:
`analysis/portable-scene-tests-03/`. Native font, display/timer integration and the
actual device memory/stack budget remain explicit boundaries.
