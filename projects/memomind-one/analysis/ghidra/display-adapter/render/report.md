# Indexed4 rendering allocation audit

For the stock built-in decoder/software renderer and the proposed untransformed
600×350 indexed4 image, **no full-frame RGBA temporary is allocated**. The traced
image path decodes scanlines and uses small palette/color/opacity buffers. This
is not an exact whole-system heap peak or proof that a64KiB reserve is sufficient
under concurrent stock UI work.

## Exact relevant path and requests

1. Image setter `0x042bd7fa` calls decoder-info `0x042b64e6`; it borrows the
   variable descriptor and does not decode the full image. Decoder initialization
   [0x042b675a](function-042b675a.c) installs built-in info/open/read/close entries.
2. Open [0x042b61e0](function-042b61e0.c) recognizes cf9 in its indexed7..10 branch.
   `0x042b4076(9)` returns4. It allocates20-byte decoder state,16-byte converted
   grayscale palette and16-byte opacity palette: **52 bytes of requested heap**.
   The decoded-image-data field remainsNULL. Full-width×height allocation in
   other format/file branches is not taken for this variable indexed4 descriptor.
3. [0x042b4172](function-042b4172.c) sees decoded-dataNULL, clips to the dirty
   region, requests `2*clipped_width` scratch (at most1200 bytes), and calls
   decoder read separately for every row. It passes one-row clipping to the
   software draw callback and releases the decoded row afterward.
4. [Read 0x042b5dda](function-042b5dda.c) handles cf9 with packed stride
   `(width+1)/2=300`, palette offset64 and high-nibble even-x. It requests300-byte
   scratch even for variable memory source, then reads original packed bytes and
   expands each pixel into grayscale+opacity in the supplied1200-byte output.
   The300-byte scratch is released before returning to the draw backend.
5. Context initialization [0x042bd374](function-042bd374.c) installs image callback
   [0x042b77ce](function-042b77ce.c) at+0x18 and blend callback0x042b8b58 at+0x54.
   This is the default used by native display initialization. The decoded
   indexed row is format5, grayscale+alpha. Image callback requests separate
   color and opacity scratch, each at most600 bytes for this one-row clip.
   It then releases both. Thus simultaneous *in-use image scratch requests*
   are at most1200+600+600=2400 bytes, plus52-byte decoder state/palettes.
6. Blend `0x042b8b12` invokes installed0x042b8b58. Its inspected arithmetic/copy
   helpers contain no allocation calls. Default before-blend0x042bd2f6 is a no-op.
   Decoder close [0x042b5d8a](function-042b5d8a.c) frees palette,opacity and state.

The shared16-slot scratch pool retains released allocations for reuse; its
realloc path can transiently hold an old allocation plus a replacement, and
historical buffers can be larger than current requests. Therefore **2452 bytes
is a bound on the listed concurrent requested payloads, not total heap footprint
or incremental peak**. Allocator headers, retained slots, reallocation overlap,
fragmentation, and unrelated rendering remain additional demand. Image decoder
open allocations and scratch growth still use assertion-capable stock APIs.

## Display refresh and boundary

Native display port [0x042abd06](function-042abd06.c) supplies pre-existing static
buffer60000 bytes at0x020162b0 to the600×350 primary display and36000 bytes at
0x02024d10 to its second display. It calls default driver initialization and
sets flush callbacks; it does not replace the software drawing context initializer.
Those buffers already exist before creating the proposed image. They are not a
new heap allocation proportional to image dimensions.

Refresh0x042cbe70 has a software-rotation branch that can request10240 bytes of
scratch; this is a chunked conversion, not a fullRGBAframe. The port initialization
does not enable rotation. This pass did not prove that runtime code can never
change display flags. Stock screen widgets, masks, font work, opacity layers,
other image formats/custom decoders, and other tasks can cause other allocations.

Result for admission: the feared600×350×4=840000-byte image decode is not present
in the traced built-in indexed4 path. A64KiB policy margin greatly exceeds the
specific small image buffers above, but cannot be promoted to a whole-system
safety guarantee. Passive free/low-water observations, sparse commands, bounded
lease and final tests remain relevant. No image/device changes were performed.
