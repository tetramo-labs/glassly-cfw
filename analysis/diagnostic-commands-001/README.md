# Optional native diagnostics and implemented-session cleanup

Frozen runtime `runtime/build/diagnostic-commands-001/graphics.bin`:65,456 bytes, SHA256 `c1d8a1ffdd4f2799de4149d2e113527b29716886f6530549e56f68f61333d3b3`. The unchanged65,536-byte limit leaves80 bytes. The final `report.json` contains `passed:true`, exact runtime/build identity and `source_drift:[]`. No device/OTA/catalog operation was performed by this task.

Enable `--diagnostic-commands`, requiring the text/bundle/raster/scene profiles. The tested full profile includes the existing input, reader, storage diagnostics and canary. Only when diagnostic_commands is enabled, `diagnostics.c` gets `-Oz` and `runtime/graphics/graphics.c` gets `-Os`; flags are appended after the unchanged default `-O2` and recorded in the build manifest. Every other translation unit retains its old flags. Diagnostics-only `-Os` and then `-Oz` both produced66,256-byte links,720 bytes over the guard. Adding the conditional graphics override gave65,456 bytes. No guard, architecture, ABI, linker address or writable-section rule was relaxed. Fresh compilation without diagnostics exactly reproduces text-commands-001's63,648 bytes and `ab0f32b5a96264b8ee1c9f5faa4122a09b52c0d48d9f6404394c3ed927feded7`; manifest preserved as `legacy-text-build.json`.

Mode7/0x87 accepts a missing or unknown subcommand as success/no-op and ignores trailing bytes. Sub0 clears the sticky reorder/skip/duplicate flags, seen/resync/last/high,16-entry ring and supported failure counters. It preserves overlay visibility and saved epoch. Sub1 requests hide;sub2 requests show. None presents or immediately changes the current visible overlay. The next actual graphics presentation applies visibility. The lease-only empty geometry command still makes no presentation.

Frame tracking uses the exact original16-bit arithmetic and ring behavior: all16 slots initialize/reset to0xffff, so a first0xffff is a duplicate. Duplicates set the flag and return without changing last/high/ring/resync. Keyframes set seen/resync but retain the ring; the next nonduplicate delta rebaselines. Difference exactly0x8000 is a skip; greater is reorder. High is numeric maximum, not wrap-aware sequence ordering. IDs never suppress pixel drawing. Direct and bundled mode3/6 both feed tracking. As upstream, valid frame headers are recorded before RLE decode; malformed bounds/length/side dimensions never reach tracking, while an invalid RLE payload after a valid header can update tracking and the executed-dispatch failure count. Public input alias guards still run first.

Every successful mode7 response is:

```
{"glassly":"diagnostics","abi":1,"result":"ok","presentation":"unchanged","stateHex":"40 lowercase hex characters"}
```

The fixed20-byte little-endian `native-v1` snapshot is:

| Offset | Value |
| --- | --- |
| 0 | Flags:bit0 reorder,bit1 skip,bit2 duplicate |
| 1 | Requested hidden state,0 or1 |
| 2 | Seen,0 or1 |
| 3 | Resync,0 or1 |
| 4 | Last frame ID,u16 |
| 6 | Numeric high frame ID,u16 |
| 8 | Executed scene-dispatch failures,u32 |
| 12 | Token-workspace allocation refusals,u32 |
| 16 | Last failed raw command byte,including highbit |
| 17 | Reserved zero |
| 18 | Saved scene epoch,u16 |

Counters wrap as unsigned32-bit values. They collect only while diagnostic metadata exists and only at the actual scene-dispatch failure producers. They do not cover BT admission, queue loss, graphics owner/init failure, metadata/overlay allocation failure or JSON allocation failure. No NACK, mutex timeout, DWT timing, calibration, native heap maximum or latest-RX CRC field is fabricated. Allocation/native JSON failure can instead return the existing error/status path. Identity advertises `diagnostics:"native-v1"`, `snapshotBytes:20` and this full profile's `cleanup:"graphics-input-current-screen"`.

The display overlay is a separate80×18 packed image with a compact3×5 fixed glyph subset. Its rows show sticky R/S/D flags, hexadecimal last/high IDs (`F`/`H`), and hexadecimal supported failure counters (`W`/`A`). This is an explicit native presentation, not G2's Terminus font or complete diagnostics layout. Its palette and720-byte pixels belong to the diagnostic metadata allocation, never the scene/raster source. The metadata image is a hidden, source-less screen child. The visible overlay is a child of the CFW graphics image and naturally paints after it. There is no move-to-front/reorder call: the discarded approach could synchronously invoke an unproved screen callback.

Ownership is serialized on the display task. Overlay DELETE clears the metadata's weak pointer. Metadata DELETE first deletes any live overlay while its callback userdata is still valid, then invalidates/frees its private buffer. Graphics DELETE recursively deletes the visible child after its own DELETE callback; that child refers only to independent metadata, never the freed graphics owner. Both screen sibling deletion orders are tested. The existing graphics lease/launcher/screen timer naturally removes visible children. Hidden metadata has screen-object lifetime without a new timer; destroying that screen frees it. Native callbacks, class behavior and painter ordering are documented in `analysis/diagnostics-cleanup-review-20261102`.

Mode11/0x8b ignores trailing bytes and idempotently disposes the implemented graphics scene, assets, canvas, timer and input subscription, then hides the overlay. It retains hidden diagnostic history for the same screen object. There is one scene disposal/epoch increment: the later DELETE callback sees initialized=0 and performs no second release. Saved epoch is restored on a later graphics owner. Zero-epoch RESET then increments again; an explicit nonzero RESET still selects the caller's epoch, as upstream. Persistence is best-effort if metadata must be allocated during cleanup and allocation fails; cleanup still releases graphics/input. Repeated cleanup with no graphics owner does not advance the saved epoch. This is not G2 singleton lifetime or complete mode11 parity: screen destruction discards metadata/history/epoch, and future compass/raw-IMU/ALS/audio/notification controllers are not stopped by imaginary bindings. The unrelated one-shot canary worker is not canceled.

Validation:

* ASan/UBSan standalone host tests execute the exact pinned G2 `cfw_diag` function and mode7 branch:100,000 generated transitions plus sentinel/wrap/half-range/ring/reset edges and all256 subcommand bytes. Separate ownership tests cover deferred visibility, both sibling deletion orders, recursive weak-pointer clearing and allocation/callback registration failure. This host layer does not claim full graphics/input integration.
* Four actual RV32 groups execute152 calls through the real optimized graphics code, frame hooks, diagnostic core/native wrappers and cleanup. They verify snapshots, direct/bundled frame IDs, malformed admission versus valid-header/bad-RLE tracking, mode7 no-ops/trailing/highbit, real graphics framebuffer snapshots before/after overlay/copy/hide, input cleanup, epoch/history/idempotence, actual nested DELETE callbacks in both orders and overlay creation failure. External native APIs and LVGL tree/scheduling are explicit mocks.
* Retained gates7,955cases,canary10groups,reader/diagnostic12,input6,scene8,bundle7,text5 pass on the exact new binary. Mode11's new input cleanup expectation is explicit. Retained cleanup assertions permit only one tagged hidden diagnostic metadata allocation, verify it is the sole surviving owned block, then execute its DELETE callback and require zero owned allocations. The old bundle alias fixture still checks session/core-owned regions; separately owned diagnostic metadata is excluded from that core-only fixture and its ownership is independently checked. Production Python clients validate retained canary/read/diagnostic responses. Nine compiler guard/dependency tests pass.

Stable runners:

```
python3 runtime/graphics/tests/run_diagnostic_command_tests.py --output NEW_HOST_DIR
python3 scripts/compile_memomind_graphics.py NEW_BUILD_DIR --scene-session --input-observer --flash-reader --external-tail-reader --storage-diagnostics --full-store-reader --flash-canary --raster-commands --rect-copy --command-bundles --text-commands --diagnostic-commands
.tools/rv32-tests-venv/bin/python tests/rv32/diagnostic_command_runtime_emulator_test.py --build NEW_BUILD_DIR --report NEW_REPORT.json
.tools/rv32-tests-venv/bin/python tests/rv32/diagnostic_command_existing_runtime_emulator_test.py --suite gates --build NEW_BUILD_DIR --report NEW_GATES.json
```

The retained wrapper also accepts `canary`, `reader`, `input`, `scene`, `bundle` and `text`. Fresh builds must match the literal final pin. No previous suite/pin/artifact was edited.

Diagnostic control frame208 bytes, overlay present32 bytes, metadata/child DELETE16 bytes each. Observed synthetic stack maxima are80 bytes for BT and1,120 for display, excluding native callees, interrupts and scheduler frames. Native generic allocation may still assert; free-memory admission is not a largest-block or concurrency guarantee. These offline tests establish no physical panel, actual hardware timing, transport delivery or complete-task stack proof. Existing8,192-byte ingress and64KiB native RAM asset store remain unchanged.
