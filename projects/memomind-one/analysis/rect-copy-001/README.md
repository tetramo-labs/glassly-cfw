# Optional mode9 rectangle copy

Frozen runtime `runtime/build/rect-copy-001/graphics.bin`:62240 bytes, SHA256 `c2c702f42d92e0b1dccc99e647f4038c391305e0b1ec642ded205c1a6c30dca7`. The adjacent `build.json` pins all source inputs, flags, ELF map/symbols and frame sizes. `report.json` here records changed sources and scoped validation. No device/OTA/catalog operation was performed by this task.

Enable `--rect-copy`, which requires `--raster-commands` and therefore `--scene-session`. The tested artifact retains input/fullreader/diagnostics/canary. Fresh compilation without the new flag remains byte-identical to the installed raster-commands-001 binary. It adds mode9 to identity only when enabled; the existing `rasterLens:"first-left"` policy applies.

Wire: `[09][source x,y,w,h:u16LE][destination x,y,w,h:u16LE]`, minimum17 bytes. Both selected rectangles must be positive, equal-sized and wholly inside the validated raster, with no clipping. `89` requires33 bytes and uses only the first/left16-byte pair; the unused second pair is ignored, even if invalid. Arbitrary trailing bytes are accepted, matching the original. Coordinates/size are full unsigned16-bit values, not mode3's scaled8-bit geometry. Self-copy and all overlaps are accepted.

`runtime/portable/rect_copy_commands.c/.h` provide validation and drawing separately. Whole-byte copies use directional byte loops in place of libc `memmove`; odd-coordinate/width copies preserve neighboring nibbles with directional pixel loops. Source/descriptor/frame aliases, integer-span overflow, malformed dimensions and bounds are rejected before writes. No additional allocations or canvas are needed. Native session uses the existing all-owned-allocation input guard, then validates before scene takeover. Valid copy freezes/hides retained active objects without freeing their cache, operates on the currently displayed shared buffer, and presents once; laterSHOW can use those objects again. Malformed copy neither changes pixels nor stops animation. This validation-first behavior intentionally hardens the original, which took over before mode-specific validation. No mode8 bundle behavior is implied.

Validation passed:

* 26227 ASan/UBSan host cases compare the exact function extracted from pinned G2 `draw.c` against production code and an independent snapshot copy model: overlap in every direction, same row/column, self-copy, odd source/destination/width, odd raster size, row padding/sentinels, full600×350 surface, edge equality,16-bit values, malformed lengths/fields, highbit unused-right data, trailing data, aliases and native queue/presentation/cleanup.
* 3 actual RV32 groups execute real native/C/session/copy instructions, with only external firmware APIs mocked. They include the planned129×115 source99,99→301,99 and63×31 source100,180→101,181 copies, actual RLE/checkerboard initialization, snapshot verification, one presentation/no new scene allocation, malformed-animation continuation, valid-copy takeover/deferred settled, all owned-core alias spans, request/queue lifetime, headroom/queue loss and expiry.
* 7955 actual gate cases pass. Retained new-address canary10groups, reader/diagnostics12groups and input6groups pass on this exact binary; strict production Python clients validate canary/read/diagnostic emitted responses. Canary flash/task APIs remain mocks, with no real mutation.
* Compiler prerequisite rejection passes three subcases before any output directory is created. Independent source review is `analysis/rect-copy-review-20261102/report.md`.

Commands:

```
python3 runtime/graphics/tests/run_rect_copy_tests.py --output NEW_HOST_DIR
python3 scripts/compile_memomind_graphics.py NEW_BUILD_DIR --scene-session --input-observer --flash-reader --external-tail-reader --storage-diagnostics --full-store-reader --flash-canary --raster-commands --rect-copy
.tools/rv32-tests-venv/bin/python tests/rv32/rect_copy_runtime_emulator_test.py --build NEW_BUILD_DIR --report NEW_REPORT.json
.tools/rv32-tests-venv/bin/python tests/rv32/rect_copy_existing_runtime_emulator_test.py --suite gates --build NEW_BUILD_DIR --report NEW_GATES.json
```

The last runner also accepts `canary`, `reader` and `input`. New-build tests require the exact literal SHA pin; no prior suite or pin was changed. Aggregate integration is parent-owned and not edited here.

New primitive frame sizes are32 bytes for parsing,48 for validate and80 for draw; scene dispatch remains192 bytes. Recorded synthetic4KiBBT/8KiBdisplay stack measurements exclude native internals/interrupts. Hardware timing, complete command parity, full256KiB native asset capacity and safe arbitrary compressed ingress are not established. Native message cap8192, scene store64KiB and1000-tick launcher/screen lease remain unchanged.
