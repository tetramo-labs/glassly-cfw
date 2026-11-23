# Working instructions

This repository contains the desktop flasher and the device firmware projects. Read README.md first.
Device sources and research live in projects/. Read the device README and its AGENTS.md when present.
The desktop app bundles hardware-verified images from firmware/.

## Rules that exist because of the 2026-11-13 Gamebrick incident

A tester's Gamebrick of a previously unseen kind (new flash layout, new flash part, new factory
build) was accepted by identity checks, flashed with a fully verified write, and then never came
up again. The write was correct; the application did not run on that hardware. Nothing below may
be relaxed to get past a refusal.

- **Writes are gated on a hardware-verified allowlist, not on structural validity.** Each device
  module keeps an explicit set of unit kinds (for the Gamebrick: `(flash layout, flash part)` in
  `devices/gamebrick/layout.py::HARDWARE_VERIFIED`; for the 8BitDo controllers: the exact
  installed baseline hashes; for the Ananke: the exact bootloader, configuration, layout and
  application hashes) on which the shipped images have been flashed and seen booting. Any other
  unit gets backup and "restore own backup" only, with a message asking for the backup folder.
- **Accepting a new kind and writing to it are never one change.** The sequence is: the unit is
  backed up (backup-only modes exist for every controller); the dump is decoded and reviewed
  offline; the first flash of that kind happens on a developer-owned controller with a proven way
  back; only then is the kind added to the allowlist, in its own commit, citing the evidence.
- **Only hardware-verified images ship.** An image that has only passed emulation or offline
  checks is not bundled for install, even if it looks like a small change; it is flashed on the
  developer's unit first. The Zero 2 steady-LED build is such an image and is not bundled.
- **Every write mode keeps the way back.** Backups are taken before any erase and the app can
  restore a controller's own earlier backup; a session's `flash-pass1.bin` is the recovery image
  of record. Never add a mode that writes without a backup.
- **Documented exception: MemoMind One.** Its stock firmware has no command to read its flash, so
  Back up records identity only. Restore sends the vendor's own 1.0.3.127 image (the one the MemoMind
  app installed on the developer's glasses, replayed byte for byte in the tests) through the same
  staged, CRC-checked OTA; this app has not yet run that path on glasses, so the first restore happens
  on the developer's pair. The identity gate admits model H001Y whose reported MAC is the address
  connected to, on any hardware, firmware or Glassly revision (the owner's call on 2026-11-16); keep
  the model and MAC checks.
- **Refusals name what was seen.** Identity refusals print the values the controller reported
  (flash part, layout, application build) so a new kind can be reviewed from the message alone.

- **Rokid Glasses** are switched off: `devices/rokid` and its tests stay, but the device is not in the
  `DEVICES` registry, so neither the app nor the command line offers it. When it is back, it installs an app over
  adb rather than firmware. `devices/rokid` gates install on
  `INSTALL_VERIFIED` build fingerprints and the launcher takeover on `TAKEOVER_VERIFIED`; both start empty. The
  `GLASSLY_FLASHER_DEVELOPER=1` override exists only for the first install on the developer's own glasses and must
  never be set by the app or documented as a user step.

Do not commit AI attribution. Keep `.gitattributes` (`firmware/** -text`): Windows checkouts
once rewrote a bundled JSON and broke its pinned hash.
