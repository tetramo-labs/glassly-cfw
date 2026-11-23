# MemoMind 1.0.3.127 native firmware findings

Static analysis of the captured stock application establishes its OTA resume
calculation, staging CRC validation, reboot metadata commit, and native plugin
capability/validation paths. It does **not** establish that modified whole-firmware
images will pass the bootloader or that a failed flash can be recovered.
No modified firmware or plugin was installed during this analysis.

## Reproducible target and mappings

Input: `analysis/extracted/validated-1.0.3.127/segment-3.body.bin`, 1,773,176 bytes,
SHA-256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
The image header and partition metadata imply load/start address `0x041eb020`.
This address is derived from files, not a live program-counter observation.
Startup establishes `gp = 0x02011688` at `0x041eb03e` / `0x041eb042`.
The startup copy routine at `0x041fb1ec` establishes these additional mappings:

| Source in extracted file | RAM destination | Length |
|---|---|---:|
| `0x64` | `0x02000000` | `0xf8b4` |
| `0x1aefa8` (XIP `0x04399fc8`) | `0x0200f8b8` | `0x1e78` |

BSS `0x02011878..0x0205e128` was modeled as uninitialized memory. These mappings
resolve many calls into copied RAM code without pretending to possess live RAM.
Machine-readable checks: [mapping-validation.json](mapping-validation.json).

Ghidra 12.2 imported the raw file as little-endian RV32 with compressed instructions.
Its generic calling convention uses ilp32d; the official plugin SDK declares
RV32IMAFC / ilp32f. Integer control-flow findings below do not rely on floating-point
ABI inference. All function names are analyst/tool names, not original symbols.
Decompiler prototypes can be wrong: `0434cb38.c` elides the CRC accumulator loop,
while its assembly explicitly retains it. Use paired `.asm` exports for that routine.

The owned project is `analysis/ghidra/projects/memomind-1.0.3.127`; scripts live in
`scripts/ghidra`. REA performs the APK inventory, but its current provider does not
support this raw RISC-V import. These native results are from direct Ghidra, not
misrepresented REA evidence. See `analysis/rea-workflow.md` for installation hashes
and runnable wrappers.

## Initial OTA offset and resume

[Parser 0x0423a90e](integrity/function-0423a90e.c) handles the OTA commands.
For `e2`, the incoming payload length and CRC32 are compared with retained globals
at `gp+0x4c8` and `gp+0x4c4`. A match sets the flag at `gp+0x4dc`. For `e3`,
the cursor at `gp+0x4cc` survives only when that flag is set and the cursor is
strictly between zero and payload length; otherwise it resets to zero.

[Response builder 0x0423a278](integrity/function-0423a278.c) adds 18 to the internal
cursor and encodes that result as the requested big-endian file offset. Its request
length is `min(payload_length - cursor, 4096)`. The captured initial file offset
`0x27bc5` therefore corresponds to payload cursor `0x27bb3` (162,739). This is a
resume position within the file, not a component boundary. The source and lifetime
of the retained cursor in this session remain unknown. See `analysis/protocol.md`.

## Whole-firmware staging and reboot

[Verifier 0x04341c08](checks/function-04341c08.c) has direct-memory and flash-backed
staging paths. It checks magic `0xabcd6543`, counts component bits, verifies the CRC32
of the component table, bounds the sum of packed component lengths, and verifies
CRC32 over the packed payload range. Success returns zero; integrity failures
return `0x10` in the inspected branches. This is executable validation logic,
not a conclusion drawn solely from error strings.

CRC wrapper [0x0434cb6e](integrity/function-0434cb6e.c) initializes to `0xffffffff`,
uses [0x0434cb38](checks/function-0434cb38.asm), then complements the result.
All 256 words in its table at `0x043984a0` match reflected polynomial `0xedb88320`.

[Commit 0x043169ce](commit/function-043169ce.c), called with argument 1 by
[0x04341fdc](checks/function-04341fdc.c), alternates metadata sectors at physical
`0x7fc000` and `0x7fd000`. It changes the header state, copies 20-byte entries,
and writes a CRC32 over header plus entries. The reboot path then calls
[0x0434c42c](commit/function-0434c42c.c) with `(6, 0)` to schedule the reset/event.
No public-key verification call was identified in these particular paths.
That limited observation is not proof that boot ROM, a bootloader, decompression,
component activation, or another verification stage lacks authentication.

## Read-only plugin capability query

Send the normal GM control envelope with **service `0x0f`, command `0x20`, and
zero payload bytes**. It is not an OTA-channel command and requires no TLV field.
The native evidence is:

- [Initializer 0x042e8114](dispatch/function-042e8114.c) installs handler
  `0x042e4680` at callback table offset `0x70`.
- [Dispatcher 0x042e70a4](service/function-042e70a4.c) indexes callbacks at
  `table + 0x34 + service * 4`, establishing service 15.
- [Admission 0x041fa9cc](admission/function-041fa9cc.c) immediately returns 1 for
  command `0x20`, without entering the installer-session state path.
- [Handler 0x042e4680](dispatch/function-042e4680.c) obtains the host display
  callback and formats a JSON response. It does not inspect the request payload
  or enqueue a plugin installation operation for this command.

The host interface at `0x0436609c` has size 112, ABI `0x0100`, and capabilities
`0xff`. Its callback [0x04299704](integrity/function-04299704.c) returns width 600,
height 350, refresh 30 Hz, pixel format 1, and one logical display. The handler
advertises package format 2, `lz4-block`, compression block 65,536 bytes,
maximum package `0x2f0000`, and chunk 8192 bytes, plus cached/resumable installation
and runtime-state flags. The parent investigation independently confirmed these values on installed
firmware 1.0.3.127 with request `fa000009030f200135` and a type-5 JSON response.
Evidence: [native-plugin-caps-live.json](../evidence/native-plugin-caps-live.json),
raw traces `captures/probe/native-caps-01*`, and the after-native-caps HCI capture.
Pixel format 1 is GRAY4 in the SDK. The live query confirms capabilities; it does
not demonstrate successful custom package installation or bootloader acceptance.

## Native plugin package validation

These observations concern the GMP plugin mechanism, not whole-firmware OTA.
The dispatcher sends installation operations to worker `0x042a90ba`; the admission
queue at `0x042a97d4` checks operation lengths and limits data chunks to 8192 bytes.
[Begin 0x042a4598](loader/function-042a4598.c) checks ABI `0x0100` and active state.

[Parser 0x042a2608](checks/function-042a2608.c) checks the 120-byte/version-2 header,
exact total length, name/padding, entry alignment, code/RAM limits, and relocation
and import-table structure. [CRC validator 0x042a2a62](checks/function-042a2a62.c)
uses reflected CRC32 with package bytes `0x30..0x33` zeroed. It canonicalizes binding
instruction pairs in scratch buffers through [0x042a28c6](checks/function-042a28c6.c),
which also validates expected instruction encodings.

[Cache verifier 0x042a4178](integrity/function-042a4178.c) checks metadata identity,
ABI, structural parsing, canonical CRC32, and canonical SHA-256 against the expected
32-byte manifest digest at offset `0x40`. SHA initialization
[0x0433fdf8](checks/function-0433fdf8.c) contains the standard SHA-256 constants.
[Finish 0x042a48d0](loader/function-042a48d0.c) returns a validated cached package
pointer using the `0x05500000` XIP alias. The inspected plugin path supports the
public SDK's CRC/SHA integrity model; it is not evidence of firmware boot policy.

## Remaining blockers to a custom firmware flash

The bootloader/ROM was not acquired, and its signature, anti-rollback, hardware
binding, partition activation, decompression and reset-time verification behavior
remain unproven. Neither alternating metadata sectors nor a successful stock
update proves a recoverable A/B scheme. A recovery interface, known-good full
flash backup, and recovery procedure have not been demonstrated.

A safe future patch decision needs a specified behavior, exact affected component,
boot acceptance evidence, and a validated recovery path. No broad private installer,
modified image, or new live memory-reading payload was implemented in this pass.


## Bounded recovery and boot-authentication follow-up

This pass searched all six validated component bodies (3,747,714 bytes) for
printable ASCII runs of at least five bytes containing boot/recovery/reset and
cryptographic-authentication terms. It followed selected string references and
16 additional functions in the existing application Ghidra project. Exact input
hashes, keyword classes and exported functions are in [recovery/scope.json](recovery/scope.json);
all candidate strings are in [raw-string-search.json](recovery/raw-string-search.json).
Other components received the string scan only, not full code analysis. ROM,
bootloader flash, live RAM and alternate firmware versions were outside this pass.
This is a bounded search, not an exhaustive proof about all reachable code.

### A settings-recovery path exists inside the application

[Application entry 0x0424ba34](recovery/paths/function-0424ba34.c) invokes
[0x041fca6e](recovery/paths/function-041fca6e.c). That function reads a crash count
through [0x041fc12c](recovery/checks/function-041fc12c.c), which accesses key
`0x6002`. A qualifying previous reset increments the count; reaching three calls
the settings-reset routine and then reset `(3, 9)`. A nonqualifying reset clears
the counter. [0x041fc9cc](recovery/checks/function-041fc9cc.c) defines qualifying
reset categories using the boot-reason tuple and crash-record helper.
[Settings reset 0x0422b280](recovery/checks/function-0422b280.c) iterates a table
of setting identifiers through `0x0433f2b8`; it does not install a replacement
firmware image. Application entry separately recognizes the `(4, 3, 9)` boot
reason/source/flag tuple and clears RTC state.

This is concrete automatic settings recovery, but it requires execution of the
application entry path. It does not demonstrate a way to recover an invalid image,
a missing Bluetooth stack, an exception before entry, or a broken bootloader.
No user-invokable bootloader recovery interface was established.

### Metadata redundancy and reset flags are observable

[Metadata reader 0x0431684e](recovery/function-0431684e.c) checks the CRC32 of both
metadata sectors at XIP aliases `0x047fc000` and `0x047fd000`. It chooses the valid
record, or the lower first-word sequence if both are valid; it returns error 5
if neither validates. Together with the decrement-and-alternate writer described
above, this establishes redundant metadata selection. It does not establish dual
application images, automatic firmware rollback, or anti-rollback enforcement.

[Reset routine 0x0434c3e0](recovery/function-0434c3e0.c) calls
[0x0434c44a](recovery/paths/function-0434c44a.c) to store the reason/flag tuple,
[0x0434c486](recovery/paths/function-0434c486.c) to OR in `0x53520000`, then the
lower reset path. [0x043323fa](recovery/checks/function-043323fa.c) updates the low
two bits of MMIO address `0x01a80070`. These are reset control observations;
no branch establishing a download-mode trigger was identified here.

### Additional checks and misleading search hits

The existing [OTA parser 0x0423a90e](integrity/function-0423a90e.c), command `e2`,
compares two incoming 16-bit identifier fields with configuration fields at
`0x0434a94c()` plus offsets `0x4ba`/`0x4be`, bounds the payload size against staging
capacity, and consults update eligibility/state helpers. The inspected helper
[0x0423eb7e](recovery/checks/function-0423eb7e.c) performs threshold comparisons
against 30 or 50, with a state-dependent bypass; it is not a signature verifier.
The exact configuration identifier meanings and remaining eligibility helper
semantics were not assigned in this pass. These checks must not be discarded by
a future custom sender merely because the container CRC is known.

The `unknown boot command` string references resolve to
[0x042e4a5e](recovery/paths/function-042e4a5e.c) and
[0x042e4c26](recovery/paths/function-042e4c26.c). The former handles call status and
call-memory/local-record operations. The latter forwards commands as application
queue events `0x71..0x7b`; those downstream consumers were not fully traced.
Neither string establishes a bootloader transport. Calibration rollback and IMU
recovery strings similarly do not identify firmware rollback or recovery.

No searched ASCII string explicitly named bootloader/boot ROM, DFU, download or
recovery mode, secure boot, signatures, anti-rollback, fuse/OTP, RSA/ECDSA/Ed25519,
or public-key authentication. This absence does **not** prove those mechanisms
are absent: optimized, unnamed, indirect, ROM or separate-stage implementations
would evade this search. No new signature-enforcement or reliable unbrick claim
is justified. The next decisive evidence remains acquisition/analysis of the
actual earlier boot stages and demonstration of a usable recovery route.
