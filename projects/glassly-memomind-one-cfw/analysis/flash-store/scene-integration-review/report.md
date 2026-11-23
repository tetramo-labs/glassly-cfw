# Full-capacity scene backend integration review

**Recommendation:** keep the existing RAM path and unchanged G2 tests, add an optional transactional store plus bounded offset readers, and port every cached asset consumer to those readers. The flash core is suitable for logical byte rollback, but cannot replace `texture_cache` with a pointer. Full 256 KiB asset capacity is achievable at this layer without reducing object, path, font, image or message limits. Full native parity additionally requires solving ingress/decompression memory, flash reservation, scheduling and read-failure presentation behavior.

This is a source review and implementation proposal only. No production source, compiler, runtime, aggregate runner, image or device was changed. `evidence.json` pins the inspected source hashes, collects direct pointer-use line witnesses, records current RV32 layouts and pins unchanged replay fixtures. Baseline evidence is `analysis/regression-20261031-10/scene/report.json`; the parent reports the latest aggregate has 36 passing stages. Existing historical evidence is not a claim that a flash-backed scene was tested.

## Exact access inventory

Paths in this table are under `runtime/portable/` unless specified. Line numbers refer to the pinned source snapshot.

| Location | Current dependency | Required replacement |
| --- | --- | --- |
| `scene.h:43`; `scene_cache.inc:238–276` | Context owns a contiguous mutable allocation, selected from 256/192/128/96/64 KiB; availability and capacity are inferred from pointer/size. | Separate `store_ready`/logical capacity from RAM pointer. Optional externally owned backend; default allocation policy stays intact. A flash profile reports exactly 256 KiB or fails, never silently falls back to 64 KiB. |
| `scene_cache.inc:303–339`, `1750–1790` | Free/reap/reset/epoch paths depend on RAM pointer ownership; reset reports `texture_cache_size`. | Explicit backend epoch reset/close, no erase on reset or release; preserve descriptor/epoch/reply behavior. Do not free caller-owned flash state as RAM. |
| `scene.c:117–129` | Input alias checks exclude context, store, framebuffer, vector workspace and variable undo allocation. | Preserve checks for RAM. Add external context/workspace/view alias checks; require request bytes remain stable through commit. |
| `scene_cache.inc:347–393`, `908–981` | Metadata snapshot plus sparse 16-byte granule before-images, copied from/to `t->store`. | Flash uses its own byte COW and **mandatory metadata snapshot**. Do not copy granule before-images for flash. RAM keeps old rollback/fallback semantics. |
| `scene_cache.inc:1078–1088` | Asset upload writes directly; final chunk validates the entire assembled asset through a contiguous pointer. | Backend write; complete-asset validation using staged offset reader. Distinguish bad content from backend I/O failure. Earlier upload messages remain committed when the current message aborts. |
| `scene_cache.inc:1167–1171` | Retained inline strings become private bytes via memcpy. | Backend write of at most 128 bytes, same descriptor/refcount behavior. |
| `scene_cache.inc:1175–1193` | Compiled path header and each edge are stored through a typed pointer. | Encode 4-byte header and write the compiled edge block from existing vector workspace. Never one COW write per edge. |
| `scene_cache.inc:609–637` | Shapes hold `asset`, `font`, `text`; path is `store+offset`. String and font pointers can be alive simultaneously. | Keep bounded `{offset,length}` asset handles; inline request text may remain a borrowed RAM span. Copy short retained strings before fetching font data. |
| `scene_cache.inc:642–661` | Every render clears shadow and loops active shapes; texture and paths are read synchronously. | Checked asset readers; explicit render failure propagation, no silent partial-success return. Preserve paint order and full feature set. |
| `scene_cache.inc:1578,1584` | SHOW reads each private path header for total active edge budget. | Read just the 4-byte header from staged view; validate kind/length/count. Include failures in transaction rollback, including SHOW without PUT entries. |
| `scene_cache.inc:1847–1895`; `scene.c:98–111` | Modes 19/20/36 resolve complete assets into pointers; mode36 has a validation pass followed by draw pass. | Same bounded handles and readers for immediate and retained rendering. Keep prevalidation before drawing for malformed input. |
| `scene_assets.inc:37–65,85–113,175–250` | RLE image pointer, font table pointer and two-pass cached-text renderer; glyphs have variable lengths. | Bounded cursor reads across pages/sectors, retain numeric positions rather than borrowed view pointers. Preserve exact RLE validation, character advances, transparency/inversion and clip rules. |
| `scene_assets.inc:305–320`; `scene.c:77–95` | UTF-8/control text is bounded at 128 bytes and copied to a native-font message. | Read retained text into existing/small explicit scratch; native font callback ABI need not change. |
| `vector.c:227–239,384–402` | `mm_vector_draw_path` requires a contiguous aligned path, checks it, then copies/transforms every edge into `work->edges`. Input may not alias workspace/frame. | Add a reader entry point that loads/validates edges directly into existing workspace, then transforms/fills only after all reads pass. Keep original public function as a RAM wrapper and preserve original validation. |
| `scene_internal.h:297–305`; `scene_cache.inc:1295–1304` | Same-version reassertions retain pointers to request records until commit. | Safe only while full request remains stable. A future streamed ingress must store record offsets or copied fixed fields, never decoder-scratch pointers. |

`scene_shapes.inc` decodes borrowed text/path-command pointers from the current request. These are not retained after successful commit; compiled path edges and retained inline text are copied into the asset store. This distinction must survive a reader conversion.

`cfw_texture_render_a4` in `scene_assets.inc:117` uses native/host glyph bitmap memory, not `texture_cache`. Its pointer contract must remain separate from cached RLE font assets. `vector.c` otherwise has no cache allocator or flash ownership; its only relevant coupling is the path input API.

## Smallest concrete API

Add `runtime/portable/scene_store.h` and a small implementation, with an optional backend configured by a new `mm_scene_init_with_store(...)`. Keep `mm_scene_init(...)` as the default-RAM wrapper. Do not insert a fake nonnull `texture_cache` sentinel to bypass checks.

Suggested external backend contract:

```c
typedef struct {
    void *user;
    uint32_t capacity;                  /* full flash profile: 262144 */
    int (*read)(void *, uint32_t, void *, size_t);
    int (*begin)(void *);
    int (*write)(void *, uint32_t, const void *, size_t);
    int (*commit)(void *);
    void (*abort)(void *);              /* nonfailing, no I/O after begin */
    int (*reset)(void *);               /* new empty epoch, no physical writes */
    void (*close)(void *);              /* idempotent owner cleanup */
    int (*aliases)(void *, const void *, size_t);
} mm_scene_store_ops;

typedef struct {
    /* One of RAM or store is selected explicitly. */
    const uint8_t *ram;
    const mm_scene_store_ops *store;
    uint32_t offset, length;
} mm_scene_bytes;
```

All fields/pointers have defined ownership. The session copies the operations table; its opaque owner outlives the scene. `reset`/`close` are session lifecycle events, not writes. All begin/write/read/commit calls use the same serialized owner; no backend operation may reenter scene code. Flash read automatically selects staged or active data according to its transaction. Capacity/range arithmetic remains subtraction-based. `aliases` must cover flash context, workspace and any mapped read ranges; a binding cannot treat invalid pointer arithmetic as proof of nonaliasing. A small public wrapper can expose the core's known context/scratch spans without allowing context mutation.

`mm_scene_bytes` is a value handle. `bytes_read(handle, relative, dst, n)` validates against handle length before translating the logical offset; RAM uses a checked copy, flash uses callbacks. Helpers include LE16/LE32/header reads, a sequential cursor with a bounded cache (e.g. 256 bytes), and explicit subregions. A string and font handle coexist safely because neither holds a backend scratch pointer.

Do **not** expose a generic writable `map()` API. Flash physical placement is fragmented by sector COW. `mm_flash_store_view()` is useful for internal bulk copies but its single scratch view expires at the next store operation, including a second view/read/write; it cannot back simultaneously retained asset/font/path pointers. If using views inside readers, copy needed bytes before any nested access. For a first implementation, direct checked reads into reader-owned cache are simpler than sharing the flash write scratch.

The flash adapter directly binds begin/read/write/commit/abort to `mm_flash_store_*`, with init/reset retaining authoritative geometry, bitmap and callback configuration. Reset discards maps without erasing physical data. Native reservation and all excluded-sector checks remain the responsibility of the separately reviewed platform binding. The default RAM path can initially retain its current contiguous fields and sparse byte undo while passing through the same read helpers. This preserves all original allocation-failure predicates; converting RAM to a second COW implementation is unnecessary scope.

## Transaction order and exact semantic boundary

Modes 37 and 38 are per-message asset/descriptor transactions. Multi-message upload chunks are separate transactions; a failed final chunk must not erase the already committed prefix. Mode8 preparation understands segments, but the current session adapter does not dispatch mode8. Do not invent whole-bundle atomicity: preserve each constituent command's established transaction boundary if native bundle support is later added.

For flash, before any pinning, eviction, staged descriptor change, journal modification or asset write:

1. Allocate a mandatory metadata snapshot during prepare, before the display gate where required by the platform. If it cannot be obtained, return the existing capacity refusal without mutating anything. An ops-only SHOW can now encounter path-header I/O, so it also needs snapshot protection before setting PINNED/NEXT flags.
2. Under serialized ownership, take the snapshot and begin the byte transaction. Complete syntax validation still happens before mutations. No flash erase/program is permitted for malformed preflight input.
3. Stage all uploads, inline text and compiled paths, resolve references, validate completed assets, total edge budget, operations and dependencies through the staged reader.
4. On validation/missing/capacity/I/O failure, abort flash first, then restore metadata/journal/LRU/upload progress/active flags; preserve the computed rejection details. No render, presentation, settled notification or success acknowledgment occurs before this decision.
5. Once all fallible asset reads/writes/checks finish, commit the flash map and perform the deterministic existing descriptor commit with no further fallible storage access in between. The flash commit currently performs no I/O. An unexpected commit failure must leave the active map intact and force abort/metadata restore. All callbacks in a generic backend must honor that contract.
6. Apply SHOW state/animation and render/present according to the existing order. Presentation failure is a different boundary: current SHOW already commits before `cfw_scene_present`, and can return an error afterward (`scene_cache.inc:1597–1642`). Do not claim framebuffer/presentation rollback from byte transaction rollback.

There is an important existing compatibility nuance: if `sc->undo` cannot be allocated, `cfw_txn_snapshot` intentionally allows the RAM message to continue, and a rejection may retain evictions/revision changes (`scene_cache.inc:908–916,983–990`). Original tests explicitly exercise this behavior. Keep it for the default RAM path; the flash path must never enter it. Requiring a fixed metadata snapshot for the external transactional backend strengthens failure isolation without changing normal wire semantics or discarding any successful G2 feature.

Minimum initial edit: reuse `cfw_undo` with `undo_capacity=0` for flash, skip its byte saved-map/granule copy loops and rely on flash abort. That costs 45,468 bytes on RV32, including 2,048 bytes of unused saved bits. A later split into `cfw_cache before` plus a RAM-only sparse-granule extension saves those 2,048 bytes; it is not necessary to prove first correctness. Snapshot must also include every field the failure path can change; it is not enough to restore asset descriptors alone.

Backend I/O is not malformed asset content. Use a distinct internal scene error, e.g. `MM_SCENE_STORAGE_IO`, and propagate it to the caller after rollback. The portable transport can NACK a nonzero handler result without changing the G2 wire format. Native JSON should identify the storage failure rather than silently reporting a successful empty frame. Existing CAPACITY/MISSING/REFUSED replies remain unchanged for their original causes.

## Rendering without a full asset copy

Images are up to 255×255 pixels, and fonts can occupy most of the full 256 KiB store. Loading an entire font/image into RAM would defeat the capacity goal. RLE needs only up to four token bytes at a time, but fetching every token with a native call is needlessly expensive. A 256-byte checked cursor can refill in page-sized reads and carry token/header fragments across boundaries. Store the RLE offset/length in `cfw_cached_image`, not a pointer. Validation and rendering must use the same format rules and count arithmetic as now.

Cached strings are at most 128 bytes. Copy one into small session scratch before font lookup, then read the 96-entry font table by LE32 entries or a bounded table cache. The current text renderer validates every character and glyph before drawing; retain that validation pass. It then validates/reads glyph streams again for drawing. Avoid repeated native reads by optional reader caching after correctness is proven; do not skip validation or reject large valid fonts to reduce work.

Compiled paths are at most **8196 bytes** (4-byte header plus 512×16-byte edges), larger than the flash scratch sector. Add `mm_vector_draw_path_reader(...)` with a header and read callback, or a generic bounded byte handle. Read the header and edges into the already allocated 10,752-byte vector workspace, validate every source endpoint and transform bound, and only then perform transform/fill. This removes the need for an additional contiguous path copy. Keep the original `mm_vector_draw_path` as a RAM adapter to the same algorithm and preserve all original overlap/alignment/validation behavior. Path upload should write its 4-byte header and contiguous `work->edges` block in two calls (or a small scatter-write helper), not 512 individual writes.

Animation uses the same render path on every frame; no parse-time pointer may survive into the next tick. Numeric asset identities, offsets and lengths are safe while the scene owner holds serialization. Retained frames, arbitrary rotation, all 512 edges per path, the 4096-edge scene budget and all cached image/font/text modes must stay supported.

**Read errors during drawing require an explicit policy.** Prevalidation catches malformed content but cannot guarantee a later driver read succeeds. The current render clears and writes the shared shadow before presenting; LVGL also borrows this pixel allocation. A second-pass read failure therefore cannot honestly promise an untouched frame simply by suppressing a new `present` call. At minimum mark the shadow invalid, stop animation, propagate failure and prevent LVGL from using it until a successful redraw or owner teardown. Strong last-frame preservation requires separately owned staging pixels or a proven nonfallible snapshot/XIP read path. This is an open native integration decision, not something the byte-store transaction resolves.

## RAM reader versus optional XIP optimization

The correctness implementation uses callback reads. A later XIP reader may return **const spans for individual mapped physical sectors**, with a mapping epoch/lifetime held until render completes. It cannot return a whole logical-store base: adjacent logical sectors may map to unrelated physical sectors. Assets crossing a sector still require cursor iteration.

XIP needs native proof of the exact external-device translation, cache coherency after program/erase, availability during controller writes, and serialization against every other native user. It must respect the real unavailable map and cannot point at uninitialized/unmapped logical sectors (which read as zero in the ephemeral core). Span addresses must never become retained scene fields. Stable XIP can reduce read-call cost; it does not make the store writable via CPU pointers, prove 30 fps, or establish safe physical reservation.

## Memory and ingress: why 256 KiB storage alone is insufficient

Measured RV32 layouts from the unchanged scene regression:

| Allocation | Bytes |
| --- | ---: |
| Scene context | 1,016 |
| Cache descriptors / transaction / bitmap / journal | 43,420 |
| Existing undo base with zero granules | 45,468 |
| Vector workspace | 10,752 |
| Flash context plus scratch | 4,416 |
| Sum before reader caches, session owner and allocator headers | **105,072** |

Splitting the metadata snapshot removes 2,048 bytes from that sum. The native 600×350 packed4 framebuffer alone is 105,000 bytes plus palette/descriptor/allocator ownership. The current native session policy remains 170 KiB with 48 KiB allocator headroom and deliberately requests the **64 KiB** RAM store (`runtime/graphics/graphics.c:144–145`). Replacing that store and its variable byte undo reduces RAM pressure, but native admission still needs measured simultaneous lifetimes; summing isolated successful allocations is not proof.

The GM graphics command currently caps input at 8192 and copies request→owned job→native queue (`graphics.h:15`; `graphics.c:217–236`; `native.c:27`). Its admission bound includes `32KiB + 2*(length+header)+8` while the inbound request still exists. Simply changing the constant to 65535 would demand roughly another 128 KiB transient reservation and may overflow a native envelope's size field once its own job header is added. Confirm exact native length widths and TLV limits before any change. The display's job remains alive while scene prepare/dispatch run.

The portable G2 transport is different: it reassembles a full compressed wire record, allocates `max_record+1` decoded bytes, retains inflater history, verifies decoded CRC, then calls a synchronous handler while the buffers remain alive (`transport.c:139–169,222–249`). Native compressed ingress is not installed merely because the host transport tests pass.

The pinned inflater study (`analysis/ghidra/transport-inflater/report.md:128–160`) measures 39,944 bytes per full-window stream, 79,888 for both origins. At max record 65535 the current design needs **171,015 bytes for one origin** or **276,494 bytes for two retained origins with one synchronous decode**, before scene, pixels, queue buffers, metadata, stacks or allocator overhead. Limiting the history window, only allowing small records, or disabling one original origin would reduce G2 behavior and is not a full-parity completion.

Recommended separate ingress step: retain bounded packet receipt and both stream histories, feed an actual persistent inflater incrementally, compute decoded CRC incrementally, and stage decoded records in a separately budgeted spool. Dispatch only after complete CRC/flags/context validation. The parser currently needs random-access bytes and same-message reassertion pointers; convert those to reader positions/fixed copied fields before removing the contiguous decoded buffer. A spool cannot casually share the asset store's logical256KiB or active transaction: a full asset store still has to accept the next full65535-byte message, and two partial origins must remain independent. Nor can the native managed directory or excluded/bad sectors be treated as free scratch. A specific reserved physical/RAM spool layout and its maximum coexistence proof are still required.

## File edits proposed after review

| Files | Change |
| --- | --- |
| New `scene_store.{c,h}` and flash adapter | Optional backend contract, bounded value handles/cursor, lifecycle and alias checks; default RAM wrapper. |
| `scene.h`, `scene.c` | Optional initialization/context backend; retained read handles; checked rendering errors and source alias rules. |
| `scene_internal.h`, `scene_cache.inc` | Replace pointer presence checks; byte writes/validation through backend; mandatory external metadata rollback; path header reads; report logical capacity; lifecycle. Keep default RAM undo fallback. |
| `scene_assets.inc`, related prototypes | Reader-based RLE/font/text validators and renderers with no retained scratch pointers. |
| `vector.{c,h}` | Reader-based path load into existing workspace, original API as RAM wrapper. |
| `scene_session.{c,h}`, `graphics.c`, native reservation binding | Explicit backend ownership, full capacity and measured budgets, task/lifetime/read-fault policy. Only after portable correctness. |
| Later `transport.{c,h}` and native ingress adapter | Incremental spool/parser and full65535 ownership model; separate from asset backend. Preserve both origins/context/reset/reply semantics. |
| Compiler/tests/provenance generation | Explicit new sources, real RV32 layout/stack/blob guards, generated-port source check update with preserved upstream pin and predicates. |

No changes to `flash_store` are required for a first read/write adapter. Performance work may later add sector-coalesced writes: today two writes to one sector cause two COW cycles, and each one-byte change erases/programs an entire sector. That is correct but can create high write amplification for many inline objects or path fragments. Any optimization must retain poison/abort guarantees and full replacement capacity with genuine bad sectors.

## Acceptance tests preserving full behavior

1. Keep the original 334 shape and 90 vector CHECK predicates and unchanged upstream fixtures on the default RAM backend, including allocation-failure fallback behavior. Existing white-box assertions directly index `texture_cache`, inspect path pointers and constrain undo capacity; do not rewrite/remove them to make flash appear compatible. Add a separate backend conformance harness using the same wire messages and expected replies/pixels, plus explicit snapshot reads for byte comparisons.
2. Replay the unchanged pinned `vector-fixture.bin`, `gif-300.bin`, `svg-300.bin` through RAM and flash; compare full raster bytes at every presentation, replies, revisions, state snapshots, settled tags and time-driven final states. Existing corpus covers 24/302/302 messages and 21/7200/7200 pixel probes; those probes alone should be supplemented by complete raster comparison.
3. Exercise all assets and entry types across page/sector boundaries: one-/two-/four-byte RLE tokens, font table entries, glyph streams, UTF-8/control strings, inline strings, compiled header and all512 edges. Use nonadjacent physical mappings, bad first/last/interior sectors and poisoned scratch on every read to catch retained pointers. A font and string must remain simultaneously usable.
4. Full256KiB occupancy with original256asset/256object descriptors, pinned/evictable supersession, full65535 messages and multi-message large fonts. Test >4096-byte paths, maximum edge expansion, 4096 active scene edges and exact over-limit refusals. Keep all geometry, clipping, inverse/transparency, cached/native-font and animation operations.
5. Inject every flash callback failure during uploads, complete-asset validation, path-header SHOW checks, rendering and immediate modes. For precommit failures compare **all logical bytes and all semantically relevant metadata**, journal/revision/LRU/refcounts/fill/active flags, previous replies and active scene. Test a late failure after earlier entries evict or supersede assets. No success reply/settled/present on rejected staging. Test zero usable runtime snapshot allocation before any mutations.
6. Commit/abort duplicate/retry semantics, same-version request reassertions, stale epoch, lost replies, reset/release/lease expiry/current-screen deletion and animation task serialization. No erase/program from status, render, reset or teardown. Ensure no stale handle survives reset/reuse.
7. Separate full65535 native ingress tests: both origins, partial records plus decoded full record, retained dictionaries, malformed/truncated/CRC-failed streams, expansion overflow and each allocation failure. Verify no scene side effects before validated record completion and no reduced-window compression shortcut. Audit all u16 length additions in native envelopes.
8. ASan/UBSan plus real RV32 compile and actual machine-code tests with native callbacks mocked; preserve source pins for installed profiles. Measure stack/call chains, blob/staging limits, native allocation peak, flash operations/bytes per message and elapsed rendering/animation cost before scheduling claims. A later hardware trace must establish reservation, reads/writes/coherency and stock coexistence; passing host fixtures alone is not full native parity.

The smallest safe first milestone is the complete portable reader/backend conversion with unchanged RAM semantics and differential flash fixtures. It should advertise neither full native ingress nor hardware readiness until the separate bounds above are proven.
