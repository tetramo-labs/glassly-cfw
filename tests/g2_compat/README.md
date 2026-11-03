# G2 source tests and MemoMind coverage

This directory preserves the upstream test corpus at G2 commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce` and records which assertions exercise
MemoMind code. The in-scope G2 command/feature suite is **not yet ported**. A successful selected
run must not be reported as complete G2 feature parity.

`UPSTREAM.json` pins all 96 bundled source/license files by SHA-256. Fourteen
copies have identifier/comment naming normalized to Glassly; the manifest retains
the original and normalized hashes. Numeric protocol values and original test
assertions are unchanged, as is the license notice. `inventory.json` maps 30
suite/orchestrator/integration files to their hashes, scenario counts, assertion
locations and expressions, counterpart implementations, dependencies and one of
`ported`, `unimplemented`, or `platform-specific`. Mixed suites retain an
incomplete file status, with finer coverage in `test_groups`.

## Current scope (2026-11-02)

The user excludes **Bluetooth keyboard/HOGP, ring battery, mode5 sound/tone commands, volume gating and gesture-specific
behavior**. The glasses have one button. Single-button events, generic wake
ownership, compass data, **raw IMU data**, ambient-light sensing, settings,
notifications, microphone, transport and drawing remain required.

All 96 source/license files are retained. Original assertion expressions remain
unchanged; the naming-only normalization is recorded separately.
The required coverage inventory is **38 C scenarios /622 assertion sites and11
Bun cases**. The historical totals remain46 /746 and21. The dedicated battery
scenario and head-up/ring-touch live harnesses are optional reference, not completed
ports. There are now **19 incomplete required suite/integration entries**.

Mixed settings/routing/compass/link suites stay required. Their preserved portable
reference binaries still execute historical battery/keyboard structural checks;
these do not require adding nonexistent hardware or native ring-battery reports.
Native adapter acceptance must separate unsupported selectors from required
settings/transport behavior. Compass headings must not be dropped with head-up
gesture tests. Scope regressions check these distinctions and original hashes.

Both runners keep keyboard-only stages optional via `--include-keyboard-reference`
and volume-gate checks optional via `--include-volume-gate-reference`.
The gesture live harnesses are inventoried, never run automatically. Historical
pass counts below refer to their dated scope. `--require-complete` continues to
fail until all currently required entries are implemented.

## Mode8 command-parity checkpoint (2026-11-02)

The native mode 8 bundle image is boot verified, the user confirmed its bundled
B8/checkerboard pattern, and the independent trace verifies final cache replies,
all nine ordered completion notifications, malformed-command rejection and clear.
The latest aggregate passes all **94 required stages**, including **222 Python**
and **79 Swift** tests. See [hardware evidence](../../analysis/bundle-native-20261102/report.json).

The local `~/dev/g2flash` checkout still matches the pinned commit and all 96 copied
files. The inventory freshness check passes. **21 required suite/integration
entries remain incomplete** at the file level; partial portable coverage does not
close their native adapter or hardware obligations. Full suite porting remains a
completion requirement. At that checkpoint only keyboard/HOGP was excluded;
see the expanded current hardware exclusions above. Preserve
original assertions and fixtures, test production MemoMind paths, and keep
`--require-complete` failing until those entries are closed. The exact remaining
list and acceptance criteria are in the [suite audit](../../analysis/bundle-native-20261102/g2-suite-port-audit.json).

## Executed coverage

Evidence: `analysis/g2-compat-tests-02/` (all C runs use AddressSanitizer and
UndefinedBehaviorSanitizer with recovery disabled).

Historical aggregate run before the keyboard scope change: `analysis/regression-20261101-07/report.json`.
All 75 required stages passed with no source drift:219 firmware/transport/client
tests (zero skips),56 native Swift tests with captured OTA replay, a read-only inventory freshness check, G2 compatibility,
geometry/RLE/vector comparisons, production scene/cache/notification/keyboard/
transport/policy tests, native text/display/input host checks, fresh RV32 builds,
and actual graphics/scene/input/flash-reader execution with explicit native mocks.
The extended reader, full-capacity transactional flash core and native reservation
boundary tests are also required, along with fixed storage diagnostics and actual
native badmap acquisition code. Six exclusive-store entry gates add 96 actual
RV32 rejection checks; they do not establish hardware storage ownership. The full portable flash-backed scene stage runs
the same fixtures with 256 KiB assets, 65,535-byte messages, rollback faults and
reader ownership checks. Native full-capacity integration remains pending.
The flash-reader checks replay emitted C and RV32 replies through the Python
client with fragmented GM framing. The current inventory maps every in-scope original orchestrator
stage to required local stages, with keyboard mappings explicitly optional; deleting a mapped stage fails the aggregate run.
`--require-complete` returned2 because the full upstream feature
port remains incomplete. All424 original shape/vector assertion sites passed
(42,466 evaluations). The original media also passes through the new scene
session at640×480 and at600×350 with the64KiB native store and modeled wire memory.
Out-of-panel pixel probes are explicitly omitted in the600×350 comparison.

| Suite | Result | What this establishes |
| --- | --- | --- |
| Original immediate geometry partition | 14 original assertion sites passed | Original 22-record geometry fixture and pixel expectations run against `runtime/portable/geometry.c` |
| Original easing tests | 69 assertion evaluations passed | Five original assertion sites exercise the unchanged copied easing functions |
| Original volume gate suite (optional reference) | Historically passed, 32 source assertion sites | Volume gating excluded; unchanged source retained |
| Six original C host reference binaries | All passed under ASan/UBSan | Separate G2 reference baseline |
| Full portable shape/vector suites | All424 original CHECK sites /42,466 evaluations passed | Actual portable scene/cache/asset/rendering implementation with explicit platform callbacks; native font callback pending |
| Portable notification relay | All9 original scenarios,76 unchanged CHECK sites /266 evaluations passed | Production queue/chunking/lease/control core; G2 hook/layout/action checks use a test-only shim and do not establish MemoMind ANCS integration |
| Portable keyboard (optional reference) | All6 original scenarios,86 unchanged assert sites /966 evaluations passed | Production control/event/queue/timer core; native MemoMind HOGP and ARM hook behavior remain pending |
| Portable record transport | All5 original scenarios and50 unchanged assert sites passed | Production record parsing, CRC, reset/context/reply behavior; host zlib and G2 outer framing/topology remain explicit test adapters |
| Portable upstream policies | All5 original scenarios,78 unchanged assert sites /25,620 evaluations passed | Extension parsing, settings composition, battery encoding, heading matching and link policy; native data/layout and controller bindings remain pending |
| Three original Bun test files | 21 tests, 5,770 `expect()` evaluations passed | Copied phone-side codec/algorithm fixtures; two outer G2 settings-wire cases remain platform-specific |
| Both original TypeScript configurations | Passed | Upstream vector and keyboard type checks |
| Generated vector fixture | 24 messages, 21 pixel probes passed | Separate G2 reference and production MemoMind scene/path replays |
| GIF and prepared SVG video | Each 302 messages, 7,200 pixel probes passed | Two 300-frame replays against both G2 reference and MemoMind portable production code; no on-device video claim |

The inventory contains 46 distinct C scenario groups, 21 named Bun cases and
8 ARM keyboard emulator scenarios. These are inventory counts, not MemoMind pass
counts. The vector binary also runs 16 shape scenarios; those inherited scenarios
are explicitly not counted twice. Assertion sites, scenario groups and repeated
loop evaluations are different counts.

All46 C host scenarios now have portable core coverage, preserving746 original
assertion sites across the seven host suites. Notification, keyboard, transport
and upstream-policy file rows remain platform-specific: their native-layout and
hook assertions use explicit test-only adapters. Their core coverage does not
complete the eight ARM machine scenarios or the remaining live harnesses.

`prepare_ports.py` reproduces the selected geometry tests from the
pinned sources. The geometry port retains the original geometry records and all
14 associated CHECK predicates; only the renderer call is adapted to the explicit
buffer API. Original 640×480 coordinates and pixel expectations remain unchanged.
The initial geometry partition omitted asset/font checks. The complete portable
scene suite now runs them with the original host font stub through an explicit
callback; native built-in glyph rendering remains pending. This is supplemented by the separate
828 byte-for-byte reference comparisons, 600×350 and 600×175 stride-320 tests,
padding/nibble sentinels and malformed packet checks in
`runtime/portable/tests/` (`analysis/portable-geometry-tests-03/`).

## Reproduction

Run from the repository root, using a new output directory:

```sh
python3 tests/g2_compat/prepare_ports.py
python3 tests/g2_compat/inventory.py --check
python3 tests/g2_compat/test_scope.py
python3 tests/g2_compat/run_tests.py --output /tmp/memo-g2-compat
```

The runner checks every copied source hash before compiling. It needs local
Clang with ASan/UBSan, host zlib, Bun and the existing installed dependency tree
at `~/dev/g2flash/demos/node_modules` (override with `--demos-dependencies`). It
copies that tree into the output directory and performs no install/download or
write to the G2 checkout. Copied dependency package versions/hashes are saved in
`dependency-versions.json`; the recorded run also has a complete dependency-file
hash manifest. The G2 checkout remained clean after the recorded execution.
The default runner runs the vector TypeScript check (keyboard is opt-in), generates the vector
fixture, and replays it and 300 GIF frames against the G2 reference runtime.
`--g2-media` defaults to `~/dev/g2flash/demos`; its `bad_apple_quarter.gif` is
required. Prepared `.cache/bad-apple/smooth/video.json` is optional and, when
present, adds a second 300-frame replay. Media is read without modification and
its hashes are recorded. These are G2 reference replays, not MemoMind rendering.

Normal exit 0 means the required offline checks passed. Missing required
dependencies fail with exit1. Use `--require-complete` for a parity gate: it exits 2
while required in-scope MemoMind coverage remains unimplemented/platform-specific;
failed builds/tests exit 1. Report JSON explicitly sets
`memo_full_suite_port_complete: false` and does not count skipped coverage as pass.

## Remaining coverage and dependencies

- Retained scenes, caches, assets, transactions, rollback, tweens, state, paths and
  rotations now run all original host assertions against the portable implementation.
  Their file rows are ported. Native allocator/timer/display integration, built-in
  font rendering and the device memory/stack budget remain separate boundaries.
- The notification relay now has a production portable core and preserves all
  nine original scenarios. The aggregate runner requires its sanitizer tests,
  independent public-API boundary/lifecycle tests and freestanding RV32 audit.
  Its file remains platform-specific because stock chaining, G2 ANCC layouts
  and action-handle validation use a test-only adapter. See
  `runtime/portable/NOTIFICATIONS.md` and the per-assertion inventory mapping.
- Record transport has a production portable core and required sanitizer/RV32
  stages, with original scenarios and predicates retained. Its native queue,
  transport and inflater bindings remain pending. Keyboard host/RV32 checks
  are optional reference; native HOGP integration is excluded from completion; G2 outer-wire and ABI checks are labeled test-only adapters.
  The upstream settings/sensor suite now also exercises production portable
  protocol/policy code. Its G2 stock import and memory-layout checks remain
  test-only adapters. MemoMind native settings read/write/readback behavior
  requires separate integration tests.
  Existing MemoMind RFCOMM/OTA tests are related coverage, not replacements for
  these tests.
- The upstream TypeScript checks and vector/GIF/prepared-SVG stages now execute
  as reference checks. The aggregate runner also replays the same hashed fixtures
  against the production portable scene/path implementation.
  The upstream Thumb build has a separate RV32 probe build/emulation counterpart;
  this does not establish a port of the full G2 runtime. Media preparation itself
  still requires ffmpeg/Potrace and is not performed by this runner.
- `vector_path_check.c` is an input-driven compiler harness, not a standalone
  registered test suite. Its portable counterpart matches291 original outcomes,
  including malformed input and edge limits.
- Optional reference only: the eight ARM keyboard emulator scenarios need pinned g2emu
  `f30527c0b7e6fa6e9be06e7067e49468197fa258`, Unicorn ARM, matching G2 images/build
  symbols and five hook witnesses. They cannot establish RV32 behavior. Separate
  actual MemoMind machine-code coverage lives in `tests/rv32/probe_emulator_test.py`
  and `analysis/rv32-probe-emulation.json`; it tests the runtime probe, not those
  keyboard scenarios.
- Live demos and probes require device-specific feature and transport adapters.
  None were run by this suite. No dedicated upstream `g2flash.py` unittest/pytest
  suite was found among tracked test/spec/check/probe paths; its embedded validation
  assertions are not described as unit-test coverage.

The geometry and retained-scene runtime has been flashed and exercised through
the native MemoMind display adapter. All24 vector fixture commands and both
302-command video sequences were accepted on hardware; independent OTA
reconstruction matches the candidate byte-for-byte. Physical scene/text visibility
still awaits user confirmation. Volume-gate and notification-core passes remain
host evidence. See `analysis/scene-hardware-verification.json`.


## Additional RLE boundary port

`inventory.json::portable_algorithm_boundaries` now maps the pinned decoder,
token parser and TypeScript encoder to `runtime/portable/rle.c`. The portable
runner additionally verifies378 reference-matching decode/encode cases,
1,048,560 token count/color combinations and20,000 adversarial stream comparisons
under ASan/UBSan (`analysis/portable-geometry-rle-tests-02/`). The original shape
asset fixture/mutation is preserved. The later full scene port also covers cache
transactions and asset lifetime under explicit host callbacks. RLE tests alone
do not establish native transport or live-video behavior.

## Vector compiler and raster port

The portable vector layer now executes16 unchanged original predicates directly
against MemoMind code (20,026 evaluations), with10,063 original compiler and483
original raster comparisons. The stdin path-check harness matches291 original
cases and is marked ported. `inventory.json` maps each preserved predicate's exact
expression/hash and original/portable source locations. The subsequent scene port now also covers all original scene/cache/timer
and lifecycle host assertions; native hardware callback bindings remain pending. See `runtime/portable/VECTOR.md` and
`analysis/portable-vector-tests-05/` for interfaces, sanitizer evidence and RV32
stack/import limits.


## Complete portable scene/cache host suite

The shape and vector file rows are now `ported`: all334+90 original CHECK
expressions and their order are preserved, with42,466 evaluations against
production `runtime/portable/scene.c`, geometry and vector modules. This includes
the complete original transaction/rollback/asset/tween/state/lifecycle/fuzz tests,
not only the earlier geometry/vector partitions. The original24-message vector
fixture and both300-frame media corpora also pass their pixel probes against
this implementation. `analysis/portable-scene-tests-03/assertion-map.json` is the
full source mapping; `runtime/portable/SCENE.md` gives the standalone runner,
platform callback contract and measured RV32 RAM/stack constraints. Native built-in
font rendering uses the same upstream host stub through a callback and remains a
pending device boundary. Full G2 hardware parity remains false.

## Text candidate offline checkpoint (2026-11-02)

All 105 required stages pass (223 Python and 89 Swift tests), with no source drift.
Mode15 adds 2,598 comparisons against actual extracted G2 text functions with
equivalent synthetic glyphs, plus compiled MemoMind RV32 tests. These supplement
the original suite; stub font fixtures are not relabeled as native text coverage.
That offline checkpoint preceded the completed hardware verification below. Native font metrics,
repertoire and missing-glyph handling differ from G2. The 21 incomplete original
suite/integration entries remain completion blockers; keyboard/HOGP is excluded.
See [offline text evidence](../../analysis/text-commands-001/report.json).

## Latest text command checkpoint (2026-11-02)

Mode15 is installed, boot verified and visibly confirmed. All 105 required stages,
223 Python tests and 89 Swift tests pass. Native text tests include 2,598 comparisons
against extracted original G2 rendering routines with equivalent synthetic glyphs,
plus actual compiled RV32 execution. The original shape-suite font stub is not
counted as native text coverage. See [text evidence](../../analysis/text-native-20261102/report.json).
All 21 incomplete suite/integration entries remain explicit completion blockers;
The exclusions at that checkpoint have since expanded as listed above. Native font appearance and
missing-glyph handling differ from G2.

## Fresh native regression builds

The aggregate runner verifies each rebuilt graphics blob against its manifest
and current source hashes before binding historical fixture runtime pins to it.
`tests/rv32/run_rebuilt.py` changes only digest assignments in module setup,
including conditional wrapper assignments. It leaves stock-image pins, test
bodies and assertions intact and records each binding in a sidecar report.
Direct fixture invocation retains its historical pins. Revision6 separately
updates the native diagnostic expectation for empty shapes: they present the
existing frame, while preserving its pixels and overlay cleanup checks.
