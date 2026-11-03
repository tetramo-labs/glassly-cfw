# Firmware backup procedure (macOS)

Update entry and SCSI identity were verified on 2026-11-01: **BR23 / UBOOT1.00**, USB `4c4a:2342`, at physical USB location `0x00100000`. Keep this unit on the same port and disconnect other IINE/Jieli controllers. The device still contains its original `0x0601` firmware.

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
sudo python3 -u research/backup_controller.py identify --location 0x00100000 --wait 30
```

This sends only standard SCSI INQUIRY. USB naming alone is not accepted for loading code. An identity other than BR23 / UBOOT1.00 is rejected by backup.

## Back up

From the user's interactive terminal, with the controller in update mode:

```sh
cd ~/dev/glassly-mini-gamepad-plus
sudo python3 -u research/backup_controller.py backup --location 0x00100000 --wait 30
```

The tool rechecks the live SCSI identity, uploads the exact pinned BR23 loader into RAM at `0x12000`, verifies all 22 blocks, and only then executes it with SPI NOR argument 1. It cross-checks flash IDs, derives capacity from the live JEDEC density, saves identity metadata, and reads all flash twice in 256-byte blocks. Every command passes a strict allowlist; flash erase/program, key/fuse writes, and command reconfiguration are forbidden. USB transfers, mode wait and total operation have bounded timeouts. This first BR23 hardware backup remains untested until run.

A successful directory contains two read-only dumps and metadata with `complete: true`, `passes_match: true`, byte count and SHA256. Failed/partial captures are retained and are not valid restore images. Verify the exact output directory:

```sh
python3 scripts/verify_backup.py research/device-backup-YYYYMMDD-HHMMSS
```

Preserve originals and analyze separate copies. After success, power-cycle and verify normal USB/buttons return. A successful backup does not establish that restoration after a broken application will work.

macOS USB access requires interactive sudo. Background administrator launches previously failed Removable Volumes authorization; do not automate Ghostty or send terminal passwords to the agent.

## Firmware base

The user selected the Purple/Gray/Cream Yellow model group and requested the latest official firmware as CFW base. The supplied matching package is `IG05_V0900.ufw`; V0901 is for Baby Blue/Mint Chocolate Green. Preserve the currently installed firmware before updating. Packaging and protected regions must come from the actual unit's full backup, not assumed from the OEM archive.

## Current diagnostic retry

The first hardware attempt (`device-backup-20261101-153148`) failed the USB status check during RAM upload, before loader execution or flash reading. Its coarse error did not identify the failing status field. The tool now retains raw command/status details in `metadata.json` and prints them on failure; all rejection checks remain unchanged. Unplug, turn off, and re-enter Capture + Home update mode on the same port before retrying the backup command above. Each run creates a new directory and preserves earlier evidence.
