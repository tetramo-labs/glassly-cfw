# Fixed RX allocation profiles (offline)

`app-rx-64k-v1` remains the implicit default. The explicit `app-rx-96k-v1` profile selects the fixed 96 KiB linker and constructor bound. Neither a numerical caller limit nor a manifest can enlarge the allocation. Both profiles retain ENTRY `0x0439bea0`, display gate `0x0439bee0`, one file-backed RX segment, no writable sections/imports/relocations, and the 512-byte static function-frame policy. That frame policy is not a whole-task stack bound.

The shared API is the keyword `rx_profile` on `compile_graphics`, `inspect_elf`, `construct_graphics`/`verify_graphics`, `construct_exclusive_storage`/`verify_exclusive_storage`, `construct_exclusive_reader`/`verify_exclusive_reader`, and `construct_canary`/`verify_canary`. Each corresponding CLI accepts only the two literal names through `--rx-profile`. Verifiers never select a profile from untrusted manifest data. Existing default manifests are unchanged. RX96 manifests have a distinct `-rx96` format suffix, fixed profile/limit fields, and `live_flashing_enabled:false`; no live admission or catalog change was made.

The new `diagnostic-rx96-001` runtime and offline OTA contain exactly the same bytes as the existing diagnostic release. This task establishes policy and boundary infrastructure, not new device execution. The current 65,456-byte runtime leaves 32,848 bytes under the new limit. Real synthetic RV32 linker fixtures exercise 65,536, 65,552, 98,304 and 98,320 bytes. Actual captured OTA construction exercises the same boundaries and independently enforces compressed staging capacity. Future code still needs per-image compilation, lifecycle tests and exact OTA reconstruction.

At the maximum 96 KiB length, append physical end is `0x003b3ea0`, erase-rounded end `0x003b4000`, within the unchanged app allocation ending `0x003eb000`. This leaves 225,632 raw bytes or 225,280 bytes after erase rounding. This consumes unused application allocation; it does not reclaim dashboard code/assets or RAM. Replacing stock dashboard functionality remains a separate possible workstream, not a compatibility requirement imposed by this profile. The historical proposed device0 mutable tail is not admitted.

Validation:

```sh
python3 -m unittest discover -s scripts -p test_memomind_rx_profile.py -v
python3 -m unittest discover -s scripts -p 'test_*memomind_graphics.py' -v
python3 -m unittest discover -s scripts -p 'test_build_memomind_*storage.py' -v
python3 -m unittest discover -s scripts -p test_build_memomind_flash_canary.py -v
.tools/rv32-tests-venv/bin/python tests/rv32/diagnostic_command_existing_runtime_emulator_test.py --suite gates --build runtime/build/diagnostic-rx96-001 --report NEW_GATE_REPORT.json
python3 analysis/rx96-profile-20261102/reproduce.py NEW_REPORT.json
```

Build (new output directory required):

```sh
python3 scripts/compile_memomind_graphics.py NEW_BUILD --rx-profile app-rx-96k-v1 --scene-session --input-observer --flash-reader --external-tail-reader --storage-diagnostics --full-store-reader --flash-canary --raster-commands --rect-copy --command-bundles --text-commands --diagnostic-commands
python3 scripts/build_memomind_flash_canary.py captures/firmware/ota-1.0.3.127-glassly-text.bin NEW_BUILD/graphics.bin NEW_OFFLINE_OTA --rx-profile app-rx-96k-v1
```

No device operations were performed. Gate emulation executes actual RV32 instructions with native and C gate targets mocked. The report pins changed sources, all compiler inputs, runtime, ELF and manifest; `source_drift` is empty.
