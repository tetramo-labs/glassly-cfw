# Optional bounded flash acquisition profile

This profile adds **read-only** acquisition to the existing scene+input runtime.
It is installed and has completed835 bounded hardware reads, including repeated
matching metadata snapshots. The app header matches the built candidate, and
the captured boot image body CRC verifies. See
[hardware verification](../../analysis/flash-read-hardware-verification.json).
It exposes no erase, program, reservation, protection, initialization, arbitrary
pointer or fallback-address interface. No mutable flash space has been reserved.

Build:

```sh
python3 scripts/compile_memomind_graphics.py runtime/build/CHOSEN-NEW-DIRECTORY \
  --scene-session --input-observer --flash-reader
```

`--flash-reader` requires both other flags. With it absent, graphics7808B, scene44592B and input49248B rebuild byte-identically to their pinned originals; see [unchanged-profiles.json](../../analysis/flash-read/unchanged-profiles.json). Existing emulator pins and profiles were not changed. The optional identity field is `"flashRead":123` in the passive probe response. Only service15 command`0x7b` reaches `glassly_flash_read_command`; the display gate and observer never call it.

Current compiled candidate is `runtime/build/flash-read-001/graphics.bin`,50,880 bytes, SHA256 `d162d7c2f93ac57618f7756260e2b9c945313c160e6874517f98a8202777ca1b`. It fits the existing64KiB extension bound and has no writable sections, unresolved symbols or runtime relocations. The service gate uses58 of its fixed64 bytes and retains ordinary tail forwarding without extra stack. This profile does not reserve any flash tail space.

## Wire contract

One request contains exactly one BYTES TLV, with no following node. Native extraction rejects null lists, null data, other TLV types and additional nodes. The normal service dispatcher supplies the response pointer and event pointer; a missing event pointer is rejected. The handler copies scalar arguments and releases the request through its address before allocation or the native read. Query/read replies use the normal synchronous response slot, not the display queue or an unsolicited sender.

| Request bytes | Action |
| --- | --- |
| `[00]` exactly1 byte | Query fixed profile/ranges; no native flash call. |
| `[01,device:u8,offset:u32le,length:u16le]` exactly8 bytes | Read1..256 bytes from a256-aligned physical offset in one permitted range. |

Fixed half-open allowlist:

| Device | Physical offsets | Purpose / evidence |
| --- | --- | --- |
|0|`[0x00000000,0x00010000)`|First64KiB internal flash below supplied partitions. Resident boot contents are not yet established.|
|0|`[0x001eb000,0x001eb100)`|Current app header and beginning of its body. Native existing32-byte header read corroborates address; this profile explicitly permits the first256-byte page.|
|0|`[0x007fc000,0x007fe000)`|Two native bootmap sectors.|
|1|`[0x00500000,0x00510000)`|First64KiB directory/journal of the managed external CUS8 store; not package payload or free storage.|

The reader checks nonzero length<=256 and offset alignment first, then `offset>=begin && offset<end && length<=end-offset`. No addition of untrusted offset+length is used. Device0/1 are explicit, and the full read must fit one range. XIP/unified aliases, cross-device reuse and all other selectors/addresses are rejected. In particular, device1 receives **0x00500000**, not the unified0x01500000 or XIP0x05500000 alias.

Query JSON:

```json
{"glassly":"flash-read","abi":1,"result":"ok","profile":"H001Y-1.0.3.127","maxRead":256,"alignment":256,"ranges":[{"device":0,"start":0,"end":65536},{"device":0,"start":2011136,"end":2011392},{"device":0,"start":8372224,"end":8380416},{"device":1,"start":5242880,"end":5308416}]}
```

Successful read JSON contains exactly `glassly`, `abi`, `result:"ok"`, `device`, `offset`, `length`, and lowercase `hex` of exactly twice the requested length. Numbers are decimal. Failure JSON has only the discriminator,abi and `result`, one of `invalid`, `allocation-failed`, `read-failed`. If native JSON construction returns null, the existing STATUS4 fallback is attempted; a null fallback remains a null response. There are no partial data replies or automatic retries. Host timeout/disconnect does not cancel an in-flight native read.

## Native ownership and resource bounds

[App-tail acquisition proof](../../analysis/ghidra/app-tail-store/report.md) establishes the exact ABI:

```c
int native_read(uint32_t device, uint32_t physical_offset,
                void *owned_destination, uint32_t length); /* 0x04329ad8 */
```

`native.c` adds a separate conditional helper, without changing `mm_graphics_platform`. Its actual RV32 tail wrapper forwards the four arguments unchanged to04329ad8. Native success is exactly0; any other return produces `read-failed`. The verified driver serializes through04329912/0432994a and reads via0432957e/04329460/020081da; no erase/program/write-enable routine belongs to that read chain.

Every read allocates exactly1024 bytes: raw256 plus JSON768. Raw bytes are initialized to zero before the driver call. Arguments and formatter bookkeeping remain on a small stack frame. The largest reply has at most512 hex characters, three bounded integers and fixed text, below768 bytes. `P.json` copies synchronously; workspace is freed exactly once after response construction, or before constructing a static error on native failure. Request memory is no longer live when the driver begins. Query has no owned workspace.

After request release, query requires reported free heap>=32768+1024; read requires>=32768+2048, covering the workspace plus a bounded response allowance. This is a preflight headroom check, not a reservation against other tasks' allocations. Native response helpers can still assert on OOM as previously documented; the lower owned allocator is the existing nonfatal try allocator.

The compiled reader frame is96 bytes; native helper frame0. The identity probe's frame is480 bytes, below the compiler's512-byte per-function limit. Actual RV32 tests measured96 bytes for reader execution on a synthetic4KiB BT stack, excluding external firmware call frames/interrupts. **No cumulative task-stack guarantee or watchdog/timeout guarantee is claimed.** Native controller busy loops have no proven software timeout. The handler must execute in the initialized normal BT service context and must never be transplanted into an interrupt, observer, display callback, or caller holding an incompatible native flash lock.

The [native store evidence](../../analysis/ghidra/native-store-capacity/report.md) proves CUS8 device1 mapping and a64KiB directory with eight8192-byte journal/snapshot slots. Reading that directory does not allocate, mount, repair or reserve anything. Native package work could change it between256-byte reads; a directory capture is not automatically an atomic snapshot. Validate generation/CRC/commit/journal state and recheck consistency before interpreting occupancy. No fake bad-sector map or capacity change is proposed.

## Offline checks and exact runners

```sh
python3 runtime/graphics/tests/run_flash_read_tests.py --output analysis/flash-read/NEW-HOST-RUN
python3 -m unittest discover -s scripts -p test_compile_flash_reader.py -v
.tools/rv32-tests-venv/bin/python tests/rv32/flash_read_gate_emulator_test.py \
  --build runtime/build/flash-read-001 --report analysis/flash-read/NEW-GATE-REPORT.json
.tools/rv32-tests-venv/bin/python tests/rv32/flash_read_runtime_emulator_test.py \
  --build runtime/build/flash-read-001 --report analysis/flash-read/NEW-RUNTIME-REPORT.json
```

The two new emulators have isolated exact blob pins and accept a fresh build directory only when its bytes match. They do not change old graphics/scene/input pins.

* Host ASan/UBSan:2400 range/ownership cases plus allocation, native failure, JSON fallback, malformed request and null-event cases. Every allowed page at length1/256, every unaligned displacement, unsupported device selectors, limits and near-UINT32_MAX rejection are covered. Driver mock checks released request and all256 initialized raw bytes. No write/erase/display APIs are provided to the host mock.
* Actual RV32 gates:7955 cases, all256 command bytes with null/non-null request, existing input/display dispatch and callsite continuation. C bodies are deliberately mocked here; preserved register/stack/FPR/fcsr properties remain checked.
* Actual RV32 C/native-wrapper tests:5 groups,95 handler calls; strict native TLV extraction, allowlist edges, malformed/overflow/alignment rejection, exact four native arguments, one-call/no-retry behavior, initialized owned destination, no out-of-bounds access, no use-after-free, response copying, failure suppression, headroom threshold and allocator/JSON failure. Only external firmware APIs are mocked. No flash program/erase address is mapped; an unexpected executable address fails the harness.
* Compiler tests require both prerequisite profiles, reject the synthetic gate profile combination, verify actual RV32/RX load and retained reader symbols, and check old-profile byte identity.

Evidence: [host](../../analysis/flash-read/host-002/report.json), [gate](../../analysis/flash-read/gates-001.json), [runtime](../../analysis/flash-read/runtime-001.json). These are mocked-native tests of actual compiled instructions, not real flash reads, driver busy-loop execution, a bootloader acquisition, or evidence that mutable storage can be reserved safely. Installation and physical reads require separate captured hardware verification.


## Host acquisition and regression

`scripts/memomind_flash_read.py` implements the fixed protocol on an existing
connection. It verifies the complete profile and allowlist before reading,
checks every device/offset/length echo and hex byte count, and stops after any
native, protocol or timeout error. It has no retry or write operation.

`scripts/capture_memomind_flash.py` defaults to query-only. Explicit `--region`
arguments select the named ranges. For regions other than `app-header`, supply
`--expected-app-prefix` containing 32..256 independently known app-header bytes.
The tool first captures and compares the app header, then acquires selected
regions in 256-byte chunks. Output uses a new private directory, exclusive files,
a flushed/fsynced chunk journal and hashes; interrupted captures retain partial
files without a completion manifest. A mismatch stops before unknown regions.
The prefix is the decompressed candidate component's header, not the appended
runtime blob or OTA container header.

The aggregate `tests/run_tests.py` requires flash host, build, gate, runtime and
C/RV32-to-Python contract checks. The client/acquisition tests cover malformed
replies, wrong identities, address limits, interrupted journals and partial files.
All of these checks are offline; native flash callbacks remain mocked.
