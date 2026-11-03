# Glassly Mini Gamepad Plus

Research toward supporting the **IINE Mini Retro Ananke Gen 2** (L1254/L1255 family) as a controller in Glassly, preferably using official firmware and an app-accessible Bluetooth button stream.

Current stage: live BR23 bootloader identified; firmware backup ready. **No Ananke firmware backup or custom image has been produced yet.** The connected controller reports USB `4353:800c`, model `ig05`, firmware `0x0601`. See [findings](docs/findings.md), [backup procedure](docs/backup.md), and [plan](docs/plan.md).

This is a separate port of the work in [glassly-gamebrick-cfw](https://github.com/tetramo-labs/glassly-gamebrick-cfw). Its images and patch offsets are not compatible by assumption.

## Tools

- `research/query_device.py`: bounded GET-only normal-mode identification; requires Python `hidapi`.
- `research/backup_controller.py identify`: SCSI INQUIRY only; no RAM loader or flash writes.
- `research/backup_controller.py backup`: gated BR23 RAM-loader upload/readback, then two complete flash reads. No flash or fuse writer is implemented.
- `scripts/verify_backup.py`: offline verification of both backup copies against metadata.

The backup/probe uses Python's standard library and a compiled macOS IOUSBHost helper. Run `python3 scripts/setup.py --reference ../glassly-mini-gamepad` to obtain the pinned BR23 loader from the existing local checkout and compile the helper. No OEM firmware is copied.

Offline checks: `python3 -m unittest discover -s research -p 'test_*.py'`.

Original dumps and downloaded artifacts are ignored by Git. This repository is local; no remote is configured.

If CFW is necessary, its base follows the user request for the latest official firmware for this variant. The supplied matching package is `IG05_V0900.ufw` for the Purple/Gray/Cream Yellow group. Back up the installed `0x0601` firmware before making any installation change.
