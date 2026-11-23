# CRKD Android decompilation — 2026-11-09

## Outcome and evidence limits

Extracted the user's installed **com.crkd_app 1.0.365 / versionCode 365** from
the USB-connected Android phone. All four installed APKs were copied unchanged.
Only package metadata and APK files were read; root, private account storage,
app reinstallation, runtime injection and phone setting changes were unnecessary.
No controller traffic was sent and no firmware was installed.

The strongest finding is a stock ATOM+ test-mode path that streams buttons,
both sticks and triggers through a vendor BLE interface. This makes a stock
Glassly driver a credible first experiment. It does not prove the mode is
implemented on every firmware, survives backgrounding, or coexists with HID.

JADX 1.5.6 emitted 9,490 Java source files, ending with 51 decompilation errors
across the whole app (exit 3). The relevant bridge, request builders and decoder
are readable; this is not a claim that the full app can be rebuilt. Obfuscation
renamed many helper classes. Preserve this exact JADX output for cited anchors.

The React Native bundle is **Hermes HBC v98**. P1sec/hermes-dec 0.1.8 at commit
`2e796663e1fedb93dca51060797ebf3327b3fedb` produced full disassembly and pseudocode
(both exit 0), with a v98 support warning and 2,557 decompiler warning lines.
Pseudocode is navigation material, not original or necessarily valid JavaScript.
Use bytecode and native call paths to check important conclusions. The tool's
[README](https://github.com/P1sec/hermes-dec) describes that pseudocode limitation.

## Local artifacts

All paths below are relative to this repository and ignored by Git.

| Path | Contents |
| --- | --- |
| `research/downloads/crkd-android-20261109/apks/` | Base, arm64-v8a, English and xxhdpi APKs |
| `research/downloads/crkd-android-20261109/extraction.json` | APK size/hash inventory |
| `research/downloads/crkd-android-20261109/unpacked/` | Extracted assets and native libraries |
| `research/decompiled/crkd-android-20261109/jadx/` | Java sources, decoded manifest and resources |
| `research/decompiled/crkd-android-20261109/index.hasm` | Hermes disassembly, 1,384,023 lines |
| `research/decompiled/crkd-android-20261109/index.pseudo.js` | Hermes pseudocode, 1,347,698 lines |
| `research/decompiled/crkd-android-20261109/selected-functions/` | Eleven focused bytecode functions plus index |
| `research/decompiled/crkd-android-20261109/*.log` | JADX/Hermes warnings and completion records |
| `research/downloads/crkd-android-20261109/firmware-catalog.json` | Public production catalog snapshot |
| `research/downloads/atom-plus-firmware/` | Three official catalog-listed binary images |
| `research/decompiled/crkd-android-20261109/firmware-inspection.json` | Sizes, SHA256, headers and entropy |
| `research/captures/android-20261109/package.txt` | Private package metadata |
| `research/tools/hermes-dec/` | Pinned decompiler checkout |

`sources.lock.json` records verified APK, bundle, catalog and firmware hashes.
No OEM image, app binary or decompiled vendor source is intended for publication.

## Product dispatch and BLE UUIDs

Source root for Java anchors: `research/decompiled/crkd-android-20261109/jadx/sources/`.

`com/crkd_app/CrkdNativeModule.java:97` (`connectToDevice`) routes type `atomp`
to `bleNdp`, the `com.crkd_app.m` wrapper around `com.host4.platform`.
Nitro Deck+ / Nitro Deck 2 / ULT PRO share this route. Other app branches use
GHIC or guitar libraries; their presence does not identify the ATOM+ chipset.

`com/host4/platform/controller/CommunicateController.java:954` (`connect`)
installs these constants from `util/Constants.java`:

| Function | Service | Characteristic |
| --- | --- | --- |
| Normal command write | FF00 | FF01 |
| Normal notification | FF00 | FF02 |
| OTA control and notification | FF10 | FF11 |
| OTA firmware data write | FF10 | FF12 |

Full UUIDs use `0000XXXX-0000-1000-8000-00805F9B34FB`. Properties, handles,
security/bonding requirements and the actual device advertisement still need
live discovery. These UUIDs are app constants, not a completed GATT capture.

## Stock input test mode

The explicit ATOM+ branch of `CrkdNativeModule.setDeviceTestMode`, around line
1918, passes **130 / 0x82** when `val == "enable"`, otherwise **0**, to
`CommunicateController.switchHandleMode`. That calls
`KrCmdController.setKeyBoardMode`, constructing `SetKeyBoardModeReq` (command 1).

`kr/request/BaseReq.getData` builds normal commands as:

```text
[total length: u8] [command: u8] [payload...] [sequence: u8]
```

The static sequence increments modulo 256. Thus the recovered test-mode frames
are `04 01 82 SS` to enable and `04 01 00 SS` to disable. These have **not** been
transmitted here. Do not assume mode changes are nonpersistent until measured.
Subscribe to the discovered normal notification characteristic before testing,
retain command responses and always record the exit attempt.

`manager/BLERxManager.lambda$heartbeatDispose$28` sends normal command bytes
`04 88 01 02` from its heartbeat scheduler. This is a separate fixed frame, not
an instance of `BaseReq` sequence allocation. Determine from the scheduler and
capture whether and when it is needed; do not infer battery idle behavior from
the existence of this code.

`util/BleModeEvent.initData` dispatches event IDs `07`, `08`, `0e`, `13`, `17`,
and `40` to `kr/response/TestModeEventRsp`. This is a multi-product list;
the ATOM+'s actual event ID has not been measured.

The decoder reads the notification buffer directly (zero-based offsets):

| Offset | Meaning in the app decoder |
| --- | --- |
| 0 | Not interpreted by this decoder; retain and determine framing |
| 1 | Event ID used by the dispatcher |
| 2, 3 | Left stick X, Y, unsigned bytes |
| 4, 5 | Right stick X, Y, unsigned bytes |
| 6–9 | Low 32 bits of button bitmap, little endian |
| 10, 11 | Left/right trigger values, unsigned bytes |
| 12 | Not interpreted by this decoder |
| 13 | Button bitmap bits 32–39 |

It accesses through byte 13, so a future parser must require at least 14 bytes
before indexing. Exact total length and trailer behavior remain unknown.
The app's neutral helper expects all four stick axes at 128 and no button bits.
Treat that as an app convention pending measurement of actual centers/deadzones.

`util/NormalManager.getKeyData`, combined with `com/crkd_app/m.b`, maps the
following raw bits to app labels. These are **not physically validated masks**:

| Mask | App label | Mask | App label |
| --- | --- | --- | --- |
| 0x000001 | A | 0x000002 | B |
| 0x000004 | X | 0x000008 | Y |
| 0x000040 | Left | 0x000080 | Right |
| 0x000100 | Up | 0x000200 | Down |
| 0x001000 | LB | 0x002000 | LT |
| 0x004000 | LS | 0x008000 | RB |
| 0x010000 | RT | 0x020000 | RS |
| 0x100000 | Minus | 0x000800 | Plus |
| 0x200000 | Menu | 0x800000 | Home |

`M7/i.java:392` emits `crkdble_keyevent` with `lx`, `ly`, `rx`, `ry`, `ltv`,
`rtv`, and fields for currently pressed recognized buttons. It emits a snapshot,
so a Glassly driver must compare successive snapshots to generate releases.
Do not mistake absent button fields for a lost release event or retain held
state across disconnects. Physical label swaps and unsupported bits need testing.

## Firmware discovery and files

Hermes functions **7366/7367** implement `getFirmwareList`; generator **21445**
forms the production URL from `getServerURL()` plus `/device/firmware`.
An unauthenticated GET to [the production catalog](https://api.crkd.gg/device/firmware)
succeeded. Only production was requested; the staging branch was not queried.

Its `ATOM_PLUS` array contained these entries at capture time:

| File | Display version | Internal version | Audience | Size |
| --- | --- | --- | --- | --- |
| [20260723.bin](https://a.crkd.gg/firmware_release/ATOM_PLUS/20260723.bin) | v1.0.0 | 0260723a | beta, all | 400,540 |
| [20260814.bin](https://a.crkd.gg/firmware_release/ATOM_PLUS/20260814.bin) | v1.1.0 | 0260814a | beta | 400,976 |
| [20260912.bin](https://a.crkd.gg/firmware_release/ATOM_PLUS/20260912.bin) | v1.1.0 | 0260912a | beta | 430,188 |

All three downloaded successfully. The public release and beta labels come from
the catalog, not from a controller. None is established as this unit's installed
version. Hashes are pinned for reproducibility, not cryptographic vendor identity.

No firmware `.bin`, `.ufw`, `.hex`, `.dat` or `.zip` was found among base-APK
assets. The three downloaded images have high byte entropy (~7.995–7.996),
shared portions of their first 64 bytes and no convincing chip/SDK strings.
Encryption, compression or another encoding is plausible, not yet identified.
Do not mistake chance printable substrings in these files for chip evidence.

## OTA path recovered from the app

`CrkdNativeModule.deviceOTA` routes `atomp` through `modifyService`, then
callback `L9/x.java:219` reads the supplied file with `Files.readAllBytes` and
calls `CommunicateController.otaUpgrade`. No host-side firmware transformation
occurs in this callback or the traced transfer path.

1. Subscribe to OTA control notifications on FF11.
2. `DeviceOTAReadyReq`, command **0x0050**, supplies a **CRC-16/XMODEM** and
   image length. `util/Utils.crc`: polynomial 0x1021, initial 0, MSB first,
   final mask 0xffff, no final XOR. Payload: CRC big endian (2 bytes), length
   big endian (3 bytes).
3. `SendBytesNumberReq`, command **0x0051**, requests the block size. Its response
   reads status at offset 2 and a big-endian size at offsets 3–4.
4. The controller class splits the raw file into those logical blocks;
   `BLERxManager.writeOtaUpgrade/writeUpgrade` further splits writes into
   **20-byte** chunks on FF12. ACK progress chooses the next logical block.
5. `SetDataSendReq`, response ID **0x52**, reads status at offset 3 and a
   big-endian cumulative count at offsets 4–7.
6. `DeviceOTACompleteReq`, command **0x0053**, completes transfer.

OTA request construction differs from normal commands:

```text
[total length: u8] [command low: u8] [command high: u8] [payload...]
```

There is no normal-command sequence byte in `BaseReq.getOTAData`. Response
layouts differ across request classes; do not apply a single assumed layout to
all replies. OTA retry/error/reconnect handling still needs bytecode and capture
review before implementing a writer.

CRC protects transfer integrity; it is not evidence that the bootloader accepts
unsigned modifications. The host sends opaque image bytes. Device-side image
authentication, partitioning, decryption and recovery are unknown. Generic USB
classes in this SDK do not establish ATOM+ USB data or bootloader support.

## Reproducing the offline decompilation

With the same extracted files and pinned tool checkout, run from the repository:

```sh
JADX_CONFIG_DIR="$PWD/research/jadx-config" JADX_CACHE_DIR="$PWD/research/jadx-cache" \
  jadx -j 4 -d research/decompiled/crkd-android-20261109/jadx \
  research/downloads/crkd-android-20261109/apks/base.apk

PYTHONPATH=research/tools/hermes-dec/src python3 -m hermes_dec.disassembly.hbc_disassembler \
  research/downloads/crkd-android-20261109/unpacked/base/assets/index.android.bundle \
  research/decompiled/crkd-android-20261109/index.hasm

PYTHONPATH=research/tools/hermes-dec/src python3 -m hermes_dec.decompilation.hbc_decompiler \
  research/downloads/crkd-android-20261109/unpacked/base/assets/index.android.bundle \
  research/decompiled/crkd-android-20261109/index.pseudo.js
```

## Next concrete experiment

Record an ATOM+ in the official app's test screen: advertisement and discovered
services, entry command/ACK, ordered press/release/chords, both sticks, trigger
states, heartbeat timing, exit command and reconnect. On the rooted Android,
a scoped app instrumentation or Bluetooth capture could verify this without
modifying controller firmware. Confirm the target before collecting traffic;
avoid collecting unrelated Bluetooth sessions or private app account data.

Then decide whether a stock driver satisfies Glassly. If it does, prioritize
native iOS/Android integration and real background/locked/battery tests. Continue
image decoding and recovery research separately if CFW remains useful.
