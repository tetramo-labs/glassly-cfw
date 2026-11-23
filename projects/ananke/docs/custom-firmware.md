# Experimental Ananke V0900 firmware

The corrected 562-byte payload was installed on 2026-11-04, verified against a complete flash readback, and tested over macOS BLE with all 16 physical controls. It wakes the OEM Bluetooth task after queue insertion so transitions arrive separately. See [protocol](button-protocol.md) and [latest live capture](evidence/cfw-fixed-controls-20261104.json). Normal HID coexistence, standby/wake and real iPhone background/locked behavior remain unverified.

## Build and packaging

`firmware/button_stream.c` maintains a 16-entry transition queue. `firmware/ananke_v0900.c` binds the scan, vendor CCC and disconnect hooks to the pinned V0900 application. State occupies 96 bytes in a 128-byte page at RAM `0xc280`. The heap start moves to `0xc300`; the input task gains 512 bytes of stack. The original RAM relocation instructions and initializer remain unchanged.

The payload starts at flash execution address `0x01e52c38` and ends at `0x01e52e6a`. Eight checked preimage edits replace three calls and five immediate values. The disassembly audit checks every instruction and direct branch, plus the narrowly scoped CCC-set tail return. Nested OEM critical sections protect queue ownership; `stock_bt_wake` at `0x01e16678` runs outside the critical section. Static checks and extra stack headroom do not prove worst-case stack use or interrupt latency.

The application allocation remains 343,208 bytes at physical `0x3140` in the used active area `0x3020..0x5717c`. The shorter OEM app plus payload is padded to fit. All partition offsets, sizes, configuration bytes, calibration, settings and keys are preserved. Only application bytes and app/area checksums change. The sector writer preserves surrounding bytes, writes the header sector last, and verifies every page, sector and the complete flash.

`research/flash_ananke.py` is the public entry point. It derives the encryption key and plan from two matching reads of the connected unit, and rejects unknown bootloaders, applications, configuration or layouts. It requires a local hash-pinned official UFW; OEM and per-device images are never distributed. The bundled `firmware/dist/payload.bin` contains only our compiled patch, with its source/build hashes and symbols in `payload.json`.

The historical `scripts/build-candidate.sh` rebuilds with Docker and the official pi32v2/r3 compiler pinned in `sources.lock.json`. It expects the original research backup/extractions and the toolchain in the sibling `glassly-mini-gamepad` checkout. These private inputs are deliberately absent from a fresh clone. Public installation instead reconstructs the pinned application from the supplied UFW and bundled payload without a compiler or sibling checkout.

Corrected application SHA256: `833e76739433639e8ad81b3d7d187ac2fe6cd7729088184d8e07ca25f7e0f350`.
Payload SHA256: `a8415156362682a565dcf179f4da985798accd9c3960bcfde419093e8bffe83c`.
A complete image's hash depends on the unit key and live settings. The public planner reproduces the recorded candidate and latest verified readback exactly from their respective saved inputs.

## Experimental limits

Independent recovery after a nonbooting application is not demonstrated. Capture + Home entry has only been observed with a functioning application. The user explicitly accepted possible device loss for the two experimental installations. The public installer requires that acceptance separately. Mac BLE tests do not establish iOS background support.

## Installation history

## Explicit experimental-install exception, 2026-11-04

The user accepted possible device loss and waived independent recovery for this unit. This does not make the candidate production-ready or prove runtime behavior. The earlier offline manifest intentionally retains its unvalidated status. The separate [authorization and loader review](evidence/experimental-install-authorization.json) records this exception.

The dedicated installer verifies the pinned original metadata/two backups and candidate, rechecks live identity, uploads/readbacks the pinned loader, and saves two fresh full reads before writing. It preserves current settings outside the application, writes only the 84 changed 4 KiB sectors in 256-byte pages, checks every page/sector, and verifies the complete final image. The header sector is last. Any failure stops; no automatic retries, protection unlocks, full-chip erase, fuses or reset are supported.

The attempted agent launch required sudo authentication before the script ran. To perform the authorized experiment in the user's terminal:

```sh
cd ~/dev/glassly-flash-tool/projects/ananke
sudo python3 -u research/flash_controller.py --location 0x02100000 --wait 3 --accept-unrecoverable-risk
```

Use only while this controller is still at that physical port in BR23 update mode. A successful installation prints `FLASH VERIFIED`; a USB identity, checksum, status or readback mismatch aborts and saves the incomplete attempt locally. No flash has occurred as of this note.

## Installation completed, 2026-11-04

`research/flash-attempt-20261104-100838` completed successfully. Independently rechecked its two full pre-install reads, pinned original/candidate, all 84 sector records, 1344 successful page-program records, and final full readback. The fresh backups match the original `da281f11…`; the complete post-flash image exactly matches candidate `a93b93a7…`. The application header sector was written last and all other sectors are unchanged. No reset command was sent. Boot/HID/GATT and physical iPhone validation remain pending.

## Bluetooth transmit wake correction, 2026-11-04

The first installed firmware queues packets but omits the stock dispatcher’s subsequent Bluetooth-task wake. This explains a plausible cause of delayed batches; it still requires a live comparison. The timed second capture received only a baseline and pairing-button releases, so L/ZL/R/ZR/Capture/Home/Minus/Plus are not mapped yet. Mac activity assertions did not resolve that capture.

The corrected binding calls the independently traced `stock_bt_wake` at 0x1e16678 after releasing its critical section, including when the queue reports backpressure. The OEM dispatcher calls the same wake after its send path; it posts to the `btstack` task through RAM 0x495e. Host tests verify the ordering and backpressure behavior. The corrected candidate is `574f6542ef749741721d8bf040aa0b45eb8837d9357b900865473400027d2c59`, with 562 payload bytes. All 58 Python tests and sanitized C tests pass. It has not yet been flashed.

The installer now accepts either the original application or the pinned, fully verified previous installation as its preimage. It preserves current settings and writes only sectors actually changed: 0x26000, 0x35000, 0x36000, 0x55000, then header sector 0x3000. Other preimages still fail. [Fix evidence](evidence/cfw-wakeup-fix-20261104.json).

## Corrected firmware installed, 2026-11-04

Attempt `flash-attempt-20261104-101746` successfully updated five sectors. Independently checked two fresh full reads, all five sector/80 page-program records, and the final 1 MiB readback. The actual image SHA256 is `4ddf865a61576ad00e08374833df34cda679e0bae6f61190a8d86458a9286294`; it differs from the offline candidate because current settings outside the application were preserved. It exactly matches the planned merged image. [Installation evidence](evidence/flash-wakeup-fix-20261104.json). The corrected application connected over BLE and sent baseline `4702000200000000`; button/latency validation is in progress.

## Corrected-build button mapping verified, 2026-11-04

The corrected image connected and delivered a baseline plus ten separate press/release pairs for the user-confirmed order A, B, L, ZL, R, ZR, Capture, Home, Minus, Plus. Sequences 0..20 were consecutive and no overflow flag occurred. Arrivals were spread across the physical test, instead of the previous long delayed batches; exact physical-to-host latency was not measured. The capture was stopped after mapping and no probe remains connected. [Capture evidence](evidence/cfw-fixed-controls-20261104.json).

All 16 requested gameplay controls are mapped across the confirmed captures. Home sets bits 12 and 24 together, so a driver must treat mask 0x01001000 as one logical button. See [protocol and complete mapping](button-protocol.md) and [machine-readable masks](evidence/ananke-button-map.json). Normal HID reports, standby/wake and iPhone foreground/background/locked tests remain outstanding.
