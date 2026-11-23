# Retained-scene display adapter

The optional `--scene-session` build connects the portable G2 scene/cache/vector
implementation to the same two guarded native entry points as the installed
geometry runtime. The default build remains byte-identical to graphics-004.
Scene code is not implied to be installed by a successful host build.

The native display worker owns the scene, canvas, LVGL image and timer. A scene
command carries the original G2 bytes in one BYTES TLV on service15/command0x7d.
The Bluetooth handler releases the original request, posts a copied job and
returns no premature success. The display worker performs preparation, dispatch
and rendering before returning a correlated JSON response whose `replyHex`
contains the unchanged cache reply. Native queue admission can still drop a job;
the client times out and does not retry an ambiguous mutation.

Modes19/20/36 and37–41 use the scene adapter. Mode11 deletes the owner and frees
its entire scene. Empty mode36 renews the one-second lease without changing the
retained display. The existing20ms native LVGL timer advances the scene on the
same worker, using elapsed time rather than replaying a backlog of missed frames.
The adapter completes the original deferred rasterization before publishing the
owned image. Settled notifications follow the correlated command response; timer
completion emits its notification using the event of the last scene command.
Clients filter these notifications before matching ordinary responses.

## Memory admission

The initial native profile advertises a64KiB asset store and8192-byte raw message
limit. These are explicit integration limits, not a claim of full G2 capacities.
The core still supports256 objects,256 assets, transactional rollback and vector
paths. Original commands can upload assets in chunks. A bounded carrier for the
full65535-byte message limit remains outstanding.

Every scene allocation includes a tracked allocator header. Aggregate scene
storage is capped at170KiB, and allocation checks preserve48KiB of reported native
free memory. Store, descriptors, vector workspace and undo growth share that
budget. Failed growth uses the original smaller undo workspace and transactional
capacity replies. It cannot silently allocate beyond the aggregate limit.

At Bluetooth admission, the incoming request is already resident. A separate
32KiB transient reserve accounts for both the temporary job and queue copy; the
request is released before posting and the temporary job is released afterward.
The retained queue envelope is included in the host memory replay model. These
policies use summed free-byte snapshots. They do not prove a contiguous block,
reserve memory against other tasks, or make stock LVGL allocations nonasserting.

The600×350 host replays pass with227000 simulated free bytes after canvas/owner
costs, a64KiB store and this wire-memory model. Peak tracked scene bytes are171584
for the vector/GIF fixtures and173824 for the prepared SVG fixture on the host
ABI. Original640×480 expectations also run separately. Native-size replays check
all in-panel probes and explicitly omit995 GIF/1810 SVG probes outside the panel;
coordinates are cropped, not scaled. These are synthetic heap/display tests.

## Native text

`native_text.c` uses the proven MemoMind resource-font APIs and a16-byte native
glyph descriptor. It preflights strict UTF-8, metrics, mapped font ownership and
bitmap availability before changing a string's pixels, then draws packed1/2bpp
coverage into GRAY4. It performs no heap allocation. The dynamic fallback cache
is rejected because its cross-task bitmap lifetime remains unproven. Missing or
unsupported glyphs are not synthesized. The native default font is34px; matching
the G2 font's exact pixels is not established. The portable scene currently
ignores a built-in text callback failure, so a scene reply alone does not prove
that every requested glyph was drawn.

## Reproduce

```sh
python3 runtime/graphics/tests/run_scene_session_tests.py \
  --output /tmp/memo-session-tests \
  --fixtures-from analysis/regression-20261031-05/g2_compat
python3 runtime/graphics/tests/run_native_text_tests.py --output /tmp/memo-font-tests
python3 scripts/compile_memomind_graphics.py /tmp/memo-scene-build --scene-session
```

The fixed append profile permits64KiB of code and retains the existing app and
OTA staging bounds. The source hashes include generated `.inc` files. Compiler
checks reject writable storage, unresolved imports, relocations and individual
stack frames above512 bytes. Actual machine-code tests separately verify native
callback contracts and observed stack use; neither establishes worst-case
interrupt/callee headroom or physical panel output.


## Installed verification

Scene-004 was installed successfully on2026-10-31. Its44,592-byte blob has SHA-256
`cd849a72ecd662a79327d01f792ddbe6b09cd5d7a2a683aa05440301dced2bbd`;
the full OTA is
`ae772aed4107926e2d2c659e8cbdbc69d92421792c98630f9b7175b1188290d5`.
All542 blocks/3791 chunks and the18-byte header match the constructed image.

The native smoke/animation/text request sequence,24-command vector fixture and
both302-command video sequences completed. Final heartbeat and stock capabilities
passed; free memory after clearing returned near334000 bytes. These are native
execution/status checks, not independent pixel readback or visual confirmation.
GIF/SVG trace spans were124.468/150.185 seconds, including transport and delays;
30fps throughput remains unproven. See `analysis/scene-hardware-verification.json`.
The bridge was stopped, its forward removed, the official app restored and all38
capture files verified against their final manifest.
