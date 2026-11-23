# Swift compass and ALS command encoders

Encoding-only APIs are complete and sources frozen. The current MemoMind firmware does not support mode10 compass or mode16 ALS. No runtime/capability/catalog/bundle implementation changed and no hardware action occurred. Raw IMU has no agreed protocol; none was invented.

```swift
SensorCommands.compassStop() // 0a00
SensorCommands.compassStart() // 0a01: distinct stock-default start
try SensorCommands.compassStart(intervalMilliseconds: 1000, minimumChange: 5)
SensorCommands.alsQuery() // 1000
SensorCommands.alsStop() // 1002
try SensorCommands.alsStart(intervalMilliseconds: 500, minimumDelta: 1,
    heartbeatMilliseconds: 5000, bindToFramebufferLease: false)
```

Configured inputs must fit UInt16 (0...65535), using Int arguments so invalid negative/oversized values throw rather than silently truncate. Their original little-endian bytes are preserved. G2 subsequently clamps compass intervals to50...2000ms and ALS intervals to100...5000ms. Minimum-change and minimum-delta values are raw; this API assumes no heading/ALS physical units. ALS heartbeat0 disables time-only reports. The ALS Boolean emits only lease flag0/1; equivalent native MemoMind ownership is not established.

Canonical compass op0/op1 is2 bytes; op2 is6 bytes. G2 op2 truncation is invalid; trailing bytes and mode highbit are ignored. Starting sets forwarding; native start/config errors clear it, and config failure calls stop. This is verified with callback mocks, not native sensor setup. The stock-default op1 makes no explicit config call (source comment documents1000ms/5 minimum change).

Canonical ALS query/stop is2 bytes; start always9 bytes. G2 also accepts partial start headers: flags defaults0; interval/minDelta/heartbeat defaults500/1/5000 unless both bytes of each pair exist. Odd incomplete low bytes are ignored. Reserved flags are stored upstream, but only bit0 is used by the lease predicate. Highbit/trailing bytes are ignored. On a non-master G2 lens, ALS returns success before checking the operation; this is a historical routing behavior, not a MemoMind single-display/sensor mapping. Query reads existing globals and does not prove a new sensor measurement. Native report bodies, calibration, sensor setup, lease/brightness ownership, cleanup and raw IMU remain outside these encoders.

Validation:

- Five Swift test methods pass:19 independent byte fixtures, explicit default/op distinction, heartbeat0, representative UInt16/LE boundaries, each negative/overflow parameter, canonical mode/size and continued bundle rejection for10/16 and their highbit variants.
- 5404 pinned original C control checks pass. The oracle extracts the unchanged mode10 dispatcher, mode16 dispatch branch, complete als_control and the exact clamp/store prefix of als_passive_start. Hardware callbacks/context/ALS hook installation/open/report side effects are mocked or explicitly excluded. Cases cover all operation bytes, both mode heads, missing/trailing/partial fields, all256 raw ALS flags, master/non-master/context absence and compass start/config failure rollback.
- Three primary source files are pinned against tests/g2_compat/UPSTREAM.json at commit1a6db4fd75de202a96599cc8f9f12fa721e7c3ce: zlib_glue.c, compass.c and als_sensor.c. Extracted region hashes and precise mock boundaries are in reference.json. compass.c supplies report/ownership context; no heading decoder or sensor binding was added.
- The pinned demos TypeScript files were searched for named compass/ALS/ambient controls; no dedicated sensor sender fixture was found. Fixtures therefore derive independently from the primary C wire contracts using struct.pack and are checked by the unchanged original parser branches, rather than treating unrelated numeric arrays as sensor recipes.

Commands:

```sh
python3 analysis/sensor-swift-20261102/generate_reference.py
swift test --package-path swift/MemoMindKit --scratch-path /tmp/mm-swift-sensor-tests --filter SensorCommandsTests
```

Generator writes only its analysis reference files and new SensorReferenceVectors.swift. MIT provenance is retained, with LICENSE. These checks establish encoder/control-byte compatibility only; no runtime support, physical sensor behavior, actual G2 memory layout, host callback threading or new MemoMind capability is claimed.
