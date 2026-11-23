# Glassly CRKD ATOM+ firmware research

Investigate a CRKD **ATOM+ / Atom Plus** port that exposes buttons and eventually
thumbsticks over an app-readable BLE notification stream for Glassly, following
the Micro, Zero 2, Ananke and Gamebrick projects.

**Status: Android app decompiled, 2026-11-09.** Extracted CRKD Android 1.0.365
(365), recovered its ATOM+ BLE test-mode and OTA paths, and downloaded all three
ATOM+ images listed in the public firmware catalog. Stock test mode has a
buttons/sticks/triggers notification decoder in the app and may meet Glassly's
needs without CFW. Controller behavior, chipset, image decoding and recovery
remain unverified. No controller commands or firmware writes have been sent.

- [Findings and sources](docs/findings.md)
- [Implementation plan and completion criteria](docs/plan.md)
- [Hardware, captures and other inputs needed](docs/needs.md)
- [Android decompilation and recovered protocol](docs/android-app-analysis.md)

The next milestone is a live stock ATOM+ test-mode capture: subscribe to FF02
under FF00 and verify the app-derived commands and packet layout. The Android
app extraction did not require root or access to account data. App-based updates
and a host-side CRC alone do not establish that modified firmware can be installed.

`research/downloads/` holds local OEM files and third-party research material;
`research/captures/` holds private device captures and backups; `build/` holds
generated artifacts. These directories are ignored. Record downloaded artifact
hashes and provenance in `sources.lock.json` when bytes are available.
