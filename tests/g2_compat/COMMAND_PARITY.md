# G2 command parity map

Source snapshot: G2 commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`, pinned by
[UPSTREAM.json](UPSTREAM.json). Memo source review date:2026-11-01. This maps the
custom image dispatcher and custom settings extensions, plus the head-up settings
used by the pinned test harness. It does not claim to inventory every stock G2
application-service command. Bluetooth keyboard/HOGP, ring battery, mode5 sound/tone commands, volume gating and gesture-specific behavior are excluded
by the user's updated scope. Single-button input, compass and raw IMU data remain
required; gesture exclusion does not exclude sensor data. No device was operated for this review.

“Implemented” below means the stated code path exists; hardware visibility,
performance, capacity and exact native behavior remain separate acceptance gates.
There is no blanket “all command parity” claim. G2 field numbers belong to its
protobuf settings/control envelope, not Memo GM service or command numbers.

## Image commands

Original dispatcher: [zlib_glue.c](upstream/patches/zlib_glue.c),
`image_dispatch` lines406–741. Memo admission:
[graphics.c](../../runtime/graphics/graphics.c), `valid_message`; execution:
[scene_session.c](../../runtime/graphics/scene_session.c),
`mm_scene_session_dispatch`. Memo scene commands use GM service`0x0f`,
command`0x7d`, one BYTES TLV; G2's original wire/ACK envelope is not installed.

| G2 mode | Contract | Memo implementation / missing boundary |
|---|---|---|
|3|RLE bounding-box delta; scaled coordinates, diagnostic frame ID; optional per-lens boxes|Implemented behind `--raster-commands`: bounded window decode, first/left box for the high-bit variant, validation before scene takeover. Frame ID is accepted; the separate `--diagnostic-commands` candidate adds original16-bit history tracking, with offline validation only so far. Native Mac smoke acknowledged; user confirmed RLE letters and checkerboard visible. Pixel-perfect display comparison and performance remain unverified.|
|5|Sound kinds0 preset,1 note,2 stop,3 frequency/duty/duration,4 owned tone sequence|**Excluded:** mode5 sound/tone commands are out of scope. Historical reference tests remain unchanged; microphone capture/streaming remain separate requirements.|
|6|Full packed GRAY4 RLE keyframe into persistent shadow|Implemented behind `--raster-commands`, using the existing owned raster without a second canvas. Full input is validated before takeover/draw. Native Mac smoke acknowledged; user confirmed RLE letters and checkerboard visible. Pixel-perfect display comparison and performance remain unverified.|
|7|Sub0 reset diagnostics/frame history;1 hide diagnostic overlay;2 show|Implemented in the offline `--diagnostic-commands` candidate: original16-bit FID ring and deferred visibility, separate child overlay and strict20-byte native snapshot. Compact font, current-screen lifetime and limited native failure counters differ from G2. Hardware acceptance pending.|
|8|Counted length-prefixed nonnested bundle, deferred sub-presents and one final presentation|Implemented behind `--command-bundles`: sequential supported children, one final explicit present, final cache scratch, bounded ordered settled collection. Mode15 text children are supported by `--text-commands`. Late errors preserve earlier changes; shared pixels can be read by incidental LVGL refresh. Native Swift smoke and visible B8/checkerboard confirmed.|
|9|Overlapping rectangle copy, fullu16 source/destination rectangles, correct odd-nibble preservation; optional per-lens rects|Implemented behind `--rect-copy`: bounds-checked overlapping copy, odd-nibble preservation, first/left pair. Native Swift smoke acknowledged and user confirmed second copied pattern; exact physical pixel comparison/performance remain unverified.|
|10|Compass stop/start/config; interval50–2000ms, min-change value; heading/sample metadata notifications|Missing command/native sampling ownership. Portable heading metadata/policy exists in `upstream.c`; no sensor binding.|
|11|Whole custom-session cleanup; reserved trailing bytes accepted|Partial: the offline diagnostics candidate accepts11/8b and trailing bytes, releases implemented graphics/input, hides overlay and retains current-screen diagnostic history. Explicit-cleanup epoch retention is best effort on allocation failure. The notification candidate also clears its relay lease/queue. Future sensor controllers and canary workers are not cleaned by this path. Hardware acceptance pending.|
|15|Immediate built-in UTF8 text; signed placement, options, control-byte x offsets, up to255 text bytes|Implemented behind `--text-commands`: exact255-byte-capable envelope, signed placement, UTF8/control validation, highbit and bundle dispatch with owned scratch. Native text visibly confirmed. Resource fonts/metrics and missing-glyph rejection differ from G2; retained shape text remains128 bytes.|
|16|ALS query0/start1/stop2; interval100–5000ms, min delta, heartbeat, lease option; field105 reports|Missing command, native sample/brightness metadata and ownership adapter.|
|17|Ring battery query `[17,0]`; field106 `RB` status with connected/valid/charging bits|**Excluded:** no ring battery hardware. Historical portable encoding/tests remain reference only; no native binding required.|
|19|Immediate cached image|Implemented in scene core/native scene session, subject to listed limits.|
|20|Immediate cached-font text|Implemented in scene core/native scene session; requires uploaded font asset.|
|36|Immediate shapes1–18 in scene build, including images/text/paths|Implemented; geometry-only build supports1–13. Native empty `[36,0]` renews lease rather than original raster takeover.|
|37|PUT object/asset chunks, replacements/reassertion, transaction|Implemented in `scene_cache.inc::cfw_cache_put`.|
|38|SHOW ordering, visibility/movement/glide/tween/freeze/finish/rotation|Implemented in portable scene/native scene session.|
|39|HIDE/optional present/tag; retains cache|Implemented in portable scene/native scene session.|
|40|STATE revision/page; unchanged/delta/snapshot replies|Implemented core. Native reply translation/size differs from G2.|
|41|CONTROL reset/drop inactive/animation period10–250ms|Implemented in portable scene/native scene session.|

Detailed byte contracts, native discrepancies and regression requirements are in
[the display review](../../analysis/command-parity-review/display-scene.md).
G2 masks the mode high bit. The optional mode3/6 implementation supports it for
those modes and advertises `rasterLens:"first-left"`: mode3 uses the first box,
while mode6 ignores the flag. Other modes still admit exact bytes. This is a
single-display mapping, not dual-lens support.
The minimal-owner profile implements a 256 KiB logical flash asset store and
65,535-byte raw commands through mode127 bounded chunks, with a 30-second lease.
Native GM packets remain bounded to8192 bytes; cache replies remain250 bytes
translated to JSON and the display is600×350. Native worker integration and its
queue ABI have separate host/RV32 tests. Hardware outcomes are recorded in
[the latest result](../../analysis/minimal-owner-queue-fix-20261102/hardware-result.json);
code presence and capability advertisement alone do not prove capacity.
The logical flash map is volatile across reboot/new scene. See
[the ownership and carrier contracts](../../runtime/graphics/MINIMAL_OWNER.md).

## Settings, control and asynchronous events

Source: [settings_ext.c](upstream/patches/settings_ext.c),
`glassly_scan_settings_control` and `settings_send_wrapper`. The generic
[portable upstream module](../../runtime/portable/upstream.c) parses fields and
composes responses; it is not registered as a native GM command adapter.

| G2 selector | Contract | Memo implementation / missing boundary |
|---|---|---|
|Settings READ; extension100|Firmware revision/capability response with bounded append/send behavior|Portable composition tested. Missing native response mapping and truthful revision/capability handshake. Native probe JSON is related but not wire equivalent.|
|Field101 `FC`v1 ops1–7|1 acquire/renew wake90s;2 release;3 claim5s;4 ready;5 acquire framebuffer90s;6 release;7 wear query|Ops1–6 implemented through GM`0f/79`, with query0, native wake guards and400ms fallback. Installed; hardware frame retention,90s expiry and cleanup pass. Five physical double-press CLAIM/READY cycles and visible redraws verified. Wear query7 is not implemented.|
|Field102 events1–5|Wake, tap, long, release, head-up wake|Native single/long/release capture verified at`0f/7c`. Ownership events1–4 implemented at`0f/79`; five physical double-press handshakes verified. Head-up, swipe and ring-touch gesture acceptance are excluded.|
|Field103 `MC`v1 ops1–4;104 status|Configure/query/stop/renew microphone; sample/codec/source/flags and stream ownership|Native RFCOMM2024 start/stream/stop, repeated capture and independent Opus decode verified; user confirmed recorded audio. G2-style leased configuration/status and whole-session cleanup integration remain missing.|
|Field126 `AN`v1 ops1–5;125 output|Enable/disable/query/action/renew notification relay; source/attribute/app/status records|Original nine scenarios retained. An opt-in native polling adapter now passes host/RV32 checks: pre-stock source/attribute copies, peer/UID validation, leased queue, actions serialized on the stock app task and mode11 cleanup. Candidate only: mobile polling/configuration and linked RV32 handler tests pass; native concurrency/full task-stack acceptance and physical ANCS/action tests remain pending. See `runtime/graphics/NOTIFICATIONS.md`. Android notifications are separate from true ANCS.|
|Field127 `BL`v1 ops0/1;128 status|Stock/fast BLE link profile; actual interval/latency/status|Portable policy exists, native BLE lifecycle binding missing. RFCOMM transport/OTA performance cannot stand in for BLE interval control.|
|Field130 keyboard control;131 keyboard output|Bluetooth HID/HOGP discovery, pairing, reports and keyboard lifecycle|**Excluded from required parity.** Historical portable/tests/ARM evidence remains optional. Mixed field-parser assertions remain required unchanged.|
|Field132 `VG`v1 ops1/2;133 status|Configure/query microphone volume gate|**Excluded:** volume gating is out of scope. Original algorithm and tests remain optional reference; microphone capture and streaming remain required.|
|Head-up switch and angle settings used by `head-up-test.ts`|Write/readback settings, then physical head-up events under display/wake ownership|**Excluded gesture behavior.** Existing native setter/readback analysis is retained as reference. Compass and raw IMU data remain required independently of head-up recognition.|

**Raw IMU data remains explicitly in scope.** A native sample/stream adapter,
metadata, ownership, start/stop and cleanup tests are still needed. The existing
shared native enable flag is not yet a safe independently leased sensor API.
No gesture recognition is required to expose the sensor data.
The reviewed native raw-sample record contains accelerometer, gyroscope,
temperature and calibrated pitch fields. Compass work still needs a verified
heading source and validity/accuracy metadata; pitch or gyro samples alone do
not establish compass heading. Both adapters need timestamped acquisition,
start/stop ownership, lease expiry and cleanup coverage before hardware parity
can be claimed.

Microphone control magic is defined by `mic_control.c`; payload/configuration
fields must be validated from that implementation before a native adapter.
The Swift CLI now captures cooked single-button events and the existing native
microphone service on `minimal-owner-flash-004`. Physical single/long/release
actions passed with zero reported observer drops. Two native Opus sessions
started and stopped; independent decoding passed and the user confirmed the
first recording. This establishes native capture, not G2's field103 lease,
configurable PCM/channel modes, or button takeover. See
[the checkpoint](../../analysis/wake-display-20261102/checkpoint.json).
[Head-up evidence](../../analysis/ghidra/input-settings/report.md) also maps native
light-up/down durations, sensitivity and nod/shake controls. The native IMU enable
function uses shared boolean ownership, not a per-client refcount; it cannot safely
be advertised as an independent leased raw-sensor API. Head-up angle equality does
not establish equal physical detection behavior.

The required record transport now has a native mode126 GM carrier, pinned
zlib inflater, persistent dictionaries, CRC/ACK/NACK handling, a 180 KiB heap
budget and a 30-second context lease. The Swift sender performs capability and
ACK checks without automatic retries. Original G2 scenarios, sanitizer tests
and actual linked RV32 display-queue tests pass. Revision4 hardware verification
is tracked separately in `analysis/record-transport-20261103`; offline results
do not establish boot or hardware timing. Mode127 remains the raw carrier.
See [native record protocol](../../runtime/graphics/RECORD_TRANSPORT.md).

## Next vertical command slice

Modes3/6/9/8/15 are installed and visibly confirmed. The mode7 diagnostics and
mode11 implemented-session cleanup candidate now passes focused host/RV32 tests;
hardware acceptance is pending. Its separate overlay leaves raster copying and
composition unaffected in those tests. See [offline evidence](../../analysis/diagnostic-commands-001/report.json).
Remaining compass/raw IMU/ALS, single-button ownership, microphone/settings adapters
and full capacities stay on the parity plan.

Required tests: original sender byte fixtures and pixel differentials; clipped or
malformed RLE rejection before mutation; delta placement/padding/frame IDs; scene
animation takeover; queue/lease/OOM behavior; one-display high-bit policy; actual
compiled RV32 dispatch with native mocks. Preserve existing retained fixtures.
A physical checkerboard→bounded delta test must verify visible output separately.
Large valid messages must return explicit capacity failure until65535-byte ingress
and full storage are integrated; command presence alone is not full-capacity parity.

The first mode3/6 implementation and actual-code tests are recorded in
[the raster report](../../analysis/raster-commands-001/report.json). Native Swift
`RasterCommands.fullFrame` and `boundingBox` generate their RLE payloads without
Android, zlib or a subprocess; they default to8192 bytes and accept an explicit `maximumCommandBytes: 65535`
for the new carrier. Direct GM ingress remains8192 bytes.

Modes3/6 have live verification and remain in the current firmware. The native Swift smoke,
independent trace verification and user visibility confirmation are recorded in
[hardware evidence](../../analysis/raster-commands-native-20261101/report.json).
Mode9 is now installed and visibly confirmed; mode8 is also installed and visibly confirmed; mode15 is now installed and visibly confirmed. Remaining command adapters are pending.
See [mode9 hardware evidence](../../analysis/rect-copy-native-20261102/report.json).

[Mode8 evidence](../../analysis/bundle-native-20261102/report.json) includes the
final-cache/notification hardware checks and independent trace verification.

[Mode15 hardware evidence](../../analysis/text-native-20261102/report.json) records
the native text checks. The inventory explicitly maps its original G2 renderer
reference and MemoMind adapter tests to required aggregate stages; no incomplete
original suite is marked complete by those supplemental tests.
