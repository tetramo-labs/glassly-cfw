# Optional transactional scene store implementation

The complete portable scene backend is implemented behind `MM_SCENE_EXTERNAL_STORE`. The default build retains its original fields, RAM allocation/undo semantics and machine code. This feature has **no native binding, compiler option, OTA or device installation** yet.

Latest completed aggregate validation: `../regression-20261101-02/scene-flash-store/report.json`. It includes the subsequent reader-owner and initializer alias fixes, also checked in `scene-integration-004/report.json`. Earlier default compatibility evidence is retained in `default-scene-regression-001/report.json` and `default-byte-identity.json`; preserving old MemoMind build identity is no longer a user requirement. The design inventory remains in `scene-integration-review/report.md`; its proposed ingress and native/XIP work is still future work.

## Public contract

With the macro defined, `scene.h` exposes `mm_scene_init_with_store(context, platform, store)`. `mm_scene_store` in `scene_store.h` contains caller-owned context, exact logical capacity262144, synchronous read/begin/write/commit callbacks, nonfailing abort/reset and an alias callback. Configuration is copied into the scene. There is no writable or permanent mapped pointer. The physical owner, callbacks and scratch outlive the scene; release/reap/reset discard the logical epoch without freeing externally owned state or performing physical writes.

`scene_flash_store.{c,h}` provides `mm_scene_flash_store_bind(operations, initialized_flash_store)`. It binds the existing production transactional core; it does not reserve a physical region, fetch native bad-map state or call any native address. The core must already have passed its exact geometry and mandatory unavailable-bitmap checks. Reset preserves its supplied geometry/callbacks/real exclusions while creating an empty logical map.

`mm_scene_bytes` is either a bounded RAM span with offset0 or a store+logical offset/length. Checked reads copy into independent caller memory. They reject malformed or ambiguous handles, missing read/alias callbacks, range/integer overflow and destination aliases with source, handle or store state. `mm_scene_bytes_sub` supports self-subdivision using a local snapshot and leaves output unchanged on failure. Typed object pointers must still refer to accessible memory; integer checks do not prove memory accessibility.

`mm_scene_cursor_init` returns an error without changing the cursor if its source would alias the cursor. `mm_scene_cursor_read` uses a256-byte cache, rejects destination/cache/state/source aliasing, bounds cache metadata and destination integer spans, and invalidates cached bytes after a failed refill. Source bytes and mapping remain stable for the cursor lifetime under scene serialization. Readers return-1 for invalid arguments and-2 for callback failures; partial destination writes are possible on I/O error.

## Transaction and rendering changes

All direct external asset accesses now use logical offsets: upload chunks, retained inline strings, compiled paths, complete-asset validation, SHOW edge-count validation, retained rendering, immediate modes19/20/36, cached fonts/images and native-font string payloads. RAM code remains available and original RAM pointer tests are unchanged.

External modes37/38 require the existing metadata snapshot with zero byte-undo granules. The snapshot is mandatory even for an ops-only SHOW, since path-header reads can fail after flags are changed. Missing snapshot allocation refuses before any flash mutation. Byte rollback uses sector COW; descriptor/upload progress/LRU/refcount/bitmap/journal/active-state rollback uses the snapshot. Flash commit happens after staged validations and before the deterministic descriptor commit. The original degraded RAM behavior when undo allocation fails is preserved only on the RAM path.

Completed images/fonts/strings validate through staged readers. Font and string handles coexist without competing borrowed pointers. RLE tokens and glyph headers can cross pages/sectors; a bounded cursor fetches bytes. Cached text keeps its prevalidation pass. Retained strings remain128bytes maximum; immediate cached-text mode20 retains its original255-byte limit.

`mm_vector_draw_path_reader` reads the4-byte header and up to512 source edges into the existing10752-byte vector workspace, validates before touching pixels, then transforms/fills. It needs no additional8196-byte contiguous path allocation. Compiled-path upload writes its header plus one contiguous edge block rather than performing a separate COW write for every edge. The original RAM path API remains unchanged.

Storage callback failures are reported as `MM_SCENE_STORAGE_IO`(-3); the scene reply length is cleared instead of returning a successful cache reply. Precommit failures restore logical bytes and metadata. Postcommit rendering failures are different: pixels may already be partly modified. The core sets `shadow_invalid`, suppresses presentation, and stops animation; callers must not let a native image consumer use those pixels while invalid. A duplicate SHOW with PRESENT retries rendering of the already committed scene without reapplying its motion or state changes. A successful complete redraw or explicit HIDE clear restores validity.

This does **not** provide an untouched previous framebuffer on physical read failure. Native LVGL currently borrows shared pixels, so a native binding must explicitly handle invalidation/ownership or provide staging pixels/proven stable XIP reads before use. Native callback timeouts, flash cache coherency and whole-task stack safety remain unproven by this portable work.

## Files and reproducibility

Changed production files under `runtime/portable/`: `scene.c`, `scene.h`, `scene_internal.h`, `scene_cache.inc`, `scene_shapes.inc`, `vector.c`, `vector.h`. New files: `scene_store.{c,h}`, `scene_flash_store.{c,h}`, `scene_assets_external.inc`.

The generated source check is preserved. `tests/prepare_scene_port.py` first derives the original adaptation from pinned upstream, then applies explicit before/after hunks from `tests/scene_store/generated-overlay.json` for only the three generated production files. Both base and result hashes must match. It neither changes nor relaxes original test predicates. `update_overlay.py` is a maintenance command for reviewed edits; the regression does not run it or silently refresh evidence.

Required standalone stage:

```sh
python3 runtime/portable/tests/run_scene_store_tests.py \
  --fixtures-from <fresh-g2_compat-output-directory> \
  --output <new-validation-directory>
```

The runner requires all three exact fixture hashes, builds production code and two host executables with ASan/UBSan, checks the generated overlay, compiles/links actual RV32IMAFC/ilp32f objects and saves ELF/disassembly/layout/stack/hash evidence. Source drift during validation fails the run. No aggregate runner was edited here.

## Final measured evidence

- All three unchanged fixtures match RAM versus flash after every message/tick: full640×480 raster, replies, descriptor arrays, allocation bitmap, journal, revisions, active list, presentation counts and settled events. The corpus has24/302/302 messages and21/7200/7200 expected pixel probes.
- A full262144-byte asset is uploaded through exact65535-byte messages; no capacity reduction. A full first replacement message fails at each of528 native callback boundaries after potential evictions/overwrites; all previous logical bytes and metadata remain intact.
- Another35 callback boundaries cover completed-asset validation. All20 reads in a cached-font/image/native-text/inline-text SHOW fail individually, including drawing-pass reads. Presentation is suppressed, invalid pixels are marked, and same-request redraw recovers without replaying mutations. Begin/commit failures and mandatory metadata-allocation failure are covered separately.
- Cached font/glyph and RLE data cross sectors and exercise all token forms, inverse/transparency, retained and immediate rendering. Malformed final content refuses with rollback. Maximum512-edge/8196-byte paths render;4096 active scene edges succeed and over-budget SHOW refuses. A SHOW path-header read failure restores metadata before rendering.
- Every mocked erase/program asserts its target is outside both active and staged maps. Every physical callback rejects genuine unavailable bits (including first/last sectors). Rendering, queries, reset and release are checked not to erase/program. The previously completed flash-core exhaustive4224-failure tests remain a separate required stage.
- Public reader tests cover malformed handles, null callbacks, overflow, aliases, self-subdivision, unchanged failure outputs, cursor boundaries and failed-refill recovery.
- Eight path-reader owner-alias cases reject handles, operation tables, backend state and RAM source overlapping the workspace/framebuffer before callback reads or writes. Two initializer cases reject scene-context overlap with the flash context or scratch before memset; the entire owner remains unchanged.
- The unchanged default original scene suite passes334 shape+90 vector CHECK sites,42466 evaluations, public ownership tests and all three fixtures. Default `scene.o`, `vector.o` and `geometry.o` matched the prior regression objects. A final fresh native flash-reader rebuild remains byte-identical:50880bytes, SHA256 `d162d7c2f93ac57618f7756260e2b9c945313c160e6874517f98a8202777ca1b`.

Optional RV32 portable link (all scene/geometry/vector/store functions retained before native profile GC):44876 executable bytes and564 readonly bytes, no imports or writable globals. Maximum individual frame384bytes. Scene context1056bytes; platform60; descriptors43420; metadata undo base45468; vector workspace10752. Add the flash core320-byte context and4096-byte scratch. These figures exclude native owner/pixels/ingress/allocator headers and cumulative callback stacks. This compile is not hardware or RV32 instruction-emulation execution evidence.

Full65535 native ingress/decompression, both-origin buffer/spool coexistence, physical reservation/bad-map binding and rendering coherency/scheduling still require the separately scoped work. Installed native scene capacity remains64KiB RAM.
