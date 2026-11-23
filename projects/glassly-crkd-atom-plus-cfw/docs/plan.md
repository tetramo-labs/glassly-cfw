# ATOM+ port plan

## Current priority — 2026-11-09

CRKD 1.0.365 has been extracted and decompiled, its public firmware catalog
retrieved, and all three ATOM+ images saved with hashes. The app includes a stock
BLE input test mode. See [the evidence and protocol](android-app-analysis.md).
Next: capture an actual ATOM+ in official test mode, validate press/release/chords
and stick axes, then establish idle/reconnect behavior. This takes priority over
building custom firmware. Root was not needed for the completed APK extraction.

## 1. Identify the exact target and collect stock evidence

- [x] Create a separate workspace; review the four local controller ports.
- [x] Locate vendor product/update pages and ATOM+-specific FCC exhibit leads.
- [ ] Retrieve the internal-photo and manual PDFs; verify file hashes and inspect
  chip markings. Record ambiguity rather than guessing from logos or packages.
- [ ] Match a physical unit's label/model/board revision to the documents.
- [ ] Record stock firmware version and CRKD app version/platform before updates.
- [x] Obtain a legitimate app package or user-controlled app capture; inspect its
  firmware catalog, product selection, BLE UUIDs, update library and image URLs.
- [x] Download catalog-listed ATOM+ stock images and record URLs, versions, sizes
  and SHA256. Matching the installed controller version remains pending.

Done when hardware identity and artifact provenance are recorded, with explicit
unknowns for anything still inaccessible. Public document work can proceed
without hardware; live interface verification requires a controller.

## 2. Inspect the stock app interface first

- [ ] Enumerate normal USB descriptors if USB data is supported; never infer
  chipset/model from a Switch-compatible product name alone.
- [ ] Capture BLE advertisements and service/characteristic properties in each
  documented mode, including app/CTRL mode. Correlate with physical power cycles.
- [ ] Observe the official app connecting and configuring the controller.
- [x] Recover the app's stock testing/diagnostic command and notification decoder.
- [ ] Verify that this unit actually delivers button and stick values through
  that interface, including release states and operation on battery.
- [ ] If available, validate baseline, press/release, chords, both sticks,
  reconnect and battery operation with a small bounded receiver.

Decision: if stock notifications meet Glassly's needs, implement the app driver
and retain this research without requiring a firmware patch. If absent or
insufficient, proceed to firmware analysis. Configuration support is not proof
of input streaming or concurrent gamepad/app connections.

## 3. Establish firmware format, update path and restoration

- [ ] Identify ISA, sections, compression/encryption, integrity checks, signatures
  and model/version checks from stock bytes and updater code.
- [ ] Reproduce unpack/repack byte-for-byte offline before changing anything.
- [ ] Recover transport framing, acknowledgements, timeouts and update entry;
  establish whether a wired path exists independently of the running app.
- [ ] Identify bootloader, app, configuration, calibration and pairing storage.
- [ ] If readback is supported, obtain two identical complete backups with
  per-region hashes. Record unreadable regions; an OTA package is not a backup
  of unit-specific calibration, keys or settings.
- [ ] Define and verify a stock restoration procedure and assess recovery after
  an invalid application. Do not call normal OTA recovery application-independent.

Done when there is an ATOM+-specific update/restore design, known write ranges,
and a documented account of signature constraints and recovery limitations.
No flasher implementation should borrow another controller's command sequence.

## 4. Minimal firmware experiment, then notification experiment

- [ ] Prepare a concrete first experiment only after the preceding evidence:
  stock reflash followed by a bounded, observable name/version-string change
  where that change is valid for the discovered format and authentication.
- [ ] Verify complete readable application contents, preserved device regions,
  stock inputs and successful boot before adding input-stream hooks.
- [ ] Locate input scanning/debounce, Bluetooth send routine, CCC/subscription
  lifecycle, task wakeup, sleep policy and reconnect reset path.
- [ ] Audit code placement, startup relocation/decompression, RAM allocation,
  stacks and calling conventions; test actual instructions where practical.
- [ ] Build a notification-only probe before binding buttons and analog axes.

Experiments remain future work: the present request establishes research and
planning, not a claim that flashing is ready or recovery has been demonstrated.

## 5. Glassly input contract and integration

- [ ] Define a versioned, explicitly documented protocol after observing inputs:
  capability/version handshake, baseline state, sequence, button bitmap, release
  transitions, overflow handling and optional normalized stick axes.
- [ ] Deliver buttons first; add both sticks with measured center/deadzone,
  calibration, rate limits and change thresholds. Motion/rumble are later scope.
- [ ] Implement native iOS/Android support in the Glassly repository following
  its own instructions. Use observed identifiers and capabilities for discovery.
- [ ] Validate ordered presses/releases, chords, rapid input, lost packets,
  disconnect while held, reconnect baseline and subscription disable/re-enable.
- [ ] Separately test normal HID, battery idle/sleep/wake and real iPhone/Android
  foreground/background/locked delivery. Measure battery impact of stick updates.
- [ ] Document tested variants and limitations; package reproducible source and
  restoration instructions only once hardware evidence supports them.

## Immediate next session

1. With an ATOM+ available, collect installed version and live GATT inventory,
   then capture the official app entering/exiting test mode and receiving input.
2. Validate the recovered FF02 packet layout, physical button mapping, heartbeat
   requirements and mode persistence without invoking OTA or calibration.
3. Continue FCC chip identification and offline image-format analysis if CFW is
   still useful after stock-mode validation.
