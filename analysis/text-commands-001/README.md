# Optional mode15 native resource text

Frozen runtime `runtime/build/text-commands-001/graphics.bin`:63,648 bytes, SHA256 `ab0f32b5a96264b8ee1c9f5faa4122a09b52c0d48d9f6404394c3ed927feded7`. The unchanged65,536-byte guard leaves1,888 bytes. `build.json` pins every source, flag, ELF segment, symbol and individual frame. `report.json` records scoped test results and changed-file hashes. No device/OTA/catalog operation was performed by this task.

Enable `--text-commands`, which requires `--command-bundles` and its existing raster/rectangle/scene prerequisites. The final profile retains input, reader, diagnostics and canary. Fresh compilation without text exactly reproduces the prior63,200-byte bundle runtime (`deeddff1533fc36c5468394a1fbbd612d3a2ec096dc864d963fa3cc30148f450`), with manifest here in `legacy-bundle-build.json`. Original binaries and tests/pins remain unchanged.

Wire is exactly `[0f or8f][x:s16LE][y:s16LE][options:u8][byteLength:u8][text bytes]`, total7+byteLength. Highbit is ignored. All lengths0..255 are supported; trailing/truncated payloads are invalid. UTF-8 scalar validation rejects NUL, overlong encodings, stray continuations, surrogates and values aboveU+10FFFF. DEL is a valid glyph token. Bytes1..31 adjust x by byte−11, including CR/LF; they do not introduce line breaks. The next glyph lookup skips these controls. Low4 option bits set intensity0..15;0x10 skips original zero-valued pixels before inverse;0x20 inverts then intensity scales with integer floor;0xc0 is ignored. Signed clipping and packed GRAY4 neighbors/padding are preserved.

Mode15 uses the existing MemoMind mapped-resource font adapter, not G2's incompatible ARM/LVGL glyph ABI. The default font chain supplies native metrics. Only the three already-proven mapped handles and supported1/2bpp static formats are accepted. Whole-string resource preflight rejects missing, unsupported or unavailable glyphs before any drawing. No fabricated glyph fallback is used. Native fallback glyph placement uses the resolved resource font's baseline. These differ intentionally from G2's advance-only missing glyph behavior and its root baseline treatment; actual font shapes/metrics are not claimed equal.

The session owns transient token scratch sized `4*max(byteLength,1)` bytes, at most1,020 bytes, plus the existing8-byte RV32 allocation header. Allocation respects the existing170KiB scene budget and48KiB free-memory reserve. Scratch is freed exactly once after synchronous rendering, before scene takeover; allocation failure returns `allocation-failed`. There is no large text-token stack array. Native resource/preflight failures return `invalid`. Existing retained shape text stays capped at128 bytes; mode15 alone adds255-byte input. Direct text that succeeds preserves the displayed shared background outside glyphs, stops retained animation, clears active ownership through the existing takeover and presents once. Invalid text preserves pixels and animation. Draw followed by takeover is safe for this serialized RAM adapter: its scene framebuffer aliases the native canvas, resync is a no-op and pending timer rendering is drained synchronously. This failure behavior deliberately improves on G2's takeover-before-validation order.

Bundles admit mode15/highbit15 with presentation suppressed for the child. Text leaves the final cache-reply scratch intact. Existing batch prepare, settled collector, final result ordering and one final presentation remain. Earlier successful children remain effective if later text fails, with no final presentation call; the shared-buffer visibility caveat remains. Tests exercise255 empty text children, text afterRESET retaining finalcache, text over an animated frame, and valid text followed by invalid UTF-8 with earlier effects retained.

Identity advertises mode15 in `modes` and `bundleModes`, `textMaxBytes:255`, `textFont:"native-resource"`, and `missingGlyph:"reject"`.

Validation:

* ASan/UBSan host runner extracts12 unchanged functions from the pinned G2 `texture_cache.c`/`utils.c`, validates source/function SHA values, and executes the actual builtin string function.2,598 differential cases use equivalent synthetic glyphs: Memo continuous2bpp `1b90` maps to G2 row-alignedA4 `05a0fa50`, equal lineheight4/baseline1/advance3. All256 options, signed clipping, every length0..255, every control1..31, all UTF-8 scalar widths, malformed encoding and exact-length rejection are compared. Actual native font baseline tests also run. Native graphics C uses only an injected font API; queue/request/scratch ownership, last-glyph failure and allocation failures are exercised under sanitizers.
* Five actual RV32 groups execute644 handler/session/timer calls, all256 option values, real font wrappers/parser/preflight/pixel loops,255-byte text, native format/bitmap/metrics failures, transient OOM/headroom, four-byte allocation alignment, full-frame background composition, animation continuation/takeover, source aliases and queue loss. Only external firmware/resource APIs are mocked.
* Retained gate7,955 cases, canary10groups, reader/diagnostics12, input6, scene8 and bundle7 pass against this exact binary. Scene changes only the capability assertion. Bundle changes only the capability assertions and removes15 from its unsupported-child fixture; new text tests cover malformed/failed15. Production Python clients validate emitted canary/read/diagnostic responses.
* Compiler prerequisite rejection passes four subcases before output directories are created. Independent review/extraction evidence is `analysis/text-command-review-20261102`.

Commands (new output paths required):

```
python3 runtime/graphics/tests/run_text_command_tests.py --output NEW_HOST_DIR
python3 scripts/compile_memomind_graphics.py NEW_BUILD_DIR --scene-session --input-observer --flash-reader --external-tail-reader --storage-diagnostics --full-store-reader --flash-canary --raster-commands --rect-copy --command-bundles --text-commands
.tools/rv32-tests-venv/bin/python tests/rv32/text_command_runtime_emulator_test.py --build NEW_BUILD_DIR --report NEW_REPORT.json
.tools/rv32-tests-venv/bin/python tests/rv32/text_command_existing_runtime_emulator_test.py --suite gates --build NEW_BUILD_DIR --report NEW_GATES.json
python3 scripts/test_compile_memomind_text.py
```

The retained wrapper also accepts `canary`, `reader`, `input`, `scene` and `bundle`. Fresh compiled binaries must match the literal final SHA. Aggregate integration is parent-owned.

New text helper frame176 bytes; native text frame144 bytes; session dispatch208 bytes. Observed synthetic stack maxima are64 bytes for BT and1,152 for display, excluding native callees, scheduler and interrupts. Tests establish no hardware timing, real glyph availability, radio delivery or whole-task stack guarantee. Native ingress8,192 bytes,64KiB RAM asset store and existing screen/launcher lease remain unchanged; this does not establish full G2 command/capacity parity.
