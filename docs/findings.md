# Findings

Updated 2026-11-01. Update entry and live BR23 SCSI identity confirmed; reviewed BR23 backup tool ready, first full read pending.

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
