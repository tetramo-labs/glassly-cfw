# Porting g2flash to MemoMind One

Read-only assessment of `~/dev/g2flash` at commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`, 2026-10-30. No G2 code was run
against MemoMind, no firmware was changed, and the G2 checkout was not edited.
The primary investigation reports model H001Y, hardware 2.1.2, firmware
1.0.2.151 (1.3), Android app 1.3.81, and an offered OTA 1.0.3.127 (2.08 MB).
Subsequent capture completed the stock update to 1.0.3.127. The OTA uses RFCOMM
UUID0x7034 and its chunks match the downloaded image exactly. The container is
decoded with verified checksums; application/system code is RV32 with a separate
likely Xtensa/HiFi DSP component. See `protocol.md` and `firmware-format.md`.
Exact chipset and modified-image acceptance remain unresolved. This assessment
identifies reusable G2 abstractions; it does not claim those port tasks are done.

## Conclusion

The reusable part is g2flash's separation of BLE I/O, protocol state, firmware
validation and reproducible patch construction. Its present flasher and patch
set are specific to Even G2. A MemoMind port needs a new protocol/container
implementation and a newly derived firmware ABI profile. Replacing UUIDs or
device names alone would leave incorrect update commands, memory addresses,
checksums, timing and retry behavior.

## Reuse assessment

| Layer | Reusable design/code candidate | MemoMind work required |
|---|---|---|
| BLE adapters | `LocalBleTransport` uses Bleak and a notification queue; `DroidBridgeTransport` exposes the same connect/discover/notify/write interface (`g2flash.py:403`, `:486`). | Replace G2 advertisement matching, lens naming and characteristic assumptions. Confirm bond/auth requirements, actual peripherals and notification source identity. The shared bridge queue assumes one lens at a time. |
| Transfer driver | Explicit discovery/authentication/file-check/data/completion stages; progress and response handling. | Recover real states, allowed transitions, write types, negotiated MTU, payload limits, pacing, watchdog behavior and reboot detection. Do not reuse G2 stage semantics as a dry-run guarantee. |
| Frame codecs | Small pure functions make offline capture replay practical (`frames`, `parse_rx`). | New encoder/decoder derived from MemoMind captures; observed sequence/fragment fields and checksums, with golden packet tests. |
| Retry handling | Distinguishes explicit rejection from ambiguous missing acknowledgment. | Establish MemoMind commit points, duplicate detection, offset queries, restart/resume semantics and disconnect behavior. G2's exact retry policy is not portable. |
| Firmware container | Parser plus checksum validation before any transport writes (`parse_firmware_segments`, `validate_firmware`). | New parser for actual captured format; model/component matching, complete range validation and preservation of all metadata. |
| Build/replay | `gen_patches.py` emits offsets, expected old bytes, replacements and base/output SHA-256; `apply_patches.py` replays without a compiler. | Reuse this representation with a MemoMind-specific manifest and exact stock hash. Supply new modifications and format checksum/signature handling. Never reuse `cfw_patches.json`. |
| ABI audit | `audit_stock.py` verifies exact donor hash, address inventory, expected instruction bytes and disjoint live patch sites. | Derive a MemoMind profile with architecture, load map, functions, globals, structure layouts and byte witnesses. Its G2 address-range filters must change. |
| C code generation | Compiler output is audited and committed as exact patch bytes; reproducibility check is separate from replay. | `build.py` targets Thumb v7E-M, ELF32 LE and selected ARM relocation types. Reuse only if the captured MemoMind target establishes compatible ISA/ABI; otherwise replace the target and relocation handling. |
| Feature logic | RLE, protobuf helpers, memory routines and pure drawing/vector algorithms are candidates for source reuse. | Check their contracts and dependencies individually. Display width/height, pixel packing, allocation, scheduling, transport and hardware access need adapters and tests. |
| Device integration | No directly transferable evidence. | Message dispatch hooks, framebuffer access, heap ownership, tasks, sensors, microphone, input, BLE tuning and wake policy all require new investigation. |

## Concrete G2 assumptions that must not leak into MemoMind

`g2flash.py:19` documents an `aa 21` envelope with 232-byte fragments, CRC-16
CCITT-FALSE, `0xc0` control / `0xc1` data messages, 4096-byte blocks and control
opcodes 0–3. Service/characteristic UUIDs are pinned at lines 53–58. The response
parser expects `aa 12`; authentication uses a G2 settings protobuf request.

The container parser at line 179 reads a component count at byte 8, 16-byte TOC
entries starting at `0x40`, 128-byte component headers and component names at
header bytes 48–127. Validation expects 5–6 components including
`ota/s200_firmware_ota.bin`, component CRC32C with MSB-first processing/init 0/
xorout 0, and a separate main-app preamble CRC32. These details are observed in
G2 source, not observations about MemoMind.

The G2 memory guard uses application load address `0x00438000`, MRAM end
`0x00800000`, OTA flag `0x007fe000`, a 32-byte preamble and a conservative app
ceiling `0x007f0000` (`g2flash.py:71`). None is a MemoMind address. Preserve the
idea of proving destination bounds and excluding persistent data, then derive
the actual limits from MemoMind firmware and its updater.

G2 retry comments and implementation explicitly describe no block index or
deduplication: a missing ACK cannot safely trigger a duplicate block. Explicit
NAKs retry a block; ambiguous timeouts restart the whole component. This is a
valuable failure model to investigate, not a policy to copy without evidence
(`g2flash.py:82`, `:655`, `:718`). Initial G2 `BEGIN` handling even logs an
unexpected response and continues (`:783`); a new MemoMind state machine should
advance only on responses whose meaning has been established.

`patch_compress.py` contains many exact instruction patches and G2 RAM address
assumptions. `message_transport.c:8` calls stock functions through absolute
addresses; `malloc.c` depends on the stock heap coordinator. Pure algorithm
reuse does not make those integration layers portable. `REBASE-2.3.0.24.md`
shows that even G2-to-G2 updates required individual function and RAM-global
re-derivation rather than one offset shift.

## Required MemoMind evidence and deliverables

1. **Acquisition:** original downloaded files and metadata, component/version
   information, file sizes and hashes; complete HCI logs beginning before service
   discovery and ending after reconnection/version verification. Keep both
   directions and all connection handles. Record drop counters/log rotation.
2. **Transport map:** observed GATT services, characteristics, handles, CCCDs,
   writes with/without response, notifications/indications, MTU negotiation,
   connection parameters and peer identities. Establish whether the update uses
   GATT alone, another Bluetooth channel or another transport.
3. **Protocol transcript:** correlate every control/data/ACK exchange with app
   logs and payload byte ranges. Reassemble transfers and compare them with the
   captured file(s). Explain framing, lengths, offsets, counters, checksums,
   component order, authentication and completion/reboot behavior.
4. **Offline codec and replay:** decode the recorded successful session,
   reproduce the official app's bytes, and prove no unexplained payload gaps.
   Tests cover boundaries, truncated frames, corruption, disconnect and delayed
   or duplicated ACKs without sending test traffic to glasses.
5. **Container and boot investigation:** identify full versus delta images,
   compression/encryption, chip/ISA/endianness, image destination maps, integrity
   and authenticity checks in both updater and boot path, rollback constraints,
   and an established recovery route. Root on the phone does not establish that
   the glasses accept custom images.
6. **Firmware ABI and first patch:** exact donor hash, byte witnesses, supported
   version/model, validated free space and RAM ownership, and a minimal opt-in
   behavior change at a proven hook. Generate/replay into a separate output and
   verify its exact diff, checksum rules and bounds before a flashing trial.
7. **Feature port:** move protocol-independent logic first; then add adapters
   for MemoMind display, allocation, scheduling, messaging and peripherals.
   Reuse host tests where their contracts still apply, and add recorded-session
   tests for the new flasher before device validation.

The first useful implementation is an **offline MemoMind OTA decoder and image
inspector**, then a separate MemoMind transport driver. Keeping the existing G2
profile intact prevents a new target from weakening its known validation rules.

Sources read: `g2flash/AGENTS.md`, `g2flash.py`, `build_cfw.sh`, `README.md`,
`patches/apply_patches.py`, `gen_patches.py`, `audit_stock.py`, `build.py`,
`patch_compress.py`, `REBASE-2.3.0.24.md`, and selected transport, memory,
allocation and rendering sources. Findings are static source observations and
proposed work; no cross-device compatibility or live port has been demonstrated.
