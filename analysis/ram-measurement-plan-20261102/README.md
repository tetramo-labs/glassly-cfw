# Read-only heap measurement

The installed `diagnostic-commands-001` exposes current free heap and low-water accounting through service15, command0x7e, empty body. It does not expose largest free block. The ordinary Swift CLI `probe` only requests heartbeat and device information; it does not fetch these capabilities.

Root can run this compiled native Swift helper from the repository root, using a new output directory:

```sh
analysis/ram-measurement-plan-20261102/measure NEW_CAPTURE_DIRECTORY
```

The helper has **not been executed by this reviewer**. It loads the exact catalogued OTA, checks the runtime and256-byte expected app-header hashes before opening normal RFCOMM to `4C:3C:8F:90:CC:C3`, probes identity, requires firmware1.0.3.127, reads and exactly compares the installed app header, and takes ten capabilities samples. It pumps the main run loop for approximately0.5 seconds between queries. New output contains durable raw `trace.jsonl`, `device.json`, `header-reply.json`, ten `capabilities-NN.json` files and a summary `result.json`. There are no retries. On an error, it records failure and closes transport without asserting completion.

The shortest query sequence after opening normal SDP service7033 is:

1. `GMSession.probe()`: event1/service1/command1 heartbeat, then event2/service1/command2 device information.
2. Pinned-header check: service15/command0x7b with one BYTES TLV containing `01 00 00 b0 1e 00 00 01`. This reads256 bytes from device0, physical0x1eb000.
3. Fresh event/service15/command0x7e with **empty body**, not a zero-length BYTES TLV. Parse one JSON TLV kind5, at most1024 bytes, remove at most one final NUL, validate exact installed canonical capabilities including eight lowercase hexadecimal digits for each heap field.

The helper uses the same checked transport and exact capability comparison as frozen `analysis/diagnostics-native-20261102/smoke-v2.swift`, stopping before any graphics commands. `responseFilter` rejects duplicate accepted responses in the same read, event/service/command correlation is enforced by `GMSession`, and unexpected service15 notifications poison subsequent reads/writes. It does not send mode11 cleanup, scene RESET, display commands, observer subscription, pre-OTA notification, or flash mutation. The complete smoke and cleanup helpers are **not** substitutes for this read-only measurement.

Native `P.free_bytes` binds `uint32_t 0x0433c460(void)`, which sums current-free accounting from the five pool descriptor slots0x0205d5f8..0x0205d648. `P.low_water_bytes` binds `0x0433c4a4`, summing each initialized pool's minimum-free accounting. Each call uses its own critical section; the pair is not atomic. Neither is largest-block telemetry. Source witnesses are pinned in `report.json`.

The canary-derived diagnostic build allocates its740-byte JSON template **before** sampling and frees it after constructing the response. The allocator's actual charge may include metadata/alignment. Connection traffic and response construction also perturb the heap. Low-water is historical and need not recover when objects are freed. Compare current free values under matched screen/activity/connection conditions; do not equate an arbitrary sample difference with an owner's allocation size. Prior diagnostic captures contain332452..333628 current-free bytes and99496..315904 low-water bytes; these are historical, not the new sample set.

## Future native Swift firmware admission

`EligibleFirmware.load(data:expectedSHA256:)` accepts only literal internal `FirmwareRelease.catalog` entries. An explicit SHA or external manifest cannot admit a new release. Admission requires an independently reviewed, exact reconstructed candidate first, then a new literal release plus stream variant and fixture tests in `FirmwareImage.swift`/`FirmwareImageTests.swift`; root owns those edits. Preserve every old entry and test. The existing `analysis/diagnostics-native-20261102/admit-candidate.py` demonstrates the process but is release-specific, already executed, and must not be rerun or mechanically reused against a different profile.

Before admitting a future image, freeze source/build hashes; verify fixed compiler profile, exact entry/gate addresses, no imports/writable sections/relocations, static stack guards and native behavior tests; reproduce the complete OTA and decoded component checksums from the exact known source and fixed constructor; verify hook/owner/registry witnesses and unchanged other components; enforce2MiB app allocation and raw plus4096-rounded0x25e000 staging limit. Pin image byte count/SHA,150-byte outer/table header SHA and all seven compressed stream offsets/sizes/raw lengths/ranges/hashes. Pin the separate first256 decoded app bytes for post-flash identity. New Swift catalog tests should load the required exact fixture and reject alterations. Build and link fresh Core objects, with their hashes, before using the new helper.

The RX96 profile is currently offline-only. It needs separate reviewed admission; a manifest does not grant that authority. Its current demonstration bytes are identical to the existing diagnostic release, which retains its existing eligibility. No larger executable hardware claim follows.

Root's deployment preflight should establish exact target model/hardware/front/MAC and currently installed header/capabilities, match the reviewed candidate and source, preserve required external backup/topology/badmap ownership evidence when a candidate retains flash-writing features, and keep the control link alive through OTA. `notifyOTA` and OTA `check` alter transient updater state; they are not part of this read-only helper. Modified images require fresh offset18, bounded responses, no speculative retry, and the explicit write gate. After transfer/reboot, verify the new app-header bytes and capabilities before new behavior. Catalog admission alone does not prove boot or runtime safety.

Compile command used (no SwiftPM build or radio access):

```sh
swiftc -I swift/MemoMindKit/.build/out/Products/Debug analysis/ram-measurement-plan-20261102/measure.swift swift/MemoMindKit/.build/out/Products/Debug/MemoMindCore.o swift/MemoMindKit/.build/out/Products/Debug/MemoMindBluetooth.o -framework IOBluetooth -o analysis/ram-measurement-plan-20261102/measure
```
