# Optional mode8 command bundles

Frozen runtime `runtime/build/bundle-commands-001/graphics.bin`: 63,200 bytes, SHA256 `deeddff1533fc36c5468394a1fbbd612d3a2ec096dc864d963fa3cc30148f450`. The adjacent `build.json` pins source inputs, flags, ELF/map/symbols and individual frames. The 65,536-byte limit remains unchanged. No device, OTA or catalog operation was performed by this task.

Enable `--command-bundles`, requiring `--rect-copy`, `--raster-commands` and `--scene-session`. The tested artifact retains input, full reader, diagnostics and canary. A fresh build without the new flag exactly matches the prior 62,240-byte rectangle-copy binary (`c2c702f42d92e0b1dccc99e647f4038c391305e0b1ec642ded205c1a6c30dca7`); its complete manifest is retained here as `legacy-rect-build.json`.

Wire: `[08 or 88][count:u8]` followed by `count` segments `[length:u16LE][command bytes]`. Length must be positive and fit the remaining input. Count0 is valid; trailing outer bytes are ignored. Subcommands are admitted by `command[0]&127`: modes3,6,9,19,20,36,37,38,39,40,41. Mode15 is explicitly unsupported, as are nesting and control commands. Highbit3/9 selects the first/left rectangle set; highbit6 is ignored. Other supported highbits are normalized before dispatch. Each child retains its full existing semantic validation.

The session prepares the whole batch once, dispatches children sequentially with presentation disabled, then presents once on complete success (including count0). A late failure keeps earlier pixels/cache changes and does not make that final presentation call. There is no transaction rollback or invisibility promise: LVGL shares this pixel buffer, so another refresh could expose changed pixels. Individual malformed raster commands remain validated before their own takeover/write, but prior valid children can already have changed state.

Cache replies follow the pinned G2 implementation exactly: clear scratch at bundle entry; each cache mode37..41 clears/replaces it; raster modes leave it alone. Only the final scratch is returned, and only if the entire bundle succeeds. This is not a stream of per-child replies. A later cache command with no reply clears the previous one. The host test exercises this using a deliberately small public reply capacity.

Settled notifications use a separate transient collector. Before prepare or any child effect, the native display handler allocates `2*count` uint16 slots (at most1,020 bytes), retaining the existing32KiB free-memory reserve. Count0 needs no allocation and preserves a pending animation tag. With serialized display execution, each pending tag is consumed once and only SHOW/HIDE can create another, giving at most `count+1` emissions; `2*count` is sufficient for nonzero count. Tests reach256 ordered tags from255 children plus an initial pending tag, and exactly2 tags from one child. Duplicates and order are retained. On success or failure, the correlated result is sent first, followed by each collected tag, then the collector is freed once. Allocation failure occurs before prepare/dispatch. An explicit overflow guard suppresses final presentation and reports an error rather than silently truncating. Native send has no exposed result: tests establish call order and local ownership, not radio delivery guarantees. This deferred notification order is the existing MemoMind adapter policy, unlike G2's immediate callbacks.

Production edits are limited to conditional paths in `runtime/portable/scene.c/.h`, `runtime/graphics/scene_session.c`, `runtime/graphics/graphics.c` and `scripts/compile_memomind_graphics.py`. The new `mm_scene_immediate_mode` normalizes bundle19/20/36 without modifying request bytes; the default build retains its original implementation. Existing input alias guards cover session/core/frame and all owned allocations before prepare. No extra framebuffer or persistent native global is introduced.

Scoped validation is summarized in `report.json`:

* ASan/UBSan host tests extract and compile the exact pinned G2 mode8 branch, compare envelope/truncation/trailing/presentation behavior, exercise all unsupported submodes, sequential pixels, late failure, final scratch,255-segment collection, duplicate tags, admission/JSON failures and cleanup.
* Seven actual RV32 groups execute real gates, C, native wrappers, scene/cache/RLE/copy instructions with only external firmware APIs mocked. They cover all supported submodes/highbits, cached image/font assets, late asset persistence, one presentation, animation takeover, empty pending state,255 segments, allocation/headroom failures, input ownership and every core-owned alias span.
* Retained gate, canary, reader/diagnostic, input and scene suites run against this same pinned binary. The scene suite changes only the identity mode list; original rendering, font, animation, alignment, malformed-request, budget and lifetime assertions remain. Production strict clients check emitted canary/read/diagnostic responses.
* Compiler dependency tests reject invalid flag combinations before creating output directories. Independent review: `analysis/bundle-review-20261102/report.md`.

Commands (use new output paths):

```
python3 runtime/graphics/tests/run_command_bundle_tests.py --output NEW_HOST_DIR
python3 scripts/compile_memomind_graphics.py NEW_BUILD_DIR --scene-session --input-observer --flash-reader --external-tail-reader --storage-diagnostics --full-store-reader --flash-canary --raster-commands --rect-copy --command-bundles
.tools/rv32-tests-venv/bin/python tests/rv32/command_bundle_runtime_emulator_test.py --build NEW_BUILD_DIR --report NEW_REPORT.json
.tools/rv32-tests-venv/bin/python tests/rv32/command_bundle_existing_runtime_emulator_test.py --suite gates --build NEW_BUILD_DIR --report NEW_GATES.json
python3 scripts/test_compile_memomind_bundles.py
```

The retained wrapper accepts `gates`, `canary`, `reader`, `input` and `scene`. Fresh compilation must match the literal new pin. No previous pin or immutable artifact was changed. Aggregate integration is parent-owned.

Limits remain:8,192-byte native ingress,64KiB RAM asset store,170KiB scene allocation budget, existing launcher/screen lease and native task sizes. Maximum count255 is an envelope bound, not a real-time guarantee. Synthetic stack measurements exclude native callees, scheduler and interrupt frames. Native firmware APIs are mocks in these tests; physical flash, timing, radio delivery and panel behavior are not established here. This slice does not claim mode15, all command parity, full256KiB native asset capacity or arbitrary compressed ingress.
