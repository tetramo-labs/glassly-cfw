# Remaining firmware work

On 2026-11-05 the user explicitly expanded scope to experimental firmware and
flashing, accepting the risk of bricking controllers. Start with existing firmware
or a minimal change. Earlier emulation results remain offline evidence.

- [x] Reflash existing v1.08 using the official updater, then verify readback and boot.
- [x] Build and flash a minimal observable patch before integrating the GATT stream.
  Our native script verified all 73,216 bytes and rebooted into USB product
  `Glassly Zero 2 test01`; the metadata page remained byte-identical.
- [x] Use local REA to recover updater method anchors; reproduce the macOS
  packet builder and erase/version/reset arguments in offline ARM64 emulation.
- [x] Implement a hash-pinned native macOS flasher with backups, CRC validation,
  exact product/location matching, full readback and reset after verification.
- [x] Build a bounded CoreBluetooth scanner/service inspector/FF13 subscriber,
  preserving exact source hashes and local event logs.
- [x] Trace separate startup BLE name `80EL` and forced-off command-02 bit 2.
  Verify 9 name cases and 16 stock/probe visibility cases in offline execution.
- [x] Build a single-instruction BLE visibility probe on the verified name image;
  retain the same RAM, stack, layout and GD32 section. Extend flasher hash pins.
- [x] Flash/read back the BLE visibility probe. All 73,216 bytes match, only
  `0x2310` differs from the name-only baseline, metadata is unchanged, USB boot
  succeeds. BLE `80EL` now advertises with USB connected; FF10/FF13 and CCC 2902
  are discovered and subscription succeeds. No button stream is included.
- [x] Test initial advertising/discovery/subscription on battery: succeeds, then
  times out after 61.097 seconds; the following scan finds no candidate.
- [x] Compare bounded FF13 keepalive writes on battery: a completed run remained
  connected for 188.395 seconds with nine acknowledged writes; one earlier
  attempt disconnected before any write. Since the handler clears both idle
  counter and watchdog, this does not isolate the exact shutdown mechanism.
- [x] Reconnect and toggle notifications enabled/disabled/enabled after that run.
  All three host callbacks succeeded. No notification data received.
- [x] Execute 48 idle-guard and 24 threshold-setter cases offline; no power I/O.
- [x] Build the next button-streaming experiment: four hooks, reserved OEM pool
  block, 16 snapshots, explicit A1/A0 lifecycle, sample-based qualification and
  command-09 ACK gating. See `buttons-probe.md` and its offline evidence.
- [x] Flash/read back `buttons-probe`: all 73,216 bytes match; metadata unchanged,
  USB boot and eight-byte BLE baseline verified. A1/A0 acknowledged around a
  187.590-second USB-connected hold.
- [x] Verify all 12 physical press/release pairs and map buttons from a
  user-confirmed ordered test. A+B held/released works; 27 consecutive packets
  have no gaps or overflow flags.
- [x] Battery button/idle test: A press/release, 187.951 seconds connected,
  166.260 seconds idle after release, no keepalives, A0 acknowledged.
- [ ] Integrate firmware idle/watchdog ownership with the notification sender,
  then test notification delivery and device-side CCC/reset ordering. Long-term
  battery use, idle/wake and sleep remain unverified.
- [x] Build and audit a separate notification/idle probe: two complete BL hooks,
  220 bytes in the stock-cleared tail, no persistent RAM or button components.
  Actual startup and 2,098 event cases pass offline with no instruction stubs;
  sleeping sends skip and exact-fill ring submissions are rejected.
- [x] Flash `notify-probe`, verify all 73,216 bytes and unchanged metadata, then
  receive four matching one-byte FF13 notifications (`31 a5 00 ff`) over BLE
  with USB connected. This verifies tail execution and the tested command-09
  dynamic-handle/one-byte payload format on hardware.
- [x] Test a battery subscribe-only session without host keepalive writes: 188.448
  seconds connected, followed by reconnect and four matching notification echoes.
  The probe's any-BLE-connection idle policy is experimental, not final CCC ownership.
- [x] Capture a wireless pairing-mode baseline for the installed name-only probe:
  user reports rapid blinking, USB target absent, 45-second requested BLE scan
  finds no Zero 2/80EL/FF10 candidate. This does not prove absence of all BLE
  advertising. The subsequent visibility probe has now been flashed.

- [x] Locate and read Gamebrick and Ananke reference implementations.
- [x] Pin 8cryptdo and official Zero 2 v1.08 bytes; preserve catalog checksum discrepancy.
- [x] Decrypt both sections and reproduce the original package byte-for-byte.
- [x] Trace Yichip radio configuration loading and extract 70 configuration records.
- [x] Recover the 18-entry radio attribute table and identify the separate BTstack sample table.
- [x] Trace IPC submit capacity checks, synchronous copies and the unchecked HID wrapper.
- [x] Implement queued button snapshots, retries, baseline/reset/overflow semantics.
- [x] Host-test with sanitizers and a 100,000-step independent queue model; compile an ARM object.
- [x] Decode stock radio command `0x09` dispatch and identify its external ROM continuations.
- [x] Trace command-completion switch to acknowledgement bit 6 and zero-status check.
- [x] Reconstruct compressed startup data and trace dynamic FF10/FF13 registration arguments.
- [x] Verify stock startup reconstruction by offline ARM emulation.
- [x] Recover GPIO-to-mask mapping; emulate all 4,096 combinations through both reader and actual wrapper.
- [x] Correct earlier filter interpretation: constant-one predicate bypasses stock delay/resample branch.
- [x] Trace input timer registration and upstream congestion gates; emulate six gate and 36 timer cases.
- [x] Implement/test an unbound per-button debounce stage, including queued press/release integration.
- [x] Emulate 1,024 IPC cursor pairs; establish the need to reserve one byte against exact-fill ambiguity.
- [x] Audit initial memory constraints: eight static pools, boot markers, image tail,
  main/dispatcher stack frames and external ARM ROM calls. Emulate all 26 pool blocks.
- [x] Record compiler stack-frame estimates for both unbound components.
- [x] Trace the vendor updater's PID `0x9018` header-selection path; verify
  comparison/advance instructions in isolation against both package headers.
- [x] Trace and emulate the application's separate BLE state, vendor-write
  handle filter, watchdog registration/cancellation and restart guards.
- [x] Identify startup OTP/chip-ID ROM call names from the public YC3121 header.
- [x] Compare pinned YC3121 printer images; emulate D110's dynamic-handle payload
  builder and command `0x09` acknowledgement wrapper with explicit IPC/time stubs.
- [ ] Establish package section/hardware variant selection; do not assume both sections belong to one unit.
  Connected runtime device identifies as `2dc8:9018`; this is the PID selecting
  section 1 in the traced updater path. USB revision `0x0200` also matches the
  Yichip descriptor, unlike section 0's `0x0001`. User PCB photos show
  `YC3121-L`; the GD32 hardware path is still unknown. The
  bootloader also reports product code `0x9018`, and the installed application
  prefix through `0x11c03` matches the pinned Yichip section byte-for-byte.
- [x] Identify `2dc8:3208` bootloader; verify vendor packet construction and
  establish CRC-checked command-5 readback and command-8 product identification.
- [x] Back up the known application extent and ARM ROM API window; independently
  reread both. Preserve the nonzero live 508-byte tail instead of reusing it.
- [x] Capture ARM ROM through `0x7f9f` and emulate the startup OTP calls with
  actual delay loops; bound destination writes and isolated stack usage.
- [x] Independently reread the expanded ARM ROM prefix: all 32,672 bytes match.
  The controller remained in update mode after this bounded verification.
  The earlier read at `0x7fa0`
  timed out and USB returned to normal mode; do not assume the cause or claim a
  full dump. No reset/write command was sent.
- [x] Recover and emulate the public vendor debug utility's code-memory selector
  sequence in 40 offline cases; retain its different-chip/transport limitations.
- [x] Test bootloader reads at radio ID, clock control and RAM base. All-ones
  peripheral responses do not establish register access; no selector writes made.
- [x] Execute stock SysTick setup in 176 synthetic cases and its interrupt chain
  in three cases. Establish five-unit rounding, reload underflow below five,
  counter-reset behavior and the fixed-ten accumulator.
- [ ] Locate the separate radio ROM mapping using the now-working readback path;
  ARM ROM at `[0, 0x7fa0)` is available, not the radio ROM continuations.
  The stock loader establishes patch programming through `BT_UCODE_DATA`, not
  a ROM read mode. Reading the ROM-referenced flash boot entry `0x01000200`
  returned status 1; this does not establish the rejection's cause.
  The new vendor utility gives a candidate indirect read sequence, but needs
  validated register access and matching stop/resume semantics before live use.
- [ ] Obtain matching YC3121 radio ROM/SDK evidence for the `0x4eda` command continuation,
  `0x4f01` notification path and `0x7dc1` guard. These are outside the update image.
- [ ] Finish proving command `0x09` payload format/handle selection and FIFO acceptance.
  LE16 attribute-handle prefix is supported by related sources, stock handle checks
  and same-family D110 sender emulation, but the actual Zero 2 ROM payload reader
  remains unavailable. Printer size/timeout limits are not Zero 2 bindings.
  The live notification probe now confirms a dynamic LE16 handle followed by
  one byte produces the matching FF13 notification. Backpressure, larger payloads,
  errors and acknowledgement lifecycle still need binding.
- [ ] Recover connection/CCC callbacks and ordering; distinguish IPC capacity from radio delivery readiness.
  The application uses `0x20682` for BLE state, not HID state `0x20182`.
  Integrate the stock BLE watchdog with the custom subscription lifecycle;
  arbitrary CCC writes do not satisfy its existing vendor-handle filter.
- [ ] Select a regularly scheduled GPIO polling hook before all congestion/mode gates;
  establish clock units, sleep/resume behavior and physical button labels.
  Preserve existing report/remapping behavior; validate the proposed 8 ms debounce window.
  Do not configure the stock shared timer with argument one: it underflows LOAD.
  Nominal startup ticks are 10 ms; dynamic scale changes and sleep remain to be bound.
- [ ] Choose custom advertised service and characteristic IDs based on the actual radio table format.
- [ ] Bind the stream with proven RAM ownership, initialization, stack headroom and execution placement;
  serialize IPC producers, reserve one byte, and distinguish insertion from radio acknowledgement.
  Current memory inventory approves no location: include external ARM ROM behavior
  and interrupt nesting in the ownership/stack audit, not only visible Thumb code.
- [ ] Audit trampolines and incoming branches, startup copies, radio wake, lifecycle serialization and checksums.
- [ ] Build a complete version-pinned experimental package and independently unpack/review it.

Installation/boot and four one-byte GATT notification echoes are now verified.
Button delivery, press/release mapping, idle/wake and iPhone background/locked
delivery remain untested; bounded reconnect/subscription cycling succeeded with the BLE
probe. `scripts/flash.py` admits exact stock, name-probe, BLE-visibility and
notification-probe packages. The notification probe is now flashed and verified;
the separate `buttons-probe` is now flashed, with baseline delivery verified.
All 12 physical transitions and A+B have now been observed; the bounded battery button/idle test also passed. The original C components remain unbound.
