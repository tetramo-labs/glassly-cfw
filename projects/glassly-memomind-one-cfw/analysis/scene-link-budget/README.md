# Retained-scene link, container and stack budget

The measured recommendation is **a 64 KiB extension limit with O2**, retaining
the existing application partition and staging allocations. Os nearly fits the
old 32 KiB limit before the native scene-session adapter, leaving only 80 bytes.
It also uses more stack on the measured recursive vector path.

The initial isolated experiment copied/hash-pinned all inputs under `snapshot/`.
It linked the existing graphics adapter plus scene/vector/RLE/geometry, forcing
all public portable exports to survive garbage collection. It changed only an
experiment linker script; no candidate OTA was written. The normal compiler's
other flags and RV32IMAFC/ilp32f ABI were retained. Portable units alone use
`-Wno-unused-function`, consistent with their existing portability runner.

| Snapshot experiment | Blob | 32 KiB result | 64 KiB spare | In-memory OTA | Staging spare |
|---|---:|---:|---:|---:|---:|
| O2 | 41,504 B | Fails by 8,736 B | 24,032 B | 2,216,299 B | 265,895 B |
| Os | 32,688 B | Fits by 80 B | 32,848 B | 2,209,217 B | 272,977 B |

`results.json` records exact hashes, flags, retained symbols and per-function
stack frames. Each optimization directory contains objects, compiler call graphs,
`.su` records, ELF, disassembly, linker map, binary and the actual 32 KiB trial
link result. The maximum individual frame is 336 bytes in both snapshot builds.
The experiments do not include the later native scene-session adapter.

## Actual scene-session integration

After authorization, the production compiler gained `--scene-session`, compiling
`scene_session.c`, `scene.c` and `vector.c` with `MM_GRAPHICS_SCENE=1`, while the
default build omits that define and those sources. Four public session entries
are explicitly retained. `.inc` files join headers/sources in the build hash and
concurrent-input-change checks. The root-owned aggregate initialization that
emitted an unresolved `memset` was corrected before the successful build.

The successful actual `runtime/build/scene-002` is **42,288 bytes**, SHA-256
`067263459317f06fb143c0a35824e686aa0382d239745d6d6b198f55c58ae1b2`.
It has 23,248 bytes left under 64 KiB. It links as actual ELF32 RISC-V, one
file-backed RX segment, with no writable/NOBITS/GOT sections, relocations or
undefined symbols. Largest individual frames are probe 400 B, geometry 224 B,
scene tick/render 208 B and session dispatch 176 B, all below the existing
512-byte static-frame ceiling. This does not claim a cumulative stack ceiling.

The default no-scene build was independently compiled after the changes. It is
byte-identical to the installed 7,808-byte graphics-004 blob, SHA-256
`08d478321f5340d06eab0f7007a49741a1ee7b1d8a3f716534221672ceac0b39`.
The existing installed artifact and device were not modified.

The linker region is now 0x10000 bytes at `0x0439bea0`; the allowed exclusive
ELF end is `0x043abea0`. The compiler, container builder and boundary tests use
65,536 bytes consistently. The fixed entry/gate, hook bytes, 16-byte alignment,
exact source hash and all CRC checks remain enforced. Tests cover an exact
64 KiB ELF span, one-byte overflow, 65,536-byte append, and staging overflow.
Eight container and seven compiler test groups passed.

At the full 64 KiB append limit, physical payload addresses are
`0x0039bea0..0x003abea0`, within the unchanged application partition ending
`0x003eb000`. Raw application size is 1,838,752 bytes, leaving **258,400 bytes**.
The type-4 staging allocation remains `0x25e000` (2,482,176 bytes); its exact
post-hook recompressed payload and 4 KiB-rounded span are checked each build.
`final-bounds.json` includes the real scene-002 and a synthetic maximum-size,
high-entropy blob. Both were constructed solely in memory; no experimental OTA
was saved or flashed.

## Stack evidence and limits

GCC `-fcallgraph-info=su` plus `.su` files provide conservative sums of known C
frames, counting even potential tail calls as retaining the parent frame.
`cv_curve` permits depth 0 through 8: at most nine 96-byte recursive frames.
`cfw_cache_prepare` has at most two frames: bundle mode 8 only recurses into
modes 37 through 41. No other direct-call cycles remain in the inspected graph.

| Known direct C chain | O2 frame sum | Os frame sum |
|---|---:|---:|
| `mm_scene_render_if_due` through scene render/vector curve | 1,488 B | 1,504 B |
| `mm_scene_dispatch` through the same rendering chain | 1,456 B | 1,472 B |
| `mm_vector_compile` through nine curve frames | 992 B | 1,008 B |

Indirect callback costs are unresolved in these sums. They are not complete
native task-stack bounds and exclude stock/interrupt/caller frames. The later
session adapter adds frames not present in the initial snapshot graph.

`measure_curve.py` executes actual linked RV32 vector code with no native mocks
needed. Two high-curvature cubic inputs reach recursion argument 8 and succeed
with 163 and 132 edges. Observed stack is **896 B O2**, **1,008 B Os**. The first
input executes 29,657 O2 instructions versus 29,072 Os instructions; these are
instruction counts, not cycle/performance measurements. An ordinary closed line
uses 128 B O2 / 144 B Os. Inputs/results are retained in
`curve-stack-measurements.json`.

## Actual RV32 scene runtime execution

The initial `tests/rv32/scene_runtime_emulator_test.py` separately pinned scene-002, required
the scene-session build flag, and reuses the prior native-mock machine through
in-process build/hash overrides. It leaves the old graphics emulator unchanged.
Six test groups pass across **79 actual handler calls** and about 11 million
display-side instructions. The actual native adapters, session core and scene
renderer execute; the same 26 external firmware API boundaries remain mocked.

Covered: reset mode 41, PUT 37, SHOW 38, STATE 40, clear 11; retained rectangle
pixels; binary cache replies; settled sent after the command reply; ten native
20 ms timer pumps completing a 200 ms translation; queue drops; admission and
core headroom failures; direct oversized allocation rejection by the actual
session-budget callback; malformed requests; lease expiry and stock-UI cleanup.
Observed core peak is **166,488 bytes**, under the 174,080-byte session budget.
The direct oversized-allocation test is an internal callback boundary test, not
a wire command. Observed handler stack is **400 B BT**, **1,120 B display**,
within the synthetic 4 KiB/8 KiB limits for these cases.

`scene-runtime-emulation.json` and its log retain the results. The separate
actual gate test passes 1,345 cases (`scene-002-gates.json`). These tests do not
establish physical rendering, stock allocator/LVGL behavior, concurrency or a
worst-case interrupt stack. This no-font profile has not been flashed by this
work; native-font integration requires a new build/hash and separate coverage.

## Final font-integrated scene-004

The current separate scene emulator pins `runtime/build/scene-004`: **44,592 bytes**,
SHA256 `cd849a72ecd662a79327d01f792ddbe6b09cd5d7a2a683aa05440301dced2bbd`.
This build includes native_text.c, the 32 KiB transient BT queue reserve, and the
four-byte-aligned session allocation header. Scene-003 preceded that header
source correction; the corrected scene-004 has identical machine bytes and a
new source manifest. The old installed graphics profile and its emulator remain
unchanged. Compiler inputs include headers and portable `.inc` files.

All **1,345 gate cases** and **8 whole-runtime groups / 96 handler calls** pass.
The latter executes 12,822,376 display instructions and 14,773 BT instructions;
observed stack remains **400 B BT / 1,120 B display**, and scene core peak is
**166,488 bytes**. New coverage forces every native owned allocation to4mod8,
then exercises reset/put/show/animation/cleanup. The ASCII AB case runs actual
native_text.c, wrappers, both preflight and draw passes, and checks the resulting
GRAY4 values `[0,5,10;15,10,5]` for each glyph. A missing second glyph leaves the
framebuffer unchanged. Readiness, font fields and glyph bits are guarded immutable
fixtures; the two native glyph lookups are explicit stubs (28 native stubs total).
This establishes the adapter contract against synthetic glyphs, not device font
resources or physical display behavior. Native helper stack frames are mocked
and therefore excluded from the observed-stack measurements.

`scene-004-container-bounds.json` independently reconstructs and verifies the
container in memory without writing an OTA image. Output is **2,218,446 bytes**,
SHA256 `ae772aed4107926e2d2c659e8cbdbc69d92421792c98630f9b7175b1188290d5`.
Payload is2,218,428 bytes, rounded staging span2,220,032 within2,482,176 capacity;
app raw length1,817,808 leaves279,344 bytes in the fixed2MiB allocation.
All known CRCs, both exact pinned hooks, unchanged prefix outside those hooks,
and unchanged other component streams are verified. Compiler rejection tests7
and container construction tests8 pass. Evidence: `scene-004-build.json`,
`scene-004-gates.json`, `scene-004-runtime-emulation.json`.
