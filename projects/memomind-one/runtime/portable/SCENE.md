# Retained scene, cache and asset core

`scene.c` implements the pinned G2 modes37–41 using explicit platform ownership.
It retains the original cache transactions, rollback journal, asset uploads and
replacement, object identity/LRU rules, active ordering, tween/rotation clocks,
state replies and lifecycle. It renders through this repository's portable
geometry/vector implementations. It does not include G2 firmware entry addresses,
a singleton context or a native MemoMind display/timer adapter.

The upstream source is commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`.
`tests/prepare_scene_port.py` reproducibly extracts/adapts `scene_cache.inc`,
`scene_assets.inc`, `scene_shapes.inc`, internal layouts and complete original
host test bodies. `--check` verifies generated files without writing. All original
source hashes remain pinned in `UPSTREAM.json`; this derivative is MIT-licensed.

## Platform and lifecycle

`scene.h` exposes `mm_scene_context` and `mm_scene_platform`. Each context has its
own allocator callbacks/user pointer, clock, lease source, raster, reply buffer,
cache/epoch, timer and text scratch. There are no global mutable core variables.
The allocator receives an explicit persistent/workspace category; it must return
unique suitably aligned memory or null, and track a total budget if needed.

Initialize a zero/unowned context with `mm_scene_init(context, platform,
store_limit)`. The limit is64–256KiB; store allocation tries the original
256/192/128/96/64KiB sequence, skipping sizes above the limit. It does not resize an
already resident store. Initialization must not replace a live context: release
owned allocations and quiesce its callbacks first.

The native adapter must preserve this order:

1. `mm_scene_prepare` before acquiring the display gate. It allocates descriptors,
   store, lazy vector workspace and undo capacity, using the original fallback
   policy. No transaction is active here; the caller serializes message ownership.
2. Acquire the caller's display gate; call `mm_scene_dispatch` with mode37–41 and
   the original payload after the mode byte. Consume `cache_reply[0..len)`.
3. Present through the explicit callback. A callback that transfers gate ownership
   to the display task sets `dirty->direct_submitted`. The callback receives a
   temporary raster descriptor and must copy it if queued; the pixel memory must
   remain owned through consumption.
4. The timer callback enters `mm_scene_tick`; the stock-compatible gate/pending
   checks advance elapsed time and queue a refresh. `mm_scene_render_if_due`
   performs the deferred rasterization under the display task's ownership.

`mm_scene_takeover` freezes and hides the retained list when a raw raster mode
owns the canvas. `mm_scene_lose` marks lease loss; `mm_scene_reap` reclaims under
ownership. `mm_scene_release` stops animation and frees cache allocations, advancing
the epoch. The timer handle itself belongs to the platform: stop/delete/quiesce it
before destroying the context. Callback implementations must honor their lock and
lifetime contracts. No native callback binding is provided by this module.

`mm_scene_immediate` accepts full modes19/20/36 on an explicit validated raster,
including resolved asset-bearing shapes. The existing geometry-only API remains
unchanged. Public message entry points reject input aliasing context, cache,
store, vector workspace, undo storage or owned raster. The transport's original
65,535-byte message ceiling is retained.

The core's reply bytes and state transitions are unchanged. The outer G2 SID0xf0
transport is not installed by this port: a MemoMind adapter must carry these
messages/replies explicitly. Reply-capacity negotiation retains the original
five-byte outer header allowance.

## Assets and built-in font boundary

Cached RLE images, cached fonts, strict UTF-8 strings, inline text ownership,
transparent/inverse image options and bounded region drawing are pure core code.
Cached-font rendering is implemented. The G2 native LVGL font ABI and its fixed
Thumb/SRAM addresses are excluded.

Built-in font rendering is an explicit `builtin_text` callback. The full original
host suite already used a box-font stub; this port supplies that same stub through
the callback and preserves its assertions. Those checks establish cache/text
lifecycle and layout behavior under that callback, not MemoMind native glyph
metrics. A platform without this callback does not draw built-in text. A native
font adapter or portable font implementation remains pending.

## Verification

```sh
python3 runtime/portable/tests/run_scene_tests.py \
  --output /tmp/memo-scene-check \
  --fixtures-from analysis/regression-20261031-01/g2_compat
```

The output directory must be new. The optional fixture directory contains the
existing generated `vector-fixture.bin`, `gif-300.bin` and `svg-300.bin`. Inputs
are copied and hashed before replay. Omitted media is explicitly not run, never
reported as passed. The runner does not operate a device or modify source files.

Evidence: `analysis/portable-scene-tests-03/`.

- **All334 original shape CHECK sites and90 vector CHECK sites**, preserving
  every expression and order, execute against the actual portable production
  implementation:42,466 evaluations, no failures, zero live allocations.
- This includes original asset dependencies/chunk continuation/replacement,
  metadata and store rollback, reasserts, eviction/pinning, hidden animation,
  elapsed-time/clock-wrap behavior, state/journal replies, leases, timer failure,
  malformed transactions,10,000 compiler fuzz cases,20,000 scene-message fuzz
  cases and extreme geometry. No original assertion was removed or weakened.
- The white-box test includes production `scene.c` so original tests can inspect
  its real descriptors/helpers; it does not include upstream `scene.c`,
  `shapes.c`, `vector.c`, context or firmware-import headers. Production rendering
  links to portable geometry/vector, while platform faults are explicit callbacks.
- The original24-message vector replay passes21 pixel probes. Each original
  300-frame GIF/SVG replay passes302 messages and7,200 pixel probes.
- Separate public API tests link production source normally and create two
  independent owners:600×350 and601×175 with320-byte stride,64/128KiB store caps,
  explicit allocation budgets, alias/oversize rejection, allocator failure,
  lease loss/reap and release. Guards, row padding and odd nibbles remain intact;
  no live allocations remain.
- All host tests run with AddressSanitizer/UndefinedBehaviorSanitizer and recovery
  disabled. Strict RV32IMAFC/ILP32F compilation passes. Linked scene+geometry+vector
  has no undefined symbols and zero writable data/BSS. Command logs, source and
  artifact hashes, original assertion mapping and layouts are retained.

`tests-01` was the initial complete host run. `tests-02` passed the suites and
public API tests, then found a test-only initialization omission in the separate
replay entrypoint. That adapter was corrected; `tests-03` is the complete result.

## Resource budget

Measured RV32 layouts:

| Allocation/layout | Bytes |
| --- | ---: |
| Context, including platform/raster/reply/text scratch | 1,016 |
| Descriptor/cache block | 43,420 |
| Transaction state, inside cache | 1,636 |
| Object / asset descriptor | 116 /32 |
| Undo base | 45,468 |
| Each saved16-byte granule plus offset | 20 |
| Vector workspace | 10,752 |
| Minimum store | 65,536 |

A small transaction with64 undo slots uses166,456 heap bytes for the cache,
64KiB store, workspace and undo. Adding the context and current105,064-byte owned
canvas gives272,536 bytes before allocator metadata, queues, task stacks or stock
headroom. Against the earlier observed333,956-byte aggregate free heap, that
leaves only61,420 bytes arithmetically; it is not a guarantee of allocation success,
contiguous blocks, current availability or safe stock headroom.

**The store limit does not cap undo growth.** The preserved rollback policy can
request45,468 +20×16,384 =373,148 bytes for undo, then halve its capacity on failure.
The native allocator should enforce a total scene budget and reserve stock
headroom. Failure must return null so the original CAPACITY/rollback paths run;
there is no permission here to consume the entire measured heap. Workspace/undo
are lazy, and old undo is released before growth to avoid two simultaneous copies.

The scene object contributes19,176 text bytes and94 read-only bytes before layout;
combined scene/geometry/vector contributes28,152 text and307 read-only bytes.
Largest individual scene stack frame is208 bytes. This is not a cumulative stack
bound: scene call chains add to vector's up-to-nine96-byte recursive curve frames,
plus callback, caller and interrupt usage. A native task-stack/call-chain audit is
required before enabling the complete scene renderer on hardware.

Full portable scene/cache behavior is now covered on the host. Native callback
integration, native fonts, measured device runtime budget and complete G2 hardware
parity are separate pending work. No scene code has been flashed by this work.
