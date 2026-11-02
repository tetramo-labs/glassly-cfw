# Portable path compiler and rasterizer

`vector.c` ports G2's pinned path compiler, transformed contour fill and rotated
geometric primitives. It uses caller-owned memory and `mm_raster`; no scene,
cache, timer, native firmware address, display task or allocator is imported.
Source commit: `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. See `UPSTREAM.json`,
`PROVENANCE.md` and the root MIT `LICENSE`.

## Memory and API

`mm_vector_work` is 10,752 bytes, aligned to its C type. The caller supplies its
address and capacity on every call and serializes use. Allocate it from owned
memory rather than an embedded task's stack. A compiled path is a four-byte
header plus 16 bytes per edge, at most 8,196 bytes. These buffers may come from
any caller allocator; the module does not allocate or free them.

```c
int count = mm_vector_compile(work, work_bytes, commands, command_bytes,
                              1, NULL, 0); /* rule 1: even-odd; measure */
if (count < 0) { /* reject malformed input */ }
size_t path_bytes = mm_vector_path_bytes((unsigned)count);
/* Caller allocates appropriately aligned path storage. */
count = mm_vector_compile(work, work_bytes, commands, command_bytes,
                          1, path, path_bytes);
mm_vector_transform transform = {0, 0, 256, {0, 0, 0}};
int result = mm_vector_draw_path(target, work, work_bytes,
                                 path, path_bytes, &transform, 15);
```

Alternatively supply maximum path storage in one compile call. Compilation
returns an edge count including zero, or a negative error. Workspace is scratch
and may change on failure; a supplied output path is unchanged on failure.
`mm_vector_draw_shape` accepts one original 20-byte type1–13 geometry record and
an explicit `mm_vector_rotation`. Zero/full-turn angles use the existing geometry
renderer exactly. Caller-owned buffers must remain stable throughout each call.

Commands retain signed LE16 Q4 coordinates: M=0, L=1, Q=2, C=3, Z=4. Every contour
must close explicitly. Limits remain 8,192 command bytes, 1,024 commands and 512
compiled edges. Adaptive cubic subdivision retains the original half-source-pixel
tolerance and eight-subdivision limit. Nonzero winding and even-odd fill use the
original sorted scan intersections and coincident-crossing rules. Transform
translation and pivot are signed16 pixel coordinates; scale is Q8 in 0..2048,
rotation is Q8 degrees within ±100 turns. Paths accept color0..15. Shape colors
retain low-nibble masking.

The public vector raster limit is 1,024×1,024, covering both MemoMind600×350 and
G2's640×480. This bound protects the unchanged signed32-bit wide-line arithmetic
after rotation clipping. Row stride remains explicit;600-wide rows can be300 or
320 bytes. Padding and odd-width unused nibbles are preserved. Geometry's separate
public API retains its previous dimension limit.

All target, workspace, compiled-path header/edge/length, rule and transform checks
complete before framebuffer writes. Compiled edges must remain in the compiler's
signed16 source-coordinate range. Workspace/path/target/input/transform overlap is
rejected as applicable. Path storage must be correctly aligned. No framebuffer
presentation or scheduling atomicity is promised.

## Original assertions and differential evidence

Run standalone, or as the final stage of `tests/run_tests.py`:

```sh
python3 runtime/portable/tests/run_vector_tests.py --output /tmp/memo-vector-check
```

The output directory must be new. Default reference sources are the bundled
pinned `tests/g2_compat/upstream`; source hashes are checked before execution.
Local Clang supplies ASan/UBSan and the task-local xPack GCC supplies RV32 codegen.
No downloads or device operations occur. Each command, return code, stdout/stderr,
input corpus and executable/object hash is recorded, including failed runs.

Evidence: `analysis/portable-vector-tests-05/`, supplemented by the complete
portable regression in `analysis/portable-complete-tests-01/`.

- **16 exact original CHECK predicates / 20,026 evaluations** from
  `vector_host_test.c`: holes/nonzero fill, disjoint negative contours, curved
  path pixels/edge count, rotated primitive area/pixels, transformed path color,
  every primitive's nonempty rotation, compiler bounds and independent64-bit
  division expectations. Their expressions, original locations and portable
  locations are mapped in `tests/g2_compat/inventory.json`. The standalone
  implementation directly produces the pixels; no renamed G2 cache drives it.
- **10,063 compiler comparisons** against unchanged original `cv_compile`,
  including exact edge output, 10,000 original random command streams, additional
  full-range curves, exact512-edge and1,024-command boundaries.
- **483 byte-identical raster comparisons** against unchanged original drawing:
  both fill rules, cubic/quadratic paths, cardinal/fractional/negative/full-turn
  rotations, scale0..8, every type1–13 primitive, extreme signed coordinates and
  pivots, wide strokes,1024 boundary,600×350 stride320 and601×175 stride311.
  Unaligned byte buffers, row-padding/odd-nibble sentinels and outer guards remain
  intact. Invalid input/capacity/alias/transform tests verify no visible mutation.
- **291 exact stdin harness comparisons** with original `vector_path_check.c`:
  identical edge count and exit status for valid paths, truncations, invalid
  opcodes, signed extremes, budgets and oversized input. This harness is now
  ported; it has no independently registered named test count.

The initial standalone vector stage covered only the predicates above. The
subsequent portable scene layer now passes the complete original shape/vector
host suite, including retained objects, rollback, timing, leases and scene fuzz.
See `SCENE.md` and `analysis/portable-scene-tests-03/`. Native platform callback
bindings and the device memory/stack budget remain separate pending work.

## RV32 code and stack audit

The tested RV32IMAFC/ILP32F `vector.o` contains5,186 bytes of text and3 bytes of
read-only data before linker layout. Vector plus geometry has no undefined
symbols and zero writable data/BSS. The existing geometry sine/Q4 stroke routines
are shared through two narrowly named private adapters. There is no copied font,
ARM import or stock device entrypoint.

The original long-division algorithm used variable64-bit shifts that GCC lowered
to compiler helper imports. Constant-shift restoring division preserves its exact
results while removing those imports. Explicit edge stores and fully initialized
message fields avoid synthesized memcpy/memset calls. Tests still exercise the
original wide-product division predicates against independent native division.

The largest individual reported vector frame is160 bytes. The cubic recursion can
reach nine96-byte frames. Using this build's `.su` figures, conservative local
chains are1,008 bytes for compile (144 + 9×96) and1,024 bytes for rotated-shape draw
(160 + 9×96); caller, ABI entry and interrupt overhead are additional. These bounds
need review against the actual device task before integration. Workspace and
compiled-path storage are separate caller-owned memory, not included in stack.

Earlier `tests-02` exposed inherited GCC warning failures; `tests-03` and `04`
exposed compiler helper imports. `tests-05` is the successful corrected result.
No portable vector code has been flashed or executed on glasses by this work.
