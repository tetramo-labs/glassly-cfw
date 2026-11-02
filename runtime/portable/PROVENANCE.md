# Source provenance and license

The geometry primitive implementation derives from the user's local
`/Users/fosse/dev/g2flash/patches/shapes.c` and geometric constants/layout in
`patches/shapes.h`, at commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`.
The original checkout was read only and remains unchanged. `UPSTREAM.json`
records exact hashes for the original source/header files, reference host test,
and license used by the verification runner.

The derived geometry module
and its adapters/tests are supplied under the MIT License. No original copyright notice has
been removed from the copied portions. Source comments documenting the primitive
algorithms are preserved. This directory is a modified derivative, not a claim
that upstream G2 supports MemoMind.

Adaptation date:2026-10-31. Changes:

- Copied integer geometric primitive functions through `rs_pie`, plus the
  type1–13 branch of shape dispatch and corresponding coordinate masks.
- Removed firmware globals/callbacks, context, allocations, retained cache,
  font/image helpers, vector paths, timers and lens handling.
- Added an explicit checked buffer/length/width/height/stride API and complete
  raw mode36 validation. Maximum natural count remains255; only types1–13.
- Replaced upstream's word-only whole-buffer clear with clipped spans, preserving
  row padding and the unused low nibble for odd widths, with no alignment demand.
- Rejects input/framebuffer aliasing and invalid dimensions/stride/length before
  mutation. The raw stereo flag is unsupported; immediate geometric record flags
  retain upstream's ignored behavior. Colors retain upstream low-nibble masking.
- Added standalone differential/sanitizer tests against the unchanged upstream
  host implementation and a freestanding RV32 compile check.

The production module does not include upstream host stubs or their firmware
addresses. `tests/g2_reference.c` includes the original host suite only in a host
comparison binary; it calls the original `cfw_shapes_immediate` on ordinary host
memory. Neither its renamed suite main nor any device entry point is executed.


RLE addition (2026-10-31): `rle.c` copies the original `patches/rle.c` state
machine and `patches/texture_cache.c::cfw_texture_rle_token`, with explicit bounded
surface/length wrappers and complete prevalidation. Its word-store optimization
is replaced by byte stores to support arbitrary alignment/effective types.
Encoding translates `demos/video-bench.ts::rleEncode` into bounded C, adding a dry
run for capacity and explicit stride. All sources are pinned in `UPSTREAM.json`;
license is the root MIT LICENSE. Tests include the unchanged original decoder and original
shape host fixture, and execute the verbatim extracted TypeScript encoder in Bun.
The geometry validator was extracted from the renderer into a public pure function;
target and alias validation remain in the renderer.

Vector addition (2026-10-31): `vector.c` derives compiler, contour/rotation and
primitive-to-contour functions from pinned `patches/vector.c`, using explicit
workspace/path/raster/transform APIs. `geometry_internal.h` declares two private
sine/Q4-line adapters to the existing geometry code; the unused copied
`rs_fill_rect` helper was removed for strict warning builds. Algorithm changes
are limited to equivalent constant-shift long division (no RV32 runtime imports),
explicit path stores/message initialization (no synthesized memory imports), and
an explicit signed winding cast/formatting for GCC warnings. Caller validation
and the1024 raster cap bound all runtime access/arithmetic. Full original
compiler/raster results and16 original vector predicates remain checked against
the pinned source. Scene/cache/native imports were not copied into production.

Scene/cache addition: `scene_cache.inc`, `scene_assets.inc`, `scene_shapes.inc` and
`scene_internal.h` are reproducible adaptations of pinned scene, texture and
shape sources. `tests/prepare_scene_port.py --check` verifies their derivation.
Device context/global lookups, heap, clock, timer, gate, shadow, presentation and
built-in font calls become explicit per-context platform boundaries. A cache
owner pointer carries context through helpers; original wire/cache/rollback
semantics and descriptor limits are retained. Cached asset renderers remain pure;
geometry and paths route to the existing portable modules. Compiler-generated
struct copies are replaced with local byte copies to avoid libc imports. Complete
original shape/vector test bodies keep every CHECK expression/order and inspect
production portable state, with only platform setup/reset binding adapted.


RESET scratch policy (2026-11-02): `MM_SCENE_RESET_UNDO_TRIM` is a native
opt-in adaptation, reproduced by `tests/prepare_scene_port.py`. After a successful
standalone RESET returns, the serialized scene adapter releases only undo scratch
through its owning allocator. It retains the store, metadata, vector workspace,
pixels, reply and epoch. Bundles never trim, including a final embedded RESET.
A subsequent mutating PUT/SHOW must reacquire undo or return CAPACITY before
pinning, eviction or staging. This deliberately differs from the default G2
revision50 no-undo fallback under allocation pressure. The default build and all
original assertions, including RESET pointer retention and no-undo behavior,
remain unchanged. Native policy tests are separate and explicitly labeled.


Naming normalization (2026-11-02): bundled reference identifiers/comments use
Glassly. Original upstream hashes remain in `UPSTREAM.json` under `original_files`;
`files` pins the normalized bundled copies. The copied-corpus manifest also records
both hashes for each changed file. Assertion expressions and numeric wire values
are preserved. CFW advertisements retain `GLASSLYCFW/N` with a numeric revision.
