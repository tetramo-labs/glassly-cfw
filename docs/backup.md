> Historical macOS research procedure. For the public macOS/Windows/Linux identify, backup and install commands, see [README.md](../README.md).

# Firmware backup procedure (macOS)

Update entry and SCSI identity were verified on 2026-11-01: **BR23 / UBOOT1.00**, USB `4c4a:2342`, at physical USB location `0x00100000`. Keep this unit on the same port and disconnect other IINE/Jieli controllers. The device still contains its original `0x0601` firmware.

**Current port, 2026-11-03:** the controller is now in normal mode at `0x02100000`. The old-port retry found no device and sent no SCSI commands. Enter update mode on the current port before proceeding. The normal-mode registry observation is not a substitute for the live SCSI identity check.

## Enter update mode

Unplug, turn the controller off, hold **Capture + Home** (the two angled front buttons), and reconnect USB. This is the procedure in the official Ananke firmware-update manual and was observed working. Pair + B is mouse mode; the earlier Gamebrick shortcut suggestion is superseded.

The OEM updater's erase/upgrade steps are for installation, not backup. Do not run them before preserving the current firmware.

## Setup

Already completed on this checkout. To reproduce from the pinned local reference dependency:

```sh
cd ~/dev/glassly-mini-gamepad-plus
python3 scripts/setup.py --reference ../glassly-mini-gamepad
python3 -m unittest discover -s research -p 'test_*.py'
```

Setup validates the source revision and exact BR23 loader hash and compiles the macOS helper. No firmware dumps are copied and no controller is opened. The backup/probe uses Python's standard library.

## Identify

Already completed successfully in `research/probe-20261101-151534/`. To repeat:

```sh
sudo python3 -u research/backup_controller.py identify --location 0x02100000 --wait 30
```

This sends only standard SCSI INQUIRY. USB naming alone is not accepted for loading code. An identity other than BR23 / UBOOT1.00 is rejected by backup.

## Back up

From the user's interactive terminal, with the controller in update mode:

```sh
cd ~/dev/glassly-mini-gamepad-plus
sudo python3 -u research/backup_controller.py backup --location 0x02100000 --wait 30
```

The tool rechecks the live SCSI identity, uploads the exact pinned BR23 loader into RAM at `0x12000`, verifies all 22 blocks, and only then executes it with SPI NOR argument 1. It cross-checks flash IDs, derives capacity from the live JEDEC density, saves identity metadata, and reads all flash twice in 256-byte blocks. Every command passes a strict allowlist; flash erase/program, key/fuse writes, and command reconfiguration are forbidden. USB transfers, mode wait and total operation have bounded timeouts. Live flash identity is confirmed as JEDEC 856014 (1 MiB); two matching complete reads are verified in `research/device-backup-20261103-174931`.

The separately evidenced BR23 ROM policy requires residue exactly 512 for pinned 512-byte FB06/FD07 transfers. All 22 blocks have now passed hardware readback. The subsequent FB08 also returned a full residue of 16 with its expected acknowledgement. The narrowly scoped jump policy requires all 22 verified blocks, exact address/argument, residue 16 and matching reply prefix. Both paths still reject nonzero status, wrong signature/tag and unexpected lengths/residues. After the verified jump, the three fixed-length identity queries require residue 16. Their live replies must agree on the measured JEDEC 856014 and 0x8000 buffer before the separate flash-read policy enables aligned 256-byte FD05 reads within 1 MiB, with residue exactly 256. Other commands retain zero-residue checks. Every accepted query reply is saved immediately. The first flash block was retained after its initial status rejection; two complete matching reads have now passed independent metadata verification. Forty offline tests pass in normal and optimized Python.

A successful directory contains two read-only dumps and metadata with `complete: true`, `passes_match: true`, byte count and SHA256. Failed/partial captures are retained and are not valid restore images. Verify the exact output directory:

```sh
python3 scripts/verify_backup.py research/device-backup-YYYYMMDD-HHMMSS
```

Preserve originals and analyze separate copies. After success, power-cycle and verify normal USB/buttons return. A successful backup does not establish that restoration after a broken application will work.

macOS USB access requires interactive sudo. Background administrator launches previously failed Removable Volumes authorization; do not automate Ghostty or send terminal passwords to the agent.

## Firmware base

The user selected the Purple/Gray/Cream Yellow model group and requested the latest official firmware as CFW base. The supplied matching package is `IG05_V0900.ufw`; V0901 is for Baby Blue/Mint Chocolate Green. Preserve the currently installed firmware before updating. Packaging and protected regions must come from the actual unit's full backup, not assumed from the OEM archive.

## Historical diagnostic retries

The first hardware attempt (`device-backup-20261101-153148`) failed the USB status check during RAM upload, before loader execution or flash reading. Its coarse error did not identify the failing status field. The diagnostic retry (`device-backup-20261103-000327`) isolated the first FB06 command: status 0, matching tag/signature, but residue 512 of 512 bytes. All rejection checks remain unchanged. Do not repeat backup unchanged.

For that exact failure, leave the controller connected and run the separate read-only diagnostic in the user's interactive terminal:

```sh
cd ~/dev/glassly-mini-gamepad-plus
sudo python3 -u research/diagnose_upload.py \
  --failed-backup research/device-backup-20261103-000327 \
  --location 0x00100000 --wait 3
```

It validates the prior failure and live identity, then reads only the first 512 RAM bytes at `0x12000`, saves them under ignored `research/ram-probe-*`, compares against the pinned loader, and stops. It cannot upload, execute code or access flash. A successful comparison is diagnostic evidence only, not permission to ignore the original status mismatch. If the device was unplugged, power-cycled or moved to another port, record that before interpreting the result; RAM persistence is not guaranteed.

Completed the repeat diagnostic as `ram-probe-20261103-001159`: the rejected data matches the pinned first loader block exactly and its saved hash matches metadata. Both FB06 and FD07 still reported status 0 with residue 512. The result supports a ROM status-reporting quirk, but the backup tool still rejects it. No further identical retry is needed; review the transport policy before proceeding. See [evidence](evidence/br23-residue.json).

The subsequent narrowly scoped ROM RAM policy described above supersedes that rejection for pinned RAM transfers only. Do not rerun the old-port diagnostic as the next step; use the current-port backup after physically entering update mode.
