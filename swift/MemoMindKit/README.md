# MemoMindKit

Native Swift MemoMind One protocol library and macOS RFCOMM flasher. The executable
uses the Mac's Bluetooth controller directly through IOBluetooth. It needs neither
the Android bridge nor Python at runtime.

From this repository's root:

```sh
swift build --package-path swift/MemoMindKit -c release
swift test --package-path swift/MemoMindKit
swift/MemoMindKit/.build/release/memomind --help
swift/MemoMindKit/.build/release/memomind devices
```

Button and microphone captures use the same transport and durable trace:

```sh
swift/MemoMindKit/.build/release/memomind buttons \
  --address 4C:3C:8F:90:CC:C3 --seconds 180 --output captures/buttons-new
swift/MemoMindKit/.build/release/memomind microphone \
  --address 4C:3C:8F:90:CC:C3 --seconds 10 --output captures/microphone-new
```

The button client subscribes to cooked events, saves each poll before ACK, and
stops on transport or session errors. The microphone command enables ENC through
GM `01/2f`, then uses the existing recording RFCOMM service `2024`. It requests
legacy records and saves individual 40-byte Opus packets locally. Capture is
bounded to 1–15 seconds; stop has no business ACK, so queued data is drained
before closing. No firmware write occurs. This does not add the G2 microphone
lease or configurable PCM/channel modes.

On `minimal-owner-flash-004`, physical single/long/release button actions were
captured without reported drops. Microphone start/stop and a second session
passed; 488 frames from the first capture decoded to 9.76 seconds of mono PCM
at 16 kHz, and the user confirmed the audio. See
[the evidence](../../analysis/wake-display-20261102/microphone-verification.json)
and [confirmation](../../analysis/wake-display-20261102/microphone-confirmation.json).

The package requires Swift 5.9 or later and macOS 13 or later. The core library
also targets iOS 15 or later; the RFCOMM transport and executable are Mac-specific.
Tests require this repository's captured firmware and transcript fixtures, and
fail if those fixtures are missing.

## Commands

Put the glasses in pairing mode and pair them with this Mac when necessary.
The terminal or application hosting the executable needs Bluetooth permission.
`devices` reports local controller status and the paired-device cache; it does
not scan. `probe` opens the normal service and sends heartbeat/device-info only:

```sh
swift/MemoMindKit/.build/release/memomind probe \
  --address 4C:3C:8F:90:CC:C3 \
  --output captures/mac-probe-01
```

`inspect` performs offline eligibility validation. `check` sends the pre-OTA
notification, opens the separate OTA service, and checks attach/file identification
and can-update responses. It stops before OTA entry and sends zero firmware chunks.
This changes transient updater state, so it is distinct from the read-only probe.

```sh
swift/MemoMindKit/.build/release/memomind check \
  --address 4C:3C:8F:90:CC:C3 \
  --firmware captures/firmware/exclusive-store-reader-001/firmware.bin \
  --expected-sha256 270dfe85438e6ff0f904a09215e15419292e16b8c7bbc36aafec50543c780c55 \
  --output captures/mac-check-01
```

`flash` additionally enters OTA, serves the device-requested blocks, checks every
reply, and requests reboot. The explicit write flag is required:

```sh
swift/MemoMindKit/.build/release/memomind flash \
  --address 4C:3C:8F:90:CC:C3 \
  --firmware captures/firmware/exclusive-store-reader-001/firmware.bin \
  --expected-sha256 270dfe85438e6ff0f904a09215e15419292e16b8c7bbc36aafec50543c780c55 \
  --output captures/mac-flash-01 \
  --confirm-write
```

There is no automatic retry, resume, rollback, or claim that a reboot ACK proves
successful boot. Modified firmware must start at offset 18. The normal connection
stays open during OTA, with unsolicited traffic drained and logged. Service
channels are discovered using UUIDs `00007033-0000-1000-8000-00805f9b34fb` and
`00007034-0000-1000-8000-00805f9b34fb`, using cached SDP records first and a bounded
fresh query when absent. Captured channel numbers are not hard-coded.

The stock `0x07d0` block pacing response is supported with a two-second wait and
control-link checks every 100 ms. This is a forward block request, not a retry.
Unknown pacing values still stop the transaction. See the
[native pacing evidence](../../analysis/ota-pacing-20261103/NOTES.md).

Every live attempt creates a new private directory containing `trace.jsonl` and
either `result.json` or `failure.json`. Existing directories are rejected. RX,
TX submission and native TX completion are recorded separately and fsynced.
Native completion means handed to the controller, not a remote application ACK.
These are RFCOMM application traces, not an HCI capture of bonding or radio traffic.

## Firmware eligibility

The compiled catalog admits captured stock 1.0.3.127, the boot-verified
`exclusive-store-reader-001`, the reviewed fixed `flash-canary-001`, and
`raster-commands-001` with optional modes3/6, and `rect-copy-001` with mode9, and `bundle-commands-001` with mode8. All require
their explicit SHA-256,
exact lengths, container CRCs and pinned stream layout. Unknown images are rejected
before connecting. A JSON manifest or matching caller-supplied hash cannot add a
release to the catalog. Catalog admission establishes exact reviewed bytes; it
does not establish successful boot or hardware flash behavior.

This ports the flashing transaction and native release validation. Firmware
construction, LZMA decompression/repacking and reproducible patch construction
remain in the existing offline Python tools. New builds must pass those checks
before a reviewed catalog entry is added, following the pinned-artifact approach
in Glassly's `G2FirmwareCatalog`. See [catalog provenance](Documentation/FirmwareCatalog.md).

## Verification

```sh
swift/MemoMindKit/.build/release/memomind replay \
  --firmware captures/firmware/ota-1.0.3.127-jhv3_release.bin \
  --expected-sha256 08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712 \
  --transcript analysis/protocol/ota-final/rfcomm.tsv
```

The replay is specific to the original recorded stock transaction, including its
device-selected resume offset. All 3,464 outgoing packets match exactly; it consumes
501 incoming records and transfers 3,457 chunks across 494 blocks. The outgoing
wire SHA-256 is `f4acaa5ca1a8a02001328eebc88c52be4ab65216cf8f42c70e09e77dda294004`.

56 Swift tests cover independent Python-generated wire vectors, actual captured
replay, fragmented reads, GM acknowledgments, malformed replies, range/sequence
checks, no-retry behavior, image corruption and all four required catalog artifacts.
The canary cases cover strict JSON, exact fixed requests, reply correlation, one
attempt per client, poisoned failures and monotonic terminal status.
The broader G2/firmware suite remains `python3 tests/run_tests.py --output NEW_DIR`.
The Mac subsequently paired successfully and transferred the full 2,223,753-byte
reader image in 543 blocks / 3,800 chunks. An independent Python replay reconstructed
the exact image from the native application trace and verified every outgoing frame.
After the first post-reboot connection timed out, waking the glasses allowed a new
read-only connection. The runtime profile and full 256-byte application header
matched the image, and the user confirmed “Glassly firmware ready.” Post-reset
flash topology and badmap checks also matched the prior capture, and the fixed
test sector plus neighbor were erased. These are application traces, not an
independent HCI capture. See [transfer evidence](../../analysis/native-mac-hardware-20261101/report.json),
[boot and storage verification](../../analysis/native-mac-preflight-20261101/verification.json)
and [original port evidence](../../analysis/swift-port-20261101/report.json).

## RLE drawing commands

`RasterCommands.fullFrame(pixels:rowStride:)` builds mode6 for a600×350 packed
GRAY4 frame. `boundingBox(pixels:x:y:width:height:frameID:rowStride:)` builds mode3
from local box pixels; x/width are multiples of4 and y/height multiples of2.
Both use the high nibble for the left pixel, validate exact input/stride bounds,
and reject RLE commands larger than the current8192-byte native limit.

They require firmware advertising modes3/6; they do not open Bluetooth, compress
an outer transport envelope or manage the display lease. Carry the returned
bytes in the graphics command's BYTES TLV. The optional native receiver maps a
stereo delta to the first/left box and advertises `rasterLens:"first-left"`.
Eight native Swift test groups use47 independently verified G2/C golden vectors.

## Fixed flash test protocol

`FixedCanaryClient` uses the shared transport for the optional canary runtime.
`verifyProfile()` checks its exact read allowlist; `status()` returns a Codable
`CanaryStatus`. `validateWorker()` runs the read-only worker test, while
`runFixedCanary()` performs the fixed erase/program/verify/restore test. Both
consume the native once-per-boot attempt. Do not run them sequentially in one boot.
A start requires an observed idle status. A lost or invalid reply poisons the client;
there is no retry, reset, arbitrary address or arbitrary payload operation.

The caller must first verify the exact installed image/header, complete current
backup, owner gates and fresh topology/badmap. A profile string alone establishes
none of those conditions. A host timeout cannot cancel a native flash operation.
The client is synchronous and single-owner; configure transport deadlines as well.
See [native fixed-test details](../../runtime/graphics/FLASH_CANARY.md).

## Glassly integration

`MemoMindCore` owns the codecs, `GMSession`, `OTATransaction`, `DeviceIdentity` and
`EligibleFirmware`. It imports Foundation/CryptoKit, with no Android, IOBluetooth,
UI, Expo or subprocess dependency. `MemoMindTransport` is a connected byte-stream
interface with throwing `read(timeout:)` and `write(_:)` methods. Access is serial;
there is one transaction per connection attempt.

For `~/dev/glassly`, add this core as a local Swift package dependency and provide
a MemoMind device adapter beside `mobile/modules/bluetooth-sdk/ios/Source/sgcs/`.
Its catalog/progress/result mapping can follow `G2Flasher.swift`; a Mac harness can
follow `tools/rayneo-io-mac`. Keep protocol logic shared instead of duplicating it.
No Glassly source files have been changed by this port.

The iOS transport is still unproven. Apple's
[IOBluetoothRFCOMMChannel](https://developer.apple.com/documentation/iobluetooth/iobluetoothrfcommchannel)
is a macOS API. Core Bluetooth's Classic support does not by itself establish
access to these captured RFCOMM services. The actual iPhone app transport must be
captured and mapped to an available API, or firmware must expose a suitable BLE
transport. An [External Accessory](https://developer.apple.com/documentation/externalaccessory)
route would depend on supported MFi accessory protocols. Do not assume changing
the transport import is enough.

The Mac transport pumps the main run loop over asynchronous native operations.
Do not call it from a Swift task-pool executor. A future mobile adapter must avoid
blocking UI callbacks: use an appropriately isolated serial worker/byte queue or
adapt the session interface to async operations. See the
[transport lifetime documentation](Sources/MemoMindBluetooth/README.md).

The `raster-commands-001` release has now been flashed directly from this Mac and
boot verified. Native Swift mode6/mode3 commands produced the RLE/checkerboard
pattern confirmed by the user; malformed commands were rejected and the display
cleared. See [hardware evidence](../../analysis/raster-commands-native-20261101/report.json).

`RasterCommands.rectangleCopy(source:destination:)` emits mode9 using
`RasterRectangle` pixel bounds. Positive matching rectangles must fit600×350; odd
coordinates/dimensions, overlaps and self-copy are supported. The exact
`rect-copy-001` catalog image was flashed natively and boot verified, and the user
confirmed the second copied pattern. [Hardware evidence](../../analysis/rect-copy-native-20261102/report.json).

`RasterCommands.bundle(_:)` packs up to 255 supported commands into the current
8192-byte native limit; it validates envelopes, not all child semantics. A later
child failure does not roll back prior effects. `GMSession` offers an optional
throwing `responseFilter` to route same-event notifications separately; callers
must also validate unsolicited messages and explicitly drain notifications.
The mode8 image is boot verified and its B8/checkerboard bundle was visibly
confirmed. [Hardware evidence](../../analysis/bundle-native-20261102/report.json).

`RasterCommands.builtinText(bytes:x:y:options:)` and its String overload encode
mode15 with up to255 UTF8 bytes. NUL and malformed UTF8 are rejected; bytes1..31
are horizontal offsets, including LF/CR. Native resource glyph support is checked
by the receiver. Bundles accept text envelopes after checking native capability.
`text-commands-001` is admitted by exact image/component pins and has boot/live
text verification; shared core typechecks for iOS15, but native iOS transport is
not established. [Hardware evidence](../../analysis/text-native-20261102/report.json).


## Large raw commands

The minimal-owner `GLASSLYCFW/1` profile adds a 256 KiB logical flash asset store
and a bounded raw-command carrier. `LargeMessage(command:token:)` creates
CRC32-checked begin/chunk/commit packets for 1...65,535 bytes, with a nonzero token.
`GMSession.sendLargeGraphicsMessage(_:token:event:)` probes capabilities, waits
for every chunk ACK, and returns the actual command reply. Serialize use of the
session, supply fresh tokens, and validate that reply with the command's normal
parser. A lost commit reply is ambiguous: there is no automatic retry or abort.
This is available in the shared Swift core for eventual Glassly integration.

Raster and bundle builders accept `maximumCommandBytes: 65535`; their default is
8192. Use the carrier for these larger commands, since the native GM request cap
is unchanged. Assets have an ephemeral logical flash map, not reboot persistence.
Compressed transport and its inflater histories remain separate work. The
[hardware record](../../analysis/minimal-owner-queue-fix-20261102/hardware-result.json)
distinguishes advertised limits from completed device checks.
