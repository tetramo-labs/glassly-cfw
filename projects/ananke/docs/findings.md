# Findings

Updated 2026-11-04. Experimental V0900 GATT firmware flashed and full readback independently verified. Original backups preserved. BLE boot and all 16 button notifications are verified on macOS. Normal HID coexistence, standby/wake and real iPhone background/locked behavior remain untested. The dated entries below retain the investigation history; see README.md for the current workflow.

## Observed connected unit

| Property | Observation |
| --- | --- |
| Requested hardware | IINE Mini Retro Ananke Gen 2 |
| USB VID:PID | `4353:800c` |
| Product / manufacturer / serial text | `Xbox 360 Controller` (generic, not a unique unit ID) |
| bcdDevice / bcdUSB | `0100` / `0200` |
| Physical USB locationID | `0x00100000` on this Mac; recheck after changing ports |
| Interface 0 | Class `ff`, subclass `5d`, protocol `01`, two endpoints |
| Interface 1 | Xbox security interface, class `ff`, subclass `fd`, protocol `13`, no endpoints |
| Interface 2 | HID, class `03`, subclass/protocol `00`, two endpoints |
| Vendor HID usage page | `ff80`, usages 1 and 2 on the same HID path |
| Vendor framing | `B5` requests, `B4` responses |
| Protocol version | `01` from command `01` |
| Model | `ig05` from command `04` and MessagePack `get_info` |
| Firmware version | `0x0601` (1537), confirmed by MessagePack response |
| Bootloader / CPU / flash size | BR23 / UBOOT1.00 confirmed by SCSI; exact silicon and flash size unconfirmed |
| Installed application / partition map | Unknown |

Evidence: [USB registry](evidence/usb-registry.txt), [identity summary](evidence/usb-identity.json), [raw GET exchange](evidence/usb-get-queries.jsonl).

The first sandboxed HID open failed before any command was sent. The same bounded GET-only probe succeeded with sandbox escalation (no sudo). Commands 01, 03, 04, 05 and `cc/get_info/all` each answered. The decoded MessagePack reply is `{"cmd":"ret_info","mode_name":"ig05","version":1537}`. This supports shared vendor protocol ancestry; it does not establish chip, layout or firmware compatibility. Command 05 returned `08 40`; its exact Ananke-specific meaning has not been independently established.

## Product documentation and update entry

The [manufacturer's product page](https://iine.store/products/iine-mini-retro-ananke-gen-2-controller) and [official guide](https://iine.store/pages/mini-ananke-gen-2-controller-guide-manual) identify a larger controller with eight connection profiles. The guide covers L1254, L1255, L1277, L1282 and L1283; the physical SKU of this unit has not been read.

The official guide lists Pairing + Left for wireless XInput, Pairing + Right for HID, Pairing + A for keyboard, Pairing + B for mouse, Pairing + X for touch, and Pairing + Y for multimedia. Its wired PC mode is XInput, consistent with the observed USB identity. It does not document USB firmware-update entry.

Located the L1254/L1255 printed-manual PDF on a public mirror:
- [English/bilingual manual](https://manuals.plus/m/bf4160920fc1158a50d20485eb70a327402e02ca8f169099778bc743f4040987.pdf)
- [Alternate original manual PDF](https://manuals.plus/m/9e4f88394414e601e867fac9f511451132e380d603ee308849f5c6c2fa21e887.pdf)

Search-index text of the manual refers users to IINE Discord for firmware/tools. Direct PDF and preview downloads returned HTTP 403, and web screenshots did not expose viewable image data. The mirror's HTML conversion mixes headings and mode descriptions (e.g. Switch heading with mouse pairing); do not use its reconstructed table as authoritative. The printed manual was subsequently downloaded by the user and fully inspected; see the manual review below. No confirmed Ananke update shortcut was found in the accessible documentation. The Gamebrick's wired Pairing + B shortcut is a possible experiment, not an established Ananke instruction.

The [official Chinese technical-support page](https://www.iine.top/support/technical) links these public dashboards:
- [Firmware files](https://u5tqxzj1yb.jiandaoyun.com/dash/645b138d99c8b800089e8fc5)
- [Electronic manuals](https://u5tqxzj1yb.jiandaoyun.com/dash/6018ef17bbf6c1000833fa98)

The firmware page's HTML was retrieved, but the attempted underlying listing request returned HTTP 401. Browser automation was unavailable under the current tool approval policy. No login restriction was bypassed, and no OEM update was run. The [store Downloads page](https://iine.store/pages/downloads) currently points to IINE apps rather than a model-specific firmware archive.

## Relationship to Gamebrick research

Source checkout: `../glassly-mini-gamepad`, commit `9d51cdf93e5bc4be71bbc7e05fe8984130838033`. Its current findings and plan were read before starting. Both unit1 original dumps were verified against `docs/device-backup.json`, and both copies for each registered Gamebrick unit were verified against that backup's metadata and devices.json. No Gamebrick dump was changed or copied into this repository.

Gamebrick's normal identity is `4353:8009`, model `mt_IINE`, stock firmware `0x0300`; this Ananke is `4353:800c` / `ig05` / `0x0601`. Gamebrick's SCSI BD19 identity and 512 KiB flash size must not be assigned to Ananke without measurement.

## Backup preparation

Prepared an INQUIRY-only identification operation, plus a backup operation that accepts only SCSI `BD19 / UBOOT1.00` before permitting the exact pinned BD19 RAM loader. Unknown identities stop without RAM code. The loader is verified chunk by chunk before execution. Flash identity replies are cross-checked, capacity is derived from JEDEC density, and two full reads must match. Flash/fuse erase and program commands are absent from the allowlist. Dumps are saved read-only and partial captures retained. Physical port selection, per-transfer timeouts, a bounded device wait and a process watchdog are enforced.

The native helper compiled. Eleven offline tests passed with normal Python and with `-O`, covering identity/hash mismatch, early jump, RAM mismatch, flash identity mismatch, prohibited commands, read bounds, short reads and matching/unstable backups. This is offline validation; no bootloader inquiry or firmware read has yet run on Ananke.

## Manual download retry: 2026-11-01

Retried both original PDF URLs with approved network/filesystem escalation. Both again failed with HTTP 403; no PDF was saved. Header inspection of the English URL showed a 302 redirect from the `.pdf` URL to the extensionless document page, followed by Cloudflare HTTP 403 with `cf-mitigated: challenge`. This is a remote browser challenge, not a local sandbox or approval rejection. The user subsequently supplied the browser-downloaded manual; see the review below. Update-mode entry remains unconfirmed.

## Original manual reviewed: 2026-11-01

The user supplied `~/Downloads/iine-plus.pdf`. Preserved an identical copy as ignored `research/manual-l1254-l1255.pdf`; byte count and SHA256 are in [manual evidence](evidence/manual.json). This is one image-only PDF sheet containing all 18 Chinese and 18 English printed panels. Rendered with macOS PDFKit and visually inspected every panel in both languages. The earlier HTML conversion is not reliable for associating headings with button combinations.

The original confirms Pair + B is mouse pairing (panel 11, LEDs 1–3); wired PC operation defaults to XInput (panel 8). It contains no firmware-update, USB bootloader-entry, backup or recovery procedure in either language. English panel 18 directs users to `discord.gg/iine` for firmware files and update tools; Chinese panel 18 points to official support for product upgrades. A distinct wired update behavior for Pair + B remains possible but unverified; the manual does not establish it.

The Pair button is on the bottom edge near the lanyard hole and four LEDs; it is separate from HOME and Turbo. Full mode and control notes are in [manual notes](manual.md). No hardware command or flash write was sent during this review.

## Official updater package and live update entry: 2026-11-01

The user supplied the official updater, a two-page firmware-update manual, and `IG05_V0900.ufw` / `IG05_V0901.ufw`. All four files are preserved under ignored `research/`; hashes and sizes are in [artifact evidence](evidence/oem-artifacts.json). Both manual pages were extracted and visually reviewed.

**Confirmed entry:** power the controller off, hold **Capture + Home** (the two angled front buttons), then plug in USB. The user performed this procedure and the same physical port `0x00100000` changed from `4353:800c` to **`4c4a:2342`, `BR23UBOOT1.00`**. [USB evidence](evidence/usb-update.json). This supersedes the earlier speculative Pair + B experiment. SCSI inquiry is still pending; USB naming alone is not final chip identification. The probe now targets this exact observed VID/PID and port. Backup is temporarily blocked pending BR23 review/inquiry, preserving the identity gates.

The manual assigns V0900 to **L1254/L1255/L1277 (Purple/Gray/Cream Yellow)** and V0901 to **L1282/L1283 (Baby Blue/Mint Chocolate Green)**. The unit's physical SKU/color still needs confirmation before any future image selection. The OEM installation procedure includes whole-flash erasure; that step is inappropriate for the current backup task and was not performed. The updater executable was not run. Its SHA256 is identical to the retained Gamebrick updater executable.

Offline UFW inspection using pinned `jl-misctools` extracted both packages. Both have the package label `AC695X`, firmware VID `ig05`, PID `jm895`, and application entry `0x01e00120`. The packed flash payload is 356,352 bytes; its embedded map places key_mac at `0xff000` with length `0x1000`, suggesting a 1 MiB address space, **not yet a measurement of installed flash capacity**. The packaged app header is at `0x3020`, unlike the retained Gamebrick layout. V0900 and V0901 applications are 338,712 and 342,552 bytes and have distinct hashes. Their extracted bootloader and configuration-tool resource match. See [inspection evidence](evidence/oem-inspection.json). Some auxiliary UFW metadata encoding remains unvalidated; no package is approved as a restore image.

Pinned `jl-uboot-tool` maps BR23 to the AC635N/AC695N family and a distinct 11,264-byte loader at RAM `0x12000`, not the BD19 loader at `0x2000`. The loader is stored in MengLi form; the matching ROM protocol encrypts/decrypts memory transfers, so block readback should match the stored blob. The proposed sequence follows the pinned tool's 512-byte ROM upload and argument 1 (SPI NOR), adds exact RAM readback before jumping, and limits subsequent flash reads to 256 bytes. Twelve offline tests passed, including rejection of BD19 identity. Live SCSI identity is required before activation.

## BR23 identification verified; backup enabled

The user ran the interactive probe successfully. `research/probe-20261101-151534/inquiry.bin` matches the metadata byte-for-byte and identifies **BR23 / UBOOT1.00**. See [saved inquiry](evidence/bootloader-inquiry.json). This supersedes the pending-inquiry/disabled-backup statuses above. The backup tool now uses only the pinned BR23 loader (SHA256 `7384429e33ee1f340fbffe46aa928a0099c163e1374a40f6f9f27468a6f16ddf`) with the reviewed 22 × 512-byte RAM upload/readback at `0x12000..0x14bff` and SPI NOR argument 1. The old Gamebrick/BD19 identity is explicitly rejected. The 12 offline tests pass in normal and optimized Python, the CRC agrees with the pinned upstream implementation on every loader block, and the native helper compiles. Hardware RAM upload/readback and full flash reads remain pending.

The user confirmed the **Purple/Gray/Cream Yellow** group and requested the latest official firmware as CFW base. The supplied matching release is **IG05_V0900.ufw**, not V0901 (which targets other color/SKU variants). The plan is to preserve the installed `0x0601` image first, derive the actual device layout, and use the matching official application as the CFW base. No stock or custom firmware has been installed on this controller in this session. The supplied package's status as the latest release has not been independently checked against a live release catalog.

## Stock firmware and Glassly integration priority

The user proposed using stock Switch-mode button reports and adding an Ananke controller in `../glassly`, potentially avoiding CFW. This is now the first integration path to investigate after preserving the original flash. No Ananke BLE service discovery, button capture or iOS background test has yet been completed.

Read-only inspection of Glassly found:

- `mobile/modules/bluetooth-sdk/ios/Source/controllers/Controller.swift`: native controller interface.
- `mobile/modules/bluetooth-sdk/ios/Source/DeviceManager.swift`: controller construction/type registry, including Gamebrick.
- `mobile/modules/bluetooth-sdk/ios/Source/controllers/Gamebrick.swift`: CoreBluetooth discovery/subscription, input translation, reconnect and state-restoration handling. Its custom AE42 four-byte packet is Gamebrick-specific and cannot be assigned to Ananke without evidence.
- `mobile/app.config.ts`: `UIBackgroundModes` includes `bluetooth-central`.

These provide integration points, not proof of Ananke compatibility. No Glassly code was changed. Apple's [Core Bluetooth background guide](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html) documents waking a suspended central-mode app for characteristic updates and opt-in state preservation/restoration. This applies only if the device provides a usable app-accessible stream; system HID/GameController recognition alone does not demonstrate that path.

Next: preserve two matching flash reads, then inspect stock Switch pairing (Pair + Up), discover GATT and capture button press/release notifications. Do not infer Bluetooth transport from the mode name. A discovered stream needs a separate Ananke driver and physical iPhone foreground/background/locked, standby and reconnect tests. If stock is insufficient, retain V0900 as the supplied matching official firmware candidate for further analysis and conditional CFW work.

## First hardware backup attempt stopped during RAM upload

`research/device-backup-20261101-153148/metadata.json` records an incomplete backup with BR23 / UBOOT1.00 identity and `Failed USB command status`. The traceback stopped in the FB06 RAM-write command before the upload loop completed. No loader jump or flash read was reached; the backup transport contains no flash-program commands. The original diagnostic did not retain the failing address or raw CSW, so neither the block index nor the failing status field is established.

Compared FB06 address/length, CRC16, padding, loader hash and stored encryption handling with the pinned upstream source; no framing discrepancy was found. This does not establish that the controller accepted it. Added strict BOT status diagnostics (CDB, CBW, raw CSW, signature, returned/expected tag, residue, status and transfer phase), retained in failure metadata. Signature, tag, residue and status gates are unchanged. Retry only after a fresh Capture + Home update-mode entry; preserve the original failed attempt. Root cause and full backup remain pending.

## Stock system-gamepad integration implemented: 2026-11-01

The user redirected work from the failed backup to implementing Ananke Joy-Con/Switch-mode support in Glassly. The full iOS GameController and Android InputDevice implementation was committed and pushed to `tetramo-labs/glassly` dev at `09063a406fbf950b99db19cc3be3e56f0a8bc6ed`. It uses existing touch_event APIs with source 6, per-button indices, and D-pad swipes plus press/hold/release phases. Pairing instructions use the reviewed Ananke-specific shortcuts. See Glassly docs/adr/0017-ananke-uses-system-gamepad-input.md for index mapping, lifecycle, identity and validation details.

The implementation is foreground-only, not a GATT/background workaround. Native synthetic tests and builds passed; physical Ananke mapping/compatibility and end-to-end phone testing remain pending. The wider iOS registry suite encountered an R1 CoreBluetooth test-runner background-mode exception. The site and current pitch were updated with preview support and the supplied purple product image, pushed to `tetramo-labs/glassly-site` main at `aad84b25bc487c194a3d4f9945c96c12c5c27aa3`.

The firmware backup remains incomplete at the first RAM-upload failure. No additional USB operation or flash write was performed while implementing app support. The original installed firmware remains the target for a future backup; V0900 stays the supplied matching official package if firmware work resumes.

## CFW research resumed: 2026-11-03

The user requested GATT button events for iOS background operation, analogous to the Gamebrick work. The foreground system-gamepad driver does not satisfy that requirement. Stock app-accessible GATT delivery remains untested; the request resumes offline CFW research while preserving the backup and recovery prerequisites.

`research/inspect_ananke.py` verifies the selected V0900 package and extracted application's pinned hashes, then locates and validates the OEM GATT table without using Gamebrick offsets. [Reproducible evidence](evidence/v0900-gatt.json) includes all 91 attributes, declaration/value/CCC relationships and button/lifecycle string anchors. The table starts at **file offset `0x4a69f`** and ends at `0x4aa50` (exclusive, including its terminator). It is byte-aligned; assuming 16-bit alignment misses it. A separate one-record GAP fragment at `0x4324c` is not the complete profile.

| Service | Characteristic | Declared property | Value handle | CCC handle |
| --- | --- | --- | --- | --- |
| AE40 | AE41 | Write without response | `0x52` | none |
| AE40 | AE42 | Notify | `0x54` | `0x55` |
| AE00 | AE01 | Write without response | `0x82` | none |
| AE00 | AE02 | Notify | `0x84` | `0x85` |

These are independently observed **V0900 package** attributes, not a live capture of installed `0x0601`. They establish a candidate vendor channel, not a stock button packet format, runtime profile selection, notification delivery or Gamebrick payload compatibility. File offsets have not been promoted to runtime addresses or patch locations. The remaining code work is to trace profile installation, AE42 CCC handling and ATT sender ownership/copy semantics, then the debounced input path and a task independent of HID readiness. All physical buttons require mapping; the six-button Gamebrick packet is insufficient by assumption.

Reviewed local Jieli SDK revision `fdc018de81629e21e594d677cf05f87d288be0f0`: `apps/hid/modules/bt/ble_hogp_profile.h` documents this record format; `ble_hogp.c` has an AE42 transfer-channel sender and CCC path, useful as analysis leads only. `apps/hid/board/br23/AC635N_hid.cbp` selects **pi32v2_r3**, unlike the Gamebrick's Q32S payload target. Source hashes are pinned in `sources.lock.json`. The existing local pi32v2 SLEIGH/pypcode decoding attempt exited with signal 11 before producing instructions; no instruction addresses or hooks were accepted from that attempt.

## First-block residue isolated: 2026-11-03

The user's retry, `research/device-backup-20261103-000327`, reconfirmed BR23 / UBOOT1.00 and stopped on its **first** FB06 upload at `0x12000`, length 512. Saved CBW/CDB/CSW establish matching signature/tag and status zero, but residue **512**, meaning the status reports the entire transfer as unconsumed:

- CDB: `fb0600012000020000f4d3ffffffffff`
- CSW: `55534253020000000002000000`
- Metadata SHA256: `4324775e439f7f6ba1b699ca33f9e356f73ee85b458756623529282de395fb71`

This is a contradictory completion report, not an established CRC failure. The `--wait 3` setting was sufficient to find the device and is unrelated to this result. No RAM readback, loader jump or flash read occurred. The incomplete original remains untouched and ignored.

Pinned `jl-uboot-tool` builds the same FB06 request. Its SCSI backends return a residual count, but `JL_MSCProtocolBase.cmd_exec_dataout` discards that return value. That explains why upstream success alone would not resolve our stricter check; it is not evidence that this unit's write succeeded. The backup transport still rejects every nonzero residue.

Added `research/diagnose_upload.py` for a **separate read-only diagnostic session** after this exact recorded failure. It validates the failed metadata, saved inquiry, physical port and loader hash, then permits only INQUIRY followed by one FD07 read of `0x12000..0x121ff`, with unchanged USB status checks and bounded timeouts. It saves the raw block read-only, compares against the pinned loader's first block, and stops. No upload, jump, flash command or retry exists. Matching RAM would support an upload-residue reporting quirk, but does not clear the original mismatch or authorize continuing backup. Power cycling or reconfiguration may affect RAM, so a mismatch alone does not establish that the original upload failed. Hardware diagnostic result pending.

The user ran that diagnostic as `research/ram-probe-20261103-000612`. INQUIRY succeeded; FD07 received 512 data bytes followed by the same status-0/residue-512 CSW. It stopped before accepting the read. The initial error path discarded the data before recording it, so no byte comparison can be made from that run. Fixed the transport to retain rejected data separately, and the diagnostic to save it as `ram-12000-incomplete.bin` with hash, comparison result and `usb_status_valid: false`; metadata remains incomplete and the original exception is still raised. Requested a repeat read-only diagnostic; no backup retry or status exception is enabled.

After explicitly authorizing the agent to run that diagnostic and supplying interactive authentication, the user permitted the repeat captured in `research/ram-probe-20261103-001159`. No credential was written to repository files or scripts. The repeat again stopped on status-0/residue-512, but this time preserved **512 bytes exactly matching the pinned loader's first block**. Independently verified the saved bytes against metadata, the loader, and read-only file permissions. Block SHA256: `dc02a47bf9202a8d4fbad161971be8cd046e1809413d1e8c63c77b95e89ec87f`; metadata SHA256: `929121190a07041a43d1a7cee44a49c2d6223f5c16b160232f0fae1b0752bdfa`. [Evidence summary](evidence/br23-residue.json).

This establishes that the first loader block reached RAM and was returned exactly despite the contradictory residual count. It supports a BR23 ROM residue-reporting quirk for these specific FB06/FD07 exchanges. It does not validate the remaining loader blocks, FB08 execution or flash-command status semantics. The diagnostic and backup remain incomplete; no status exception has been enabled, no loader jump was sent and no flash read/write occurred. Next transport work must review a narrowly scoped ROM compatibility policy with mandatory byte-for-byte RAM verification, without extending it to identity errors, status failures, arbitrary residues or post-loader flash commands.

## Build/install request and ROM transport policy

The user explicitly requested making and flashing the custom firmware, and previously authorized the agent to run privileged USB operations. Installation remains contingent on preserving the original, deriving the actual layout and proving recovery. No new flash writer has been added.

Implemented `br23-uboot100-pinned-ram-full-residue-v1` in `research/usb_transport.py`. It activates only for the exact captured 36-byte BR23 inquiry and exact pinned 11,264-byte loader. It requires residue **exactly 512** for the bounded 512-byte FB06/FD07 path, with exact loader bytes/CRC/padding for uploads. Signature, tag, status-zero, byte count and byte-for-byte RAM readback remain required. An arbitrary residue (including a changed reporting convention) still stops. The exception is removed before FB08 and never applies to loader execution or flash commands. This extends the observed first-block protocol behavior to the remaining pinned RAM blocks, each of which still requires independent readback; that extension is not yet hardware-validated.

The backup now records all 44 RAM command/status records after successful verification, before executing anything, and retains rejected data as incomplete evidence on failure. Thirty-two offline Python tests pass in normal and optimized modes, including altered residues/status/tag/signature, wrong identity/blob, out-of-bounds or unpinned writes, RAM mismatch, no jump on failure and strict post-loader behavior.

The bounded retry `research/device-backup-20261103-090759` found no device at the old `0x00100000` port and sent no SCSI commands. Read-only registry inspection found one normal-mode `4353:800c` controller at **`0x02100000`**. [Port evidence](evidence/usb-location-20261103.json). Requested power-off + Capture/Home USB entry on that port; awaiting hardware readiness. No loader was executed or flash accessed during this retry.

## Official pi32v2 disassembly and stream component

Started the local Docker runtime and used the retained official Jieli Linux toolchain with networking disabled and source/toolchain mounts read-only. Archive, clang and objdump hashes were verified and pinned in `sources.lock.json`. `scripts/pi32v2-tool.sh` checks both executable hashes on each run. A small pi32v2/r3 compiler probe establishes ELF machine 241. This resolves the earlier SLEIGH blocker for assembly inspection; it does not supply a complete emulator or decompiler.

`research/prepare_ananke_analysis.py` makes an analysis-only ELF from the exact V0900 application, with no program headers. Startup independently shows a copy from file offset `0x4c42c` (flash address `0x01e4c54c`) to RAM `0`, length `0x66c4`; BSS clearing covers `0x6f40..0xbfc7`. Both the storage and relocated RAM views are included. Generated ELF/listing/object files remain ignored. [Code evidence](evidence/v0900-code.json) records hashes, ranges, GPIO tests and candidate state fields.

| V0900 location | Static interpretation |
| --- | --- |
| RAM `0x14ba..0x15c7` | Active-low GPIO scanner: 19 tests over 18 distinct GPIOs; GPIO 17 contributes two logical bits |
| RAM `0x18c6` | Scan-task candidate; checks a 100-tick interval, calls scanner, updates key state |
| RAM `0x79e4` | Candidate raw 32-bit key state (`0x78e0 + 260`) |
| RAM `0x7920` | 16-bit connection handle used by AE42 sender |
| Flash `0x01e332a0` | AE42 sender with handle `0x54`; calls ATT wrapper `0x01e3181c` |
| Flash `0x01e331fc` | HID/vendor readiness helper; vendor branch checks CCC `0x55` |
| Flash `0x01e3b5b6` | Calls scan-task candidate at RAM `0x18c6` |
| Flash `0x01e3b7f6` | Calls key-decode candidate at RAM `0x192a` |

These addresses belong only to the supplied V0900 app and are not approved patch sites. Physical labels, contact debounce, all task-entry gates, ATT buffer lifetime, execution limits and state allocation still need review. The scanner's 32-bit mask includes more buttons and aliases than Gamebrick's six-bit packet can represent.

Added `firmware/button_stream.c` / `.h`: an unbound single-owner event queue with proposed **custom** eight-byte protocol `47 02 sequence flags keys32-le`. It preserves full key masks, initial/reconnection snapshots, press/release transitions during backpressure, explicit overflow indication and sequence wrap. It has no fixed firmware addresses and is not a stock-packet decoder. The caller must provide a coherent subscription/connection/epoch snapshot and a sender that copies before returning.

`sh scripts/check-firmware-component.sh` passes sanitized host tests for all 32 individual bits, combined masks, queued press/release, overflow retaining final release, CCC resets, epoch/connection changes and sequence wrap. The pinned pi32v2/r3 compile emits **256 bytes of text** with no relocation entries or allocated global data; state size is **80 bytes**, not yet reserved in firmware. [Component evidence](evidence/button-stream-component.json). This is a tested standalone component, **not an installable firmware image**. No flashing, HID/GATT live check or iPhone validation has occurred.

## Complete RAM verification and jump residue: 2026-11-03

After the user entered update mode on `0x02100000`, `device-backup-20261103-093602` reconfirmed the exact BR23 identity, uploaded all 22 pinned blocks and verified every byte. All 44 RAM command/status records match the reviewed full-residue policy. The following FB08 request (`fb08000120000001ffffffffffffffff`, tag 46) returned a 16-byte reply beginning `fb08`, with matching signature/tag and status zero, but residue **16**. The unchanged zero-residue jump check stopped the operation before any flash identity/read command. The rejected acknowledgement and full RAM transcript were preserved and independently verified. [Jump evidence](evidence/br23-loader-jump.json).

Added a separate `read-loaded --prepared-backup ...` operation. It verifies every prior RAM CDB, CBW, CSW and block hash, the rejected jump acknowledgement and physical location before enabling only INQUIRY, three loader identity queries and capacity-bounded flash reads. RAM upload/jump and all flash mutations are forbidden. The attempted continuation (`device-backup-20261103-093841`) found no bootloader and sent no SCSI commands: registry inspection showed normal `4353:800c` at the same port. It is not established whether the loader reset, timed out, or was affected by closing USB capture after the failed status check. No flash access or modification occurred.

Prepared `br23-uboot100-verified-jump-full-residue-v1`: FB08 requires the exact address/argument, all 22 byte-verified blocks at both transport layers, signature/tag/status-zero, residue exactly 16 and an `fb08` reply prefix. The ROM policy is retired before subsequent loader commands; **FC0A/FC0B/FC14/FD05 still require zero residue**. A successful jump acknowledgement is recorded before flash queries. The next retry will query flash identity immediately in the same captured USB session, avoiding the earlier close/reopen interval. Thirty-six offline tests pass (normal and optimized Python), including premature/wrong jumps and malformed acknowledgements. Requested fresh Capture + Home entry; this updated jump path has not yet run on hardware.

## ATT payload lifetime trace: 2026-11-03

Extended the independently derived V0900 code index through command dispatch and the send queue. The AE42 wrapper dispatches command 26 at `0x1e16cfe`; its halfword jump-table entry 23 is `0x82`, leading to `0x1e16e86`. The shared case calls `0x1e16af4`, which checks the current connection/CCC and queues a six-byte header plus payload through `0x1e16ab0`. Operation type zero looks up the value handle plus one, consistent with AE42 CCC `0x55`.

The queue helper calls `0x1e00ac2` for both header and payload. That routine checks free capacity, handles wraparound with one or two calls to external ROM `0x1127a8`, advances write counters, and returns the byte count. This supports synchronous copying into a circular buffer, but the ROM routine's symbol/implementation and actual hardware behavior remain unconfirmed. The custom component's copy-before-return contract is therefore still a binding prerequisite. Updated [code evidence](evidence/v0900-code.json) pins all reviewed ranges and the dispatch-table check. No firmware binding or flash image was produced.

The latest readiness check found normal USB `4353:800c` at `0x02100000`, not update mode. No privileged USB command was sent during this check; a fresh physical Capture + Home entry is pending. The 36 offline Python tests pass.

## Immediate loader flash query captured: 2026-11-03

The fresh update-mode attempt at `0x02100000`, `research/device-backup-20261103-174411`, verified all 22 RAM blocks again and accepted the exact FB08 acknowledgement. The immediately following FC0A query returned `fc0a03e9146085004a942850a0f7ee6b`, matching signature/tag/status zero but full CSW residue 16. The strict zero-residue query check stopped the session; no flash data read or write occurred. The preserved failed capture and hashes are recorded in [query evidence](evidence/br23-loader-query.json). The payload suggests SPI NOR JEDEC `856014` (density exponent 20), but capacity remains unconfirmed until the independent ID query agrees.

The pinned upstream protocol documentation explains that the loader installs a command hook while using ROM transfer callbacks. FC0A, FC0B and FC14 share fixed 16-byte response framing. Added a narrowly scoped full-residue-16 policy for these three identity queries, enabled only after exact BR23 identity, full pinned RAM verification, and a successful FB08 acknowledgement in the same session. FC0B/FC14 residue behavior is an explicit inference awaiting live validation, not a claimed observation. All response opcode, signature, tag, status, transfer length and cross-ID checks remain mandatory. Flash reads still require zero residue. Each completed query is now recorded immediately so later failures retain earlier replies. All 38 offline tests pass.

The controller re-enumerated in normal USB mode after the session closed. A new Capture + Home entry is required; no automatic mode switch was sent.

## Flash identity confirmed; first flash block retained: 2026-11-03

`research/device-backup-20261103-174624` verified the pinned loader and all three flash identity queries. FC0A and FC0B agree on JEDEC `856014`, establishing a 1 MiB capacity; FC14 reports a `0x8000`-byte buffer. All three queries returned full residue 16 with valid opcode/signature/tag/status. [Identity evidence](evidence/br23-flash-identity.json) pins the raw replies and source capture metadata.

The first FD05 read at address zero returned 256 bytes, then the zero-residue check rejected its full CSW residue 256. The payload is saved read-only as `rejected-data-incomplete.bin` (SHA256 `fa2dcde20ec37f39c39362100641b438335bb2dacd18a2995f4b392483f4437f`), and the zero-byte `flash-pass1.bin` remains incomplete. No flash write or erase was sent.

Prepared a dedicated full-residue-256 policy for exactly aligned 256-byte FD05 reads within this measured 1 MiB device. It requires the exact BR23 identity, pinned RAM upload/readback/jump, and validated live replies for JEDEC `856014` and buffer `0x8000`. Arbitrary residues, wrong status/tag/signature, malformed requests, other flash identities and out-of-bounds reads remain rejected. Two complete matching reads are still required; no partial capture is promoted to a backup. All 40 tests pass in normal and optimized Python. A fresh physical update-mode entry is pending.

## Full installed backup verified: 2026-11-03

`research/device-backup-20261103-174931` completed two full 1,048,576-byte reads. Both have SHA256 `da281f118ea0e3dc412b2298ce27c1b73a9cf6bca795814708e900a20a9538bc`, match byte-for-byte, and pass `scripts/verify_backup.py`. The dumps, inquiry and metadata are read-only; the entire capture is Git ignored. [Backup evidence](evidence/device-backup.json) records the metadata hash and transport source hashes. The earlier rejected first flash block also matches the first 256 bytes of both complete reads. No erase/program/fuse command was sent.

Unpacked a separate analysis copy using pinned `jl-misctools` revision `0a5b12db0ef38f3042acffbe2452730a37fd2405`. The original backup was not changed. `research/inspect_installed.py` rechecks both originals, extraction size/checksums and application hash. Its [installed evidence](evidence/installed-0601.json) establishes an application-area header at flash `0x3020`, executable data at `0x3140`, and runtime entry `0x01e00120`. The installed app is 343,208 bytes, SHA256 `3c52fc8cef33ee1d0d402f68dc9a92ed819d406b5e99a9033f8304de69cfdc6f`, distinct from V0900. The extracted bootloader and cfg_tool resource match V0900 exactly.

The top table includes app_dir_head2 and key_mac; the application table includes VM, PRCT, BTIF and USERIF. These are recorded as raw encoded offset/size fields. The upstream unpacker explicitly does not implement reserved-area semantics, so its automatically added application-base offsets must not be treated as approved flash addresses for these regions. Protection boundaries, execution limits and recovery still require review.

The installed app contains the same 91-attribute GATT table bytes as V0900, at file offset `0x4bbad`, including AE42 value/CCC handles `0x54/0x55`. This is static evidence, not a live button stream. Stock Switch-mode pairing and app-accessible notification capture are next; the user has been asked to unplug USB and enter Pair + Up. An advertisement-only 40-second scanner is prepared and does not connect or send GATT commands.

## Stock Switch discovery attempt: 2026-11-03

The user entered the requested Pair + Up mode. The sandboxed BLE scan reported unavailable access; the host-authorized scan showed Bluetooth was powered off. Bluetooth was enabled, then a fresh 40-second powered-on CoreBluetooth scan completed with no matching controller advertisement. A 12-second Bluetooth Classic inquiry found one unrelated device and no controller candidate. No peripheral connection or GATT operation occurred. [Discovery evidence](evidence/stock-switch-discovery.json) pins the local logs without publishing nearby device identities.

This attempt is inconclusive: absence during discovery does not prove Switch mode lacks BLE or a vendor GATT channel, and the controller's active pairing state/name was not independently verified. The next requested physical step is Pair + Right, with LEDs 2–3 flashing quickly, to inspect the documented HID profile. The scanner now also accepts generic controller names and reports total advertisers seen; names remain candidates only and never trigger automatic connections.

## Update-mode exit reproduced: 2026-11-03

At the user's explicit request, ran an INQUIRY-only capture/close (`probe-20261103-181219`), which did not immediately exit BR23 update mode. Repeated the existing pinned RAM-loader backup sequence (`device-backup-20261103-181244`). Both full reads passed metadata verification and exactly match the preserved original SHA256 `da281f118ea0e3dc412b2298ce27c1b73a9cf6bca795814708e900a20a9538bc`. After cleanup, USB initially still showed BR23, then re-enumerated as normal `4353:800c` Xbox 360 Controller at the same location. No flash change or vendor run-app/reset command occurred. The delayed exit was reproduced, but its internal trigger is not established. [Evidence](evidence/exit-update-20261103.json).

## Switch discovery after confirmed update-mode exit

After normal USB mode returned and the user pressed Pair + Up, no controller was present in the USB registry. A powered-on 40-second BLE scan observed 108 advertisers but no matching controller candidate; Bluetooth Classic inquiry returned four unrelated devices. No connections or GATT operations were performed. This confirms the Mac scanner is receiving advertisements, but the controller's pairing LED state/name remains unverified. [Retry evidence](evidence/stock-switch-discovery-retry.json).

## Stock Switch controller discovered

During the user's next active pairing attempt, Bluetooth Classic inquiry found an unpaired, disconnected `Pro Controller`. The simultaneous powered-on 40-second CoreBluetooth scan observed 122 advertisers and no matching controller BLE advertisement. No connection or GATT operation occurred. This is positive Classic-discovery evidence in the requested Switch mode; it does not prove absence of BLE in all controller modes. The next step is documented HID mode (Pair + Right, LEDs 2–3) to look for the vendor GATT service. [Evidence](evidence/stock-switch-discovered.json); the physical address remains only in ignored local capture logs.

## Stock HID-mode GATT connected and subscribed

Following the requested Pair + Right mode change, BLE discovery found `IG05 Gamepad(BLE)`, advertising HID service 1812. A separately bounded probe connected only to that observed peripheral UUID, required the matching name, and discovered services 180A, 180F, AE40 and AE00 through CoreBluetooth. AE41 and AE01 expose write-without-response; AE42 and AE02 expose notify. Both vendor notification subscriptions succeeded. AE02 sent one initial byte `ff`; no other messages arrived during the 90-second session. No characteristic command or firmware write was sent (only notification subscriptions).

The user was asked to press/release A, B, X, Y, Up and Down after subscription, but has not yet confirmed performing that sequence during the capture. Therefore the absence of further messages is not established evidence that stock buttons cannot be delivered. Initial `ff` semantics, button mapping and real iPhone background/locked behavior remain unknown. [GATT evidence](evidence/stock-hid-gatt.json).

## Experimental custom image built: 2026-11-03

At the user's explicit request to make CFW and target HID mode, added the V0900 binding, linker map and per-unit image builder. The 472-byte compiled patch wraps the existing scanner, vendor CCC setter and disconnect CCC clear. It sends the custom eight-byte `47 02 sequence flags keys32LE` protocol on subscribed AE42, with queued transitions and fresh session snapshots. It retains the existing HID code paths; no hardware coexistence result is claimed.

Independently traced the flash execution-range setter at `0x01e2e39c` to MMIO `0x101070`/`0x101074`, and extended its upper bound at `0x01e23944` to payload end `0x01e52e10`. Startup RAM-copy source and all initialized RAM bytes stay unchanged. A 128-byte page at `0xc280` is excluded from the heap by changing its start input from `0xc270` to `0xc300`, accounting for the allocator's 128-byte rounding. The previously empty secondary BSS loop clears exactly this page. The binding occupies 96 bytes.

The candidate preserves all installed partition offsets and sizes. V0900 plus payload fits within the installed 343,208-byte app allocation, so cfg_tool need not move. Original-image packaging roundtrip is byte-identical. Independent unpacking reproduces the patched app and verifies unchanged cfg_tool, bootloader and installed isd_config.ini. All bytes outside the original used active application area remain exact. Candidate SHA256: `ccf72e6fa222bc2b486475dea623c5e70ce975862abb6dddf919b53d73cea5b3`; the image and unpacked data remain ignored and local.

Official disassembly covers every byte of all 172 payload instructions, with no unknown instructions and all direct branches reaching instruction boundaries or explicitly bound OEM functions. It also confirms the RAM scan call's 25-bit PC wrap. Jieli's [BR23 ROM symbol table](https://raw.githubusercontent.com/Jieli-Tech/fw-AC63_BT_SDK/master/cpu/br23/maskrom_stubs.ld) identifies `0x1127a8` as memcpy, supporting the ATT ring-copy interpretation. Sanitized stream and binding tests pass, including same-handle reconnect and epoch changes during lookup. All 49 Python tests pass. A complete rebuild reproduces the same image hash. The linker executable is now pinned alongside clang and objdump.

**Installation remains blocked**, not merely awaiting permission. Recovery entry independent of the application, bounded sector restore, BR23 erase/protection behavior, complete stack headroom and callback serialization remain unvalidated. A narrow CCC/disconnect race persists between readiness check and OEM send; the nested interrupt-mask routines at RAM `0x351c`/`0x3538` are identified but their scheduling contract has not been established. The input-task creation has a stack argument of 1024, whose unit and full worst-case call chain still need review. No flash command or live CFW test occurred in this build. See [candidate documentation](custom-firmware.md) and [build evidence](evidence/cfw-candidate.json).

## Flash preparation and runtime corrections: 2026-11-04

The user explicitly requested flashing. USB registry inspection finds normal `4353:800c` at `0x02100000`; update-mode entry was requested. No flash or privileged USB operation has been sent during this turn.

Review found that the original candidate's void disconnect hook clobbered r0 even though the OEM caller at `0x01e3261c` reuses the stock CCC-clear return value. The corrected hook preserves it. The prior candidate `ccf72e6f…` is superseded and must not be installed.

Added the independently traced nested critical-section functions at RAM `0x351c`/`0x3538` around CCC mutations, snapshot reads and the final readiness check through queue insertion. The BR23 CPU header documents a single core and priority-mask level 6, matching these routines. The sender now uses the same underlying copying ATT queue at `0x01e16af4` directly, with value handle `0x54`, operation 0 and buffer 0, avoiding the outer AE42 wrapper's error logger while locked. Sanitized tests verify lock balancing, preserved return values and deferred disconnect/renewed snapshots. Hardware latency and highest-priority interrupt interactions remain untested.

Traced the input-task stack argument from flash `0x01e37a5c` through RAM `0x4daa` to `0x4be8`, where it is multiplied by four before allocation. The image now requests 1152 words (4608 bytes) instead of 1024 (4096 bytes), adding 512 bytes of headroom. The custom scan/stream/send frames total 100 bytes before OEM queue callees; this is not a complete worst-case stack proof.

The revised payload is 552 bytes, ends at `0x01e52e60`, and contains 201 fully checked instructions. Eight pinned image edits preserve RAM relocation, partitions and resource contents. A full rebuild and independent unpack pass, with candidate SHA256 `a93b93a788452026e2b155a8797805ef7d1d55be0af1e2eb7fcdd9fda49388d3`. All 49 Python tests and both sanitized C test suites pass. [Runtime byte-range evidence](evidence/runtime-review-20261104.json).

Recovery remains a concrete blocker: V0900 contains an application-level function at RAM `0xd5e` that calls ROM `0x1127f0` with boot-state argument 2 and resets. This shows why UBOOT1.00 observations alone do not prove an independent entry route. The pinned upstream `how-to-enter-uboot.md` describes a hardware USB-key updater dongle for ROM entry, but that route has not been demonstrated on this unit. Asked whether the user has such a dongle or another tested independent recovery method. Sector restore and BR23 protection/write behavior also remain unvalidated; the manifest still forbids installation.

## Experimental installation authorized: 2026-11-04

The user explicitly waived independent recovery and accepted possible controller loss. This supersedes that installation prerequisite for this one experimental attempt; it does not establish recovery or runtime correctness. The pinned candidate remains `a93b93a788452026e2b155a8797805ef7d1d55be0af1e2eb7fcdd9fda49388d3`. The offline manifest records the earlier conservative build status; the separate authorization evidence records the exception.

Added a separate `research/flash_controller.py` installer. The backup command allowlist remains unchanged. The installer verifies both original backups against pinned metadata, the exact candidate, exact live identity and loader, then takes two fresh matching full reads. It requires unchanged boot/application bytes and preserves current mutable data from those fresh reads. Only the 84 changed 4 KiB application sectors may be erased, with 256-byte programming and immediate page/sector verification; the header sector is last. A final full read must match the desired image. No whole-chip erase, fuse, protection-register, retry or reset command is allowed.

Decoded the pinned BR23 loader using the ROM's per-512-byte MengLi stream and disassembled with the pinned toolchain. FB01 reaches SPI sector erase opcode 0x20; FB04 uses the page-splitting program routine, and reads wait for the busy flag. No host protection-unlock operation is provided. New command residue handling is narrowly framed and remains subject to live verification. See `docs/evidence/experimental-install-authorization.json`. All 57 Python tests pass, including installer failure cases.

USB registry still showed BR23UBOOT1.00 at `0x02100000`. The authorized attempt to start the installer stopped at `sudo: a password is required`, before Python ran. No flash erase/program command has been sent. Per the repository credential instructions, the user must run the prepared command in their interactive terminal.

## First custom installation verified: 2026-11-04

The user ran the prepared installer in their terminal. Attempt `flash-attempt-20261104-100838` verified exact BR23 identity, all 22 RAM loader blocks, JEDEC 856014 and two fresh identical 1 MiB reads matching the original backup. It erased/programmed only the 84 changed application sectors, with header sector 0x3000 last, and verified every page and sector. The final full readback exactly matches candidate SHA256 `a93b93a788452026e2b155a8797805ef7d1d55be0af1e2eb7fcdd9fda49388d3`.

Independently checked saved metadata, both fresh backups, desired/after images, all 84 sector records and all 1344 page-program completions. Every completion has matching tag, status zero and the exact expected full residue. All other sectors are preserved. [Flash evidence](evidence/flash-20261104.json). No reset command was sent. Subsequent USB enumeration showed no controller; this does not establish normal boot. Next: reconnect normally, then HID BLE pairing and actual button capture, followed by iPhone validation.

## First live custom GATT capture: 2026-11-04

The flashed controller booted far enough to advertise `IG05 Gamepad(BLE)`, connect, expose AE40/AE42, and deliver the new protocol. A bounded 90-second capture received 78 valid eight-byte AE42 packets: one initial baseline and consecutive sequence values 0..77, with no overflow flags. AE02 also sent the stock initial `ff`. User-confirmed ordered tests establish A=0x1, B=0x2, X=0x8, Y=0x10, Up=0x10000, Down=0x20000, Left=0x40000, Right=0x80000. A separate isolated A press/release confirms mask 0x1. Other input events are unlabeled. [Capture evidence](evidence/cfw-gatt-20261104.json).

This establishes application boot and app-accessible vendor button notifications on macOS. Notifications arrived in batches, so low-latency delivery is not yet established. The probe now adds a Mac activity assertion and monotonic timestamps to investigate capture-side throttling. L/ZL/R/ZR/Capture/Home mapping, normal HID reports, reconnect/standby, and actual iPhone background/locked operation remain pending.

## Bluetooth transmit wake correction, 2026-11-04

The first installed firmware queues packets but omits the stock dispatcher’s subsequent Bluetooth-task wake. This explains a plausible cause of delayed batches; it still requires a live comparison. The timed second capture received only a baseline and pairing-button releases, so L/ZL/R/ZR/Capture/Home/Minus/Plus are not mapped yet. Mac activity assertions did not resolve that capture.

The corrected binding calls the independently traced `stock_bt_wake` at 0x1e16678 after releasing its critical section, including when the queue reports backpressure. The OEM dispatcher calls the same wake after its send path; it posts to the `btstack` task through RAM 0x495e. Host tests verify the ordering and backpressure behavior. The corrected candidate is `574f6542ef749741721d8bf040aa0b45eb8837d9357b900865473400027d2c59`, with 562 payload bytes. All 58 Python tests and sanitized C tests pass. It has not yet been flashed.

The installer now accepts either the original application or the pinned, fully verified previous installation as its preimage. It preserves current settings and writes only sectors actually changed: 0x26000, 0x35000, 0x36000, 0x55000, then header sector 0x3000. Other preimages still fail. [Fix evidence](evidence/cfw-wakeup-fix-20261104.json).

## Corrected firmware installed, 2026-11-04

Attempt `flash-attempt-20261104-101746` successfully updated five sectors. Independently checked two fresh full reads, all five sector/80 page-program records, and the final 1 MiB readback. The actual image SHA256 is `4ddf865a61576ad00e08374833df34cda679e0bae6f61190a8d86458a9286294`; it differs from the offline candidate because current settings outside the application were preserved. It exactly matches the planned merged image. [Installation evidence](evidence/flash-wakeup-fix-20261104.json). The corrected application connected over BLE and sent baseline `4702000200000000`; button/latency validation is in progress.

## Corrected-build button mapping verified, 2026-11-04

The corrected image connected and delivered a baseline plus ten separate press/release pairs for the user-confirmed order A, B, L, ZL, R, ZR, Capture, Home, Minus, Plus. Sequences 0..20 were consecutive and no overflow flag occurred. Arrivals were spread across the physical test, instead of the previous long delayed batches; exact physical-to-host latency was not measured. The capture was stopped after mapping and no probe remains connected. [Capture evidence](evidence/cfw-fixed-controls-20261104.json).

All 16 requested gameplay controls are mapped across the confirmed captures. Home sets bits 12 and 24 together, so a driver must treat mask 0x01001000 as one logical button. See [protocol and complete mapping](button-protocol.md) and [machine-readable masks](evidence/ananke-button-map.json). Normal HID reports, standby/wake and iPhone foreground/background/locked tests remain outstanding.
