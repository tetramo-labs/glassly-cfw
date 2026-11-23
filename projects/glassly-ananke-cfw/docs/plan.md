# Current plan

Goal: Ananke Gen 2 input in Glassly, including real iPhone background/locked delivery.

- [x] Preserve two identical original 1 MiB reads with metadata and hashes.
- [x] Independently verify BR23 identity, loader, installed map and matching V0900 OEM application.
- [x] Build and audit a custom AE42 v2 button stream in HID BLE mode (Pair + Right).
- [x] Install with explicit acceptance of unproven recovery, preserve storage, and verify the full flash.
- [x] Correct Bluetooth task wake and verify all 16 controls over macOS BLE.
- [x] Prepare the public per-unit flasher, pinned setup and macOS/Windows/Linux instructions.
- [x] Replace Glassly's foreground system-gamepad integration with the observed BLE protocol.
- [ ] Validate Windows/Linux USB paths on hardware; offline checks are not hardware validation.
- [ ] Validate normal HID coexistence, standby/wake, two controllers and reconnect.
- [ ] Test real iPhone foreground, background, locked-screen and state-restoration behavior separately.
- [ ] Demonstrate application-independent recovery and restore; experimental risk acceptance does not establish recovery.

Dated research and superseded decisions remain in findings.md and the evidence records. No additional hardware write is part of publication or app integration.
