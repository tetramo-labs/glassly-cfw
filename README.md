# MemoMind One firmware investigation

Revision 13 draws default text at 4/5 of the resource font. The glasses' only
Latin face is a 34 px line with its baseline 7 px up, so inline text overflowed
the 24–27 px rows the phone lays out for the Even G2's 20 px font and lost its
descenders; at 4/5 it is a 27 px line with a 22 px baseline, the G2 builtin
font's own metrics. The text adapter scales glyph boxes, offsets, advances and
the baseline and draws each output pixel as the mean of a 2×2 sample of the
glyph box (`native_text.c`; control shifts stay in panel pixels, the cursor
keeps 1/5 px so a line does not drift). The wire protocol is unchanged; the
runtime is 94,288 bytes. Built and bundled, not flashed. See the
[V13 checkpoint](analysis/text-scale-20261105/checkpoint.json).

Revision 12 renders only what changed: a SHOW or animation tick clears and
redraws the union of the boxes of the objects that changed, arrived, left or
moved in the paint order, instead of the whole canvas. Cached-font strings are
bounded from their glyph headers, resident glyphs are drawn without a second
validation pass, cursor reads inside the window skip the per-read checks and the
rollback snapshot is copied by words. On the phone's captured dashboard
commands the clock tick runs 7% of the revision 11 instructions, a tween frame
11% and a cold open 71%. The linker now relaxes calls (`--relax`, no gp use),
so the runtime is 94,000 bytes with 4,304 to spare. The same scene core is G2
CFW revision 51. See the [V12 checkpoint](analysis/renderer-20261105/checkpoint.json).

Revision 11 fixes first-run boot selecting the stock welcome/language app after
a factory reset. Both setup states now select the minimal display owner. The
image is bundled in Glassly; physical acceptance is pending. See the
[V11 checkpoint](analysis/first-run-owner-20261103/checkpoint.json).

Revision 10 adds a bounded finish/drain/release sequence for sensor capture,
preserving the unread tail during normal recording completion. Swift and Android
clients use generation-checked cleanup; V11 retains that protocol.
See the [V10 checkpoint](analysis/sensor-drain-20261103/checkpoint.json) and
[sensor protocol](runtime/graphics/SENSORS.md). V10 is flashed and boot verified:
all 2,247,403 image bytes matched, and a fresh connection confirmed the exact
installed app header and live `GLASSLYCFW/10` response. See the
[flash evidence](analysis/sensor-drain-20261103-flash-01/checkpoint.json) and
[later boot confirmation](analysis/sensor-drain-20261103-flash-01/boot-confirmation.json).
The 15-second hardware capture saved 15 light records and completed finish/drain/
release with no reported gaps or overwrites. No IMU samples arrived; active sensor
power and compass parity remain open. See the
[sensor check](analysis/sensor-drain-20261103-flash-01/sensor-verification.json).

The connected H001Y glasses successfully updated from **1.0.2.151 to
1.0.3.127** on 2026-10-30. The completion screen and fresh device-version
response confirm the result. The downloaded OTA, APKs, Bluetooth HCI recording,
network capture and app logs are retained locally.

The target is full `~/dev/g2flash` CFW feature and capacity parity. As of
2026-11-01, preserving MemoMind stock UI, app-protocol compatibility or plugin
behavior is explicitly not required. The proven hardware drivers and OTA path
remain development dependencies while useful. The pinned G2 assertion corpus and its feature semantics remain requirements.
Bundled reference names are normalized to Glassly with original hashes retained.

## Latest firmware

Revision5 was boot verified before the revision6 update. It completes high-bit
dispatch for cached graphics, shapes and cache operations.

Revision6 is flashed and boot verified. It releases the
6,144-byte record reply scratch buffer between commands and makes empty shape
commands stop animation while preserving pixels. The full 2,248,759-byte transfer
was independently verified with no retries. Compressed records up to 65,535 bytes,
dictionary reuse, high-bit shapes/STATE, cleanup, notification control and display
position/depth readback passed after reboot. Physical display confirmation and a
matched record-session RAM measurement remain pending.
See the [revision5 checkpoint](analysis/command-flags-20261103/checkpoint.json)
and [revision6 checkpoint](analysis/record-memory-20261103/checkpoint.json).

Revision7 adds leased native Opus microphone control, verified shutdown status,
disconnect/expiry gating and whole-session cleanup. The Swift tool and Glassly
iOS/Android use the new control path; display clear preserves microphone capture.
Revision7 was not flashed; its microphone changes are included in revision8.
See the [microphone contract](runtime/graphics/MICROPHONE.md) and
[revision7 checkpoint](analysis/microphone-owner-20261103/checkpoint.json).

Revision8 adds leased passive IMU register and normalized light snapshots,
with generation tokens, sequence numbers and completion timestamps. The runtime
uses94,608 bytes of the existing96KiB region and48 reserved registry bytes.
Swift and Android clients expose the native diagnostic interface; the Glassly
bundle and engine admission required revision8. It was not flashed.
Native sensor power control, physical-unit calibration and compass remain
unfinished. See the [sensor contract](runtime/graphics/SENSORS.md) and
[revision8 checkpoint](analysis/sensor-capture-20261103/checkpoint.json).

Revision9 adds a32-record acknowledged sensor FIFO, overwrite counters,
generation-checked batch reads and watchdog buffer reclamation. The runtime is
96,208 bytes; active capture uses784 heap bytes plus the existing48-byte registry
slot. Swift/Android clients and the Mac recorder implement the batch protocol.
Glassly bundled revision9 and required it for native admission. It has not been
flashed separately; its changes are included in revision10. See the
[revision9 checkpoint](analysis/sensor-buffer-20261103/checkpoint.json).

## Compressed record transport

Revision4 adds a native GM record carrier with persistent zlib dictionaries,
CRC16 and correlated ACK/NACK/data replies. It accepts up to65,535 encoded and
decoded bytes within an explicit heap budget. The runtime fits the existing
96KiB allocation. The Swift sender and required offline suites include this
path; hardware acceptance is recorded separately in the
[revision4 checkpoint](analysis/record-transport-20261103/checkpoint.json).
See the [wire contract](runtime/graphics/RECORD_TRANSPORT.md) and
[offline evidence](analysis/record-transport-20261103/offline-verification.json).

## Minimal owner and flash capacity

The `GLASSLYCFW/1` profile replaces the dashboard launcher with a minimal display
owner, connects a 256 KiB COW asset store through a native I/O worker, and handles
65,535-byte raw commands through bounded CRC-checked chunks. Native Swift sending
is included. The first installed build exposed a queue ABI defect at RESET,
before any asset writes. The corrected 2,234,179-byte update is transferred and boot verified. Hardware
accepted a 65,535-byte raw command and the full 262,144-byte asset upload, with
4 KiB independent readback, a flash-backed glyph draw and successful cleanup.
The user confirmed the text and flash-backed checkerboard in a repeat display
check; [visual confirmation](analysis/minimal-owner-display-repeat-20261102/visual-confirmation.json)
is recorded separately from protocol evidence. See the
[current result](analysis/minimal-owner-queue-fix-20261102/hardware-result.json)
and [ownership/wire contracts](runtime/graphics/MINIMAL_OWNER.md).

The wake/display ownership update is transferred and boot verified. Hardware
checks confirm frame retention beyond30 seconds,90-second lease expiry and
cleanup. Five double-press CLAIM/READY handshakes passed, and the user confirmed
the text and redraw behavior.
Single/long/release button capture and native microphone streaming are verified,
including the user's listening confirmation. See the
[wake checkpoint](analysis/wake-display-20261102/wake-flash-checkpoint.json),
[lease and wake checks](analysis/wake-background-20261102/ownership-verification.json) and
[audio confirmation](analysis/wake-display-20261102/microphone-confirmation.json).
The reported lit background on wake is unintended. A follow-up restores the
stock shared-screen background initialization and is
[boot verified](analysis/wake-background-20261102/boot-verification.json);
text and the black background are now [visually confirmed on revision 3](analysis/ota-pacing-20261103/visual-confirmation.json).
Mode5 sound/tone commands and volume gating are excluded.

The `GLASSLYCFW/3` image added the native ANCS relay and display position/depth
settings. Its entire OTA and post-reboot app header are verified; hardware relay
enable/poll/disable and settings change/readback/restoration passed. Actual iOS
notification delivery/actions and physical position/depth confirmation remain
pending. See the [revision 3 checkpoint](analysis/ota-pacing-20261103/checkpoint.json).

## Established results

- The observed updater uses **Bluetooth Classic RFCOMM**, control UUID
  `00007033-0000-1000-8000-00805f9b34fb` and OTA UUID `00007034-...`.
  This update did not use BLE GATT.
- All **3,457 OTA chunks across 494 requested blocks** have valid CRC32 and
  match the downloaded image. Every requested block precedes its matching ACK.
- Bulk transfer covers `[162757, 2185697)`; the complete 2,185,697-byte download
  is also retained. Native analysis identifies device-side resume logic.
- Partition metadata and six compressed components account for every OTA byte.
  All LZMA boundaries, component lengths and observed CRC32 layers validate.
- Application/system code is RV32, with a likely Xtensa/HiFi audio image.
  G2's Thumb patches and absolute addresses cannot be reused.
- Unchanged offline repack is byte-identical. Same-length body replacements
  recalculate all known integrity fields.
- The independent stock transaction driver reproduces all 3,464 outgoing
  recorded packets in order, consuming all 501 incoming records. This replay
  does not establish successful independent flashing on hardware.
- Offline patch manifests pin the source, component bodies, expected original
  bytes and final image hash; overlapping and unexpected edits are rejected.
- An independent Android/Python RFCOMM client has passed live heartbeat and
  device-info queries. A native capability query also confirmed ABI0x0100,
  package format2 and a600×350/30Hz GRAY4 display on the actual glasses.
- The independent stock eligibility handshake also passed on1.0.3.127. It
  stopped before OTA entry with zero blocks sent. Subsequent independent text
  and runtime transfers both completed on hardware, as described below. See
  [driver verification](analysis/stock-driver.md) for the earlier stock check.

The first same-length text patch was transferred successfully on2026-10-31:
**Bluetooth disconnected → Glassly firmware ready**. The device accepted the
update, acknowledged reboot and reconnected; the user confirmed seeing the
patched text on the glasses. See [first text patch](analysis/first-text-patch.md). Boot security,
recovery and executable patch sites remain under investigation.
The OTA is not a complete physical flash dump. Initial bonding preceded capture;
reconnect/service discovery, update and post-reboot traffic are recorded. Normal
app interactions include marked Eco Mode on/off, restored to its original off
setting.

The appended RISC-V scene runtime has been installed and exercised on the glasses. It integrates
retained scenes, cache/assets, vector animation and resource-backed native text
with the native display worker. Hardware accepted the scene lifecycle/animation
checks, all24 vector-fixture commands and both302-command video sequences. Stock
capabilities and heartbeat remain unchanged; cleanup returned free memory near
baseline. Every byte of the2,218,446-byte OTA was reconstructed from the HCI
capture. See [scene hardware evidence](analysis/scene-hardware-verification.json).
Visual acceptance of those earlier retained-scene/video tests remains unconfirmed.
Later raster, copy, bundle and immediate-text patterns have separate user confirmations.
Video trace spans of124/150 seconds do not establish
30fps performance. That earlier build used a 64 KiB store and 8192-byte messages.

The [G2 test port](tests/g2_compat/README.md) preserves the pinned upstream corpus
and maps original assertions to current MemoMind coverage. All46 unique C host
scenarios now have portable core coverage, with746 original assertion sites
preserved across all seven host suites. This includes scene/cache/assets,
notification relay, keyboard, record transport and upstream protocol policies.
The latest clean regression passes 144 required offline stages, including 235
Python tests and 155 Swift tests, with no source drift or missing mapped stages.
See the [regression summary](analysis/sensor-drain-20261103/regression-verification.json).
The required sensor ABI stage passes604 actual-code cases with
mocked hardware/RTOS boundaries. It establishes ALS normalization and shared
power behavior, plus IMU acquisition, axis reduction and shutdown boundaries;
Revision8 builds on this evidence with passive capture; it does not claim
active power control or calibrated G2 sensor parity.
See [sensor evidence](analysis/sensor-abi-20261103/NOTES.md).
Unchanged G2 reference checks and native-layout mocks remain separately labeled;
18 required suite/integration entries remain incomplete. Bluetooth keyboard/HOGP,
ring battery, gestures, mode5 sound/tone commands and volume gating are out of
scope. Remaining work includes active/calibrated native sensors, broader microphone profiles and hardware ownership acceptance, BLE/wear
policies, physical notification acceptance, performance, broader font coverage
and complete app/pairing capture.

Stock dashboard reclamation now has a concrete offline candidate. Six card-renderer
entries return their existing unavailable result, leaving **2,746 bytes in six RX
regions** for separately linked CFW code. The actual stock dispatcher passed54
mocked-native RV32 cases across all9 card types, plus18 direct gate checks. The
14,168-byte launcher band contains shared navigation/calibration helpers, so the
entire band is not yet reusable. The candidate does not establish heap savings
and is not installed. See the [reclaim checkpoint](analysis/dashboard-islands-20261102/report.json).

The earlier `dashboard-ram-002` release suppresses stock card/status/DND-header
construction from cold boot. Its six gates avoid at least 1,440 bytes of requested
state/base allocations, plus variable styles/resources. The entire 2,230,671-byte
OTA and the running application's header are verified. After a 90-second display
test and cleanup, free RAM settled at **353,636–353,808 bytes**, compared with
333,980–334,108 before the update: an observed median gain of **19,718 bytes**.
The first reconnect sample was 340,684 bytes; all samples are retained. The earlier
baseline was not freshly rebooted, so cache/reboot differences prevent attributing
the entire gain to the gates. Display commands, lease renewal and cleanup passed;
physical confirmation of “RAM” on black remains pending. The candidate passed
230 native RV32 calls, 2 constructor tests and 106 Swift tests; the full aggregate
was not rerun for this change. See the
[RAM hardware result](analysis/dashboard-ram-native-20261102/hardware-result.json).

The earlier `reset-undo-trim-001` release was installed and boot verified. A successful
standalone RESET now releases undo scratch while retaining scene metadata, asset
storage, vector workspace and pixels. In matched on-device measurements, RESET
increased free RAM by **46,392 bytes** (median); the following PUT consumed
about 46,382 bytes again. The previous release changed by only 56 bytes.
This improves idle memory after RESET, without reducing peak transaction RAM.
Bundles retain scratch; failed native reacquisition rejects CAPACITY before cache
mutation. The default portable G2 behavior and original assertions remain unchanged.
The runtime is 60,256 bytes within the existing 64 KiB code allocation. All 235
Python and 107 Swift tests passed, alongside native and sanitizer scene regressions.
See the [RESET scratch hardware result](analysis/reset-undo-trim-20261102/hardware-result.json).

A separate reviewed **96 KiB RX profile** permits32,848 bytes of growth beyond the
previous 65,456-byte runtime within the existing app allocation. The new
71,584-byte minimal-owner runtime is now boot verified using this profile.
See the [profile review](analysis/rx-profile-review-20261102/report.json).
Native Swift compass/ALS command encoders now match5,404 unchanged upstream
reference checks, and all105 Swift tests pass. Their firmware adapters remain
pending: native ALS and raw IMU paths are located, while a compass source remains
unresolved. These sensors stay in scope.

The current installed build also includes an optional passive input observer.
It retains cooked button/gesture events in a32-record buffer until
the host acknowledges saved records, reports overflow and preserves stock
dispatch. The earlier49,248-byte input build passes7,955 gate cases and1,710 actual RV32
handler calls with mocked firmware APIs. Its2,221,167-byte OTA was independently
reconstructed from captured bytes. Hardware subscription, nonce/ACK rejection,
scene coexistence, stop and lease checks passed with stock capabilities intact.
That earlier180-second capture observed no physical events. A later capture
confirmed single press, long press and release with no reported drops; see
[button verification](analysis/wake-display-20261102/button-verification.json).
Gesture recognition is outside the current scope;
this cooked-event observer does not supply raw IMU or compass samples.
The logger saves each page before acknowledging it; the phone was
restored to MemoMind. See [input hardware evidence](analysis/input-hardware-verification.json)
and [input observer](runtime/graphics/INPUT.md).

The earlier 50,944-byte build extended the bounded read-only flash command to
back up the proposed external 1 MiB region. Its complete 2,222,168-byte OTA
matches independent HCI reconstruction. All 4,354 native reads succeeded; the
full app header matches the candidate and the plugin directory is unchanged.
The entire proposed region and directory contain erased bytes. This establishes
contents, not a reservation or bad-sector availability. The phone is restored
to MemoMind. See [external-reader hardware evidence](analysis/external-read-hardware-verification.json).
The earlier [metadata acquisition](analysis/flash-read-hardware-verification.json)
also acquired the complete 60,856-byte boot image with a verified body CRC.

The earlier 54,064-byte storage diagnostic runtime was boot verified.
Its complete 2,223,868-byte OTA matches independent HCI reconstruction. The native
KV6009 getter reported an absent record (status7), which the native loader defines
as a zero bad-sector bitmap. This is effective-map evidence, not proof that every
sector is physically healthy. Two passive topology queries were stable; the
plugin directory remained erased and no CUS8 context was present. See
[storage diagnostic hardware evidence](analysis/storage-diag-hardware-verification.json).

The portable [transactional flash store](runtime/portable/FLASH_STORE.md) supports
256 KiB of logical assets in a 1 MiB physical region. The portable scene backend
now uses it for images, fonts, text and paths, including exact 65,535-byte messages.
It passes the unchanged vector/GIF/SVG fixtures, rollback and read-failure tests,
plus ownership/alias checks. The core's 4,224 injected callback failures remain a
separate required stage. This backend is not bound into the installed native
runtime: its limits remain 64 KiB of RAM assets and 8,192-byte messages.

The new storage direction is exclusive CFW use of the full 3 MiB native plugin
region, device1 `[0x500000,0x800000)`, rather than retaining a smaller stock cache.
The boot-verified **54,016-byte exclusive-store reader** disables the six
identified mount/read/program/erase/reset/badmap-save entry points and exposes the
full region for bounded reads. Its 2,223,753-byte OTA was independently reconstructed
from captured bytes, and its complete 256-byte app header was verified after boot.
The full 3 MiB backup is complete: all 12,288 chunk hashes verify and every byte is
`0xff`. See [hardware evidence](analysis/exclusive-store-hardware-verification.json)
and [backup verification](analysis/exclusive-store-backup-verification.json).

A fresh native Mac backup after the user factory reset acquired all 3 MiB again;
every chunk and raw request/reply correlation verified, and the bytes match the
earlier backup. See [current backup verification](analysis/native-mac-backup-20261101/verification.json).

The reader has no CFW flash writer. The separate fixed-sector canary and native
flash adapter pass offline failure, heap/worker and RV32 tests. Its complete
2,226,788-byte OTA has now been transferred by the Swift flasher and independently
reconstructed. After the glasses were woken, the exact canary header/profile and storage
preconditions were verified. One fixed erase/program/verify/erase-restore test
passed; independent readback confirmed the full 4 KiB target was erased again
and its 4 KiB neighbor was unchanged. The canary image is now installed. See
[canary hardware evidence](analysis/native-mac-canary-20261101/report.json).
Global exclusive ownership, native scene storage and performance remain in the
[storage plan](analysis/storage-integration-plan.json).

A [native Swift flasher](swift/MemoMindKit/README.md) now builds directly on macOS,
using the Mac's IOBluetooth RFCOMM services. Its shared protocol core passes an iOS
compile check and can later be integrated into Glassly. The captured stock replay
matches all 3,464 outgoing packets, and 89 Swift tests pass. Mac pairing, device
identity and a complete native OTA transfer now pass: 543 blocks / 3,800 chunks,
with the full image independently reconstructed from the application trace. The
glasses acknowledged reboot. After waking them, the running reader profile and
full application header matched the image, and the user confirmed the patched text.
See [transfer evidence](analysis/native-mac-hardware-20261101/report.json) and
[boot/storage verification](analysis/native-mac-preflight-20261101/verification.json).
Firmware construction still uses the offline Python tools.

The installed command-parity firmware supports mode6 RLE frames, mode3 rectangle
deltas, mode9 overlap copy, mode8 bundles, and mode15 built-in text. Native Swift
encoders generate these commands directly on the Mac. The text update and boot
header are verified; the user confirmed both native TEXT 15 / SWIFT groups.
Maximum 255-byte text, highbit and bundled text, malformed rejection and explicit
clear passed live checks. All 105 required offline stages pass (223 Python and 89
Swift tests). MemoMind resource fonts differ from G2; remaining command adapters,
native capacities and full suite porting are incomplete. Keyboard/HOGP is excluded.
See [command map](tests/g2_compat/COMMAND_PARITY.md) and
[text hardware evidence](analysis/text-native-20261102/report.json).

## Evidence and tools

| Artifact | Purpose |
|---|---|
| [Protocol](analysis/protocol.md) | SDP, framing, handshake, requests and acknowledgments |
| [Firmware format](analysis/firmware-format.md) | Container, partition map, ISA and checksums |
| [G2 port assessment](analysis/g2flash-port-assessment.md) | Reusable architecture and hardware-specific assumptions |
| [Native plugin assessment](analysis/native-plugin-port.md) | Official C SDK and device-access limits |
| [REA workflow](analysis/rea-workflow.md) | Executed analysis and provider constraints |
| [Native findings](analysis/ghidra/findings.md) | Function-level updater, resume, integrity and plugin evidence |
| [Independent bridge](android_bridge/README.md) | Built APK, Python transport and verified read-only hardware probe |
| [Decoder](scripts/decode_memomind.py) | Recover and verify recorded OTA data |
| [Image tool](scripts/memomind_ota.py) | Inspect, extract and repack offline |
| [Patch construction](analysis/patch-construction.md) | Exact byte edits and reproducible image validation |
| [Stock transaction driver](scripts/memomind_flasher.py) | Recorded-session replay and explicitly selected live modes |
| [Native Swift flasher](swift/MemoMindKit/README.md) | Direct Mac RFCOMM, reusable Swift protocol core, release validation and capture replay |
| [App behavior](analysis/app-actions.md) | Exercised settings, queries and connection coverage |
| [HCI validator](scripts/inspect_btsnoop.py) | Record integrity, truncation and capture identity |
| [Regression runner](tests/run_tests.py) | Firmware/transport, G2 port, geometry/vector/scenes, lifecycle and actual RV32 execution suites |
| [G2 coverage inventory](tests/g2_compat/inventory.json) | Exact upstream hashes, assertions, implemented and outstanding test coverage |

Raw artifacts are ignored by Git and may contain private device/app data:

- `captures/firmware/ota-1.0.3.127-jhv3_release.bin`
- `captures/ota-complete.btsnoop`: update plus reboot/reconnect, 10,367 records.
- `captures/general-session.btsnoop`: additional normal-app interactions.
- `captures/session-20261030-2019/`: APKs, timestamped actions, deduplicated file
  snapshots, app logcat, screen evidence and SHA-256 manifest.
- `captures/phone-20261030-2011.tar`: redundant phone-side acquisition.
- `captures/phone-final/`: selected logs and network capture from that archive.
- `analysis/protocol/ota-final/summary.json`: actual chunk/range/ACK proof.
- `analysis/evidence/`: REA package evidence and other capture checks.

Stock SHA-256:
`08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`.
Completed-OTA HCI SHA-256:
`cee5e838e3c69a9dd0a5ccbfb8e6165bafc1e730891fae6e12581e6ef73ebf18`.

## Reproduce offline checks

Run all required offline suites into a new evidence directory:

```sh
python3 tests/run_tests.py --output /tmp/memomind-regression
```

This requires the pinned local RISC-V toolchain, Unicorn environment, firmware
artifacts and Bun dependency tree documented in the individual test directories.
Missing required dependencies are failures. Add `--require-complete` to also
fail with exit2 while the full upstream test port remains incomplete. Exit0
without that option means all current offline suites passed, not full CFW or
hardware parity. No tests in this runner operate the phone or glasses.

Individual capture and image checks:

```sh
python3 scripts/inspect_btsnoop.py captures/ota-complete.btsnoop
python3 scripts/memomind_ota.py inspect captures/firmware/ota-1.0.3.127-jhv3_release.bin
python3 scripts/decode_memomind.py captures/ota-complete.btsnoop \
  captures/firmware/ota-1.0.3.127-jhv3_release.bin /tmp/memomind-new-verification
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

Decoder output directories must be new. These offline tests cover captured-image
roundtrips and corruption rejection; the separate hardware reports above establish
acceptance of the specific tested custom images. `scripts/rea-local.sh`
uses verified task-local Node/JADX and `~/dev/rea`. Direct Ghidra raw-image results
are labeled separately because REA does not support this raw RISC-V import.

Earlier diagnostics release: [hardware checkpoint](analysis/diagnostics-native-20261102/hardware-awaiting-visual.json). Its text checks are recorded in [mode15 hardware evidence](analysis/text-native-20261102/report.json).

The diagnostics/cleanup candidate adds mode7 frame tracking and a separate
overlay, plus mode11 cleanup of implemented graphics/input resources. Its
65,456-byte runtime fits the existing64KiB limit and passes focused host/RV32
tests. The exact OTA is admitted to the Swift catalog, transferred and boot verified.
Offline regression and live diagnostics/cleanup checks passed. The five-minute
display hold ended and cleanup was acknowledged; visual confirmation is pending. See [candidate evidence](analysis/diagnostic-commands-001/report.json).
Current-screen diagnostic lifetime and limited native counters remain explicit
differences from G2; sensor adapters and complete-controller cleanup are unfinished.

Hardware scope (2026-11-02): single-button input, compass and raw IMU data remain
required. Ring battery and gesture-specific behavior (head-up, swipes, ring-touch)
are excluded, along with Bluetooth keyboard/HOGP. Ambient-light sensing remains
in scope. The updated inventory has19 incomplete required suite/integration entries.

## Repository and licensing

Source is maintained in the private
[tetramo-labs/glassly-memomind-one-cfw](https://github.com/tetramo-labs/glassly-memomind-one-cfw)
repository. Each flash is followed by a commit and push containing its source,
tests and recorded outcome. The first Git checkpoint includes the boot-verified
RESET scratch release and its measured RAM result.

Original project code is MIT; upstream-derived components
are covered by the root MIT LICENSE, relicensed with permission of the upstream authors. CFW version strings use
`GLASSLYCFW/N`, with a numeric revision.

Raw captures, firmware/APKs, extracted images, toolchains and generated builds
remain local. Selected analysis notes, helpers and verification reports are
tracked. Fresh clones need the referenced local fixtures and toolchain before
running hardware-dependent construction/replay checks; missing fixtures are
reported as failures rather than silently counted as passes.
