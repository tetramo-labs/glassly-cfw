# Plan

Goal: support Ananke Gen 2 as a controller in ../glassly, including actual iOS background/locked input. Prefer the existing official firmware if its button stream is accessible to the app; custom firmware is a fallback.

- [x] Create separate local research repository; preserve original Gamebrick repository.
- [x] Verify retained Gamebrick originals without modifying them.
- [x] Enumerate Ananke USB and capture GET-only model/version responses.
- [x] Locate official guide, printed-manual mirrors and official firmware/manual directory links.
- [x] Prepare and offline-test an identity-first backup tool with no flash writes.
- [x] Visually inspect all Chinese/English original-manual panels; preserve the PDF locally and record its hash. No update-entry procedure is documented.
- [x] Read official firmware-update manual; Capture + Home while plugging in USB works. Observed 4c4a:2342 / BR23UBOOT1.00.
- [x] Preserve and hash official updater and V0900/V0901 packages; unpack both offline.
- [x] Complete live SCSI identification (BR23 / UBOOT1.00) and activate the separately reviewed BR23 backup path.
- [x] Run INQUIRY-only identification from the user's interactive terminal.
- [ ] Obtain two identical full BR23 flash reads and preserve originals.
- [ ] Verify and pin backup metadata, unpack actual partition layout and installed application.
- [x] Locate Glassly controller registry, existing Gamebrick driver, Bluetooth background declaration and restoration hooks.
- [ ] After backup, power-cycle and enter Switch pairing (Pair + Up); establish whether it exposes BLE/GATT, independently of system game-controller recognition.
- [ ] Discover services and capture app-accessible notifications for isolated presses/releases and combinations. Compare other documented modes if Switch mode provides no usable stream.
- [ ] If a stock stream is available, implement an Ananke controller in ../glassly using its observed identity and packet format; test pairing, reconnect and input mapping.
- [ ] Test the driver on an actual iPhone in foreground, background and locked states, including standby/wake and connection restoration.
- [ ] Only if stock behavior is insufficient, trace key scanning, vendor BLE services, CCC handling and lifecycle independently of HID readiness.
- [ ] If CFW is needed, base it on the latest official release for the confirmed variant (supplied V0900 for Purple/Gray/Cream Yellow); derive packaging from the installed layout.
- [ ] Design and audit a patch for the selected official application; establish application-independent recovery before flashing.
- [ ] Test HID, all physical buttons over vendor BLE, reconnect/standby, and real iOS background/locked delivery separately.
