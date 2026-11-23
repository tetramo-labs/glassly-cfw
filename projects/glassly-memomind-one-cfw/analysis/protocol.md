# MemoMind One Bluetooth update protocol

Derived from the successful stock 1.0.2.151 → 1.0.3.127 update, Android app
1.3.81 / model H001Y. This is observed protocol evidence, not proof that custom
images will boot or be accepted. No packets were injected by this analysis.

## Capture and byte-for-byte proof

Authoritative input: `captures/ota-complete.btsnoop`, SHA-256
`cee5e838e3c69a9dd0a5ccbfb8e6165bafc1e730891fae6e12581e6ef73ebf18`.
Downloaded image: `captures/firmware/ota-1.0.3.127-jhv3_release.bin`,
2,185,697 bytes, SHA-256
`08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`.

`scripts/decode_memomind.py` uses TShark to reassemble HCI/L2CAP/RFCOMM, then
parses the application stream without relying on RFCOMM write boundaries.
The verified report is `analysis/protocol/ota-final/summary.json`:

- 3,457 OTA data chunks; every chunk's CRC32 is valid.
- Every chunk's offset and bytes match the downloaded image.
- The independent encoder reproduces every captured chunk byte-for-byte.
- All 494 device-requested blocks were transferred contiguously before their
  success acknowledgment; each acknowledgment's sequence matches the last
  chunk in that block.
- Recovered bulk range is `[162757, 2185697)`, exactly 2,022,940 bytes;
  SHA-256 `4b70de3f04f4bd5f318546d80ee69c4cfbf0b221752b53cb7c057f8484d21e8f`.
- No requested range is missing, and terminal offset 0 / block size 0 is present.
- The first 162,757 bytes were not sent by the bulk-data command. The first
  18 bytes were separately sent as the file identifier. The device selected
  starting offset 162,757. Native analysis identifies a matching-image resume
  path and the offset calculation below; the origin of this session's retained
  prefix is still unresolved. Do not claim the entire downloaded image was
  sent over Bluetooth.

Reproduce into a new directory:

```sh
python3 scripts/decode_memomind.py captures/ota-complete.btsnoop \
  captures/firmware/ota-1.0.3.127-jhv3_release.bin analysis/protocol/new-verification
python3 -m unittest discover -s scripts -p test_decode_memomind.py -v
```

## Transport and discovery

This update uses Bluetooth Classic RFCOMM, not BLE GATT. SDP evidence is
retained in `analysis/protocol/sdp.txt`:

| Service UUID (Bluetooth base UUID suffix) | Observed RFCOMM channel | Service name | Observed use |
|---|---:|---|---|
| `00007033-0000-1000-8000-00805f9b34fb` | 5 | COM7 | App control, device identity/settings, diagnostics |
| `00007034-0000-1000-8000-00805f9b34fb` | 6 | COM8 | OTA |
| `00002024-0000-1000-8000-00805f9b34fb` | 4 | COM6 | Additional short binary messages, semantics unresolved |
| `00002026-0000-1000-8000-00805f9b34fb` | 7 | COM9 | Advertised; no application payload in selected trace |

Resolve the RFCOMM channel through SDP rather than treating these channel
numbers as universal. The Java APK implementation uses
`BluetoothDevice.createRfcommSocketToServiceRecord(uuid)` in
`analysis/jadx/base/sources/dev/lenhart/flutter_blue_classic/BluetoothConnection.java`.
SDP advertises provider string `WUQI` on audio services. That string alone does
not identify the exact processor model. Existing pairing/bonding preceded this
recording; the initial authentication/bond exchange remains uncaptured.

## Normal app envelope

Observed channel-5 frames use the public GM envelope:

```
head:u8 | logical_length:u24be | sequence:u8 | service:u8 | command:u8
      | payload | sum16:u16be
```

The first head is `fa`; current public documentation specifies numbered
continuation heads `01`, `02`, etc. The checksum is the additive sum of all
preceding bytes modulo 65536.
Simple payload fields have `type:u8 | length:u24be | value`. Type meanings are
not comprehensively established. Larger messages repeat the seven-byte header
across fragments: frame 401 is 512 bytes and frame 404 is 20 bytes, both declaring
logical length 523 and sharing sequence/service/command. Each fragment has its
own additive checksum. This old-firmware capture repeats `fa` instead of the
currently documented continuation index. The offline OTA decoder inventories
those fragments separately; `scripts/memomind_transport.py` supplies full GM
stream/TLV reassembly for the public numbered contract and an explicit opt-in
`legacy_repeat_fa` compatibility mode for the captured old behavior.

**Hardware correction on1.0.3.127:** RFCOMM ingress is asymmetric. The glasses'
receive reassembler requires642-byte bodies (651-byte full physical frames),
while responses still use503-byte bodies. Both retain the same logical length,
event/service/command, per-frame checksum and numbered request continuation heads.
The native receiver ignores RFCOMM SDU boundaries and collects exactly
`min(remaining_body,642)+9` bytes. Sending503-byte request bodies caused a
deterministic checksum error before the renderer was called. The corrected
5102-byte geometry request passed in8 frames on hardware.

For custom0x0f/0x7d, each incomplete request fragment produces an independent
empty9-byte ACK echoing its head and event/service/command. The client explicitly
enables numbered fragment ACKs, waits for the matching ACK, and stops on a native
rejection. `gm_frames(..., fragment_payload=642)` / `request_gm()` select this
profile; the public/default503-byte encoder remains available. See
[native receive evidence](ghidra/display-adapter/fragment-review/report.md) and
`captures/graphics-runtime-20261031/boundaries-03.json` for the hardware result.

Immediately before the OTA connection, frame 1615 sends service 1 / command
`0x1c`, field bytes `08 000001 01`. The response is the same sequence and command,
field bytes `06 000001 01`. The app logs this as
`notifyDeviceBeforeOta success`. The helper `encode_control` supports complete
unfragmented packets; it refuses messages larger than the observed 512-byte
fragment size.

## OTA envelope

```
70 07 6e | flags:u8 | command:u8 | payload_length:u16be | payload | 33
```

Observed requests use flags `0xc0`, responses `0x00`. Requests begin payload
with a sequence byte; responses begin with a transport-status byte (zero in
this successful trace), then the request sequence. The `33` footer is constant,
not a checksum. These flag/status meanings are inferred from traffic direction
and matching replies; other values and failure behavior remain untested.

The successful flow, with frame numbers in the authoritative capture:

| Step | Command | Request parameters after sequence | Observed response / interpretation |
|---|---:|---|---|
| Attach / query device | `02` | `ff ff ff ff ff` (1647) | Device information (1658); app logs attachDeviceInformationResponse |
| Get file-ID request | `e1` | Empty (1660) | `00 00000000 12` after status/sequence (1671): file offset 0, ID length 18 |
| Check image | `e2` | First 18 image bytes (1678) | `03` after status/sequence (1686), app says device can update |
| Enter update mode | `e3` | Empty (1689) | `00 00027bc5 1000 01` (1698): success, offset162757, block4096, CRC32 required |
| Send requested bytes | `e5` | Offset, bytes, CRC32 (3,457 requests) | 494 block acknowledgments with next range |
| Verify update status | `e6` | Empty (9842) | `00` after status/sequence (9844) |
| Reboot | `03` | `00` (9845) | `00` after status/sequence (9847), then disconnect |

The parent investigation independently verified firmware 1.0.3.127 after
reconnection. App log names support these step meanings; raw payloads and
timestamps are retained in `ota-frames.json`.

## Bulk transfer and acknowledgments

Request command `e5` payload:

```
sequence:u8 | file_offset:u32be | data:bytes | crc32:u32be
```

CRC32 is the standard zlib/IEEE reflected CRC32 over `data` only. The largest
observed data chunk is 630 bytes. A requested 4096-byte block is split into six
630-byte chunks and a final 316-byte chunk; complete wire sizes are 647 and 333
bytes respectively. The final requested block is 3612 bytes. Each whole block
is followed by one response:

```
transport_status:u8 | sequence:u8 | result:u8 | next_offset:u32be
                   | next_block_size:u16be | delay_bytes:2
```

Success is zero for the observed transport status and result. The final
response reports next offset 0 and block size 0. Delay bytes are `0000` in this
capture; their interpretation for nonzero values is not established.

Sequence allocation is not a monotonically increasing number across all
chunks: the first block uses 5–11, the next 6–12, then 7–13. The base advances once
per logical block, with per-fragment increments modulo 256; the acknowledgment
echoes the last fragment's sequence. The last block has six chunks and ends
with the same last sequence value as the preceding seven-chunk block. A new
flasher must not mistake that valid sequence reuse for a duplicate acknowledgment.

## Native evidence for the initial offset

Direct Ghidra analysis of the captured application component, mapped at
`0x041eb020` from its image header and partition metadata, identifies the OTA
parser at `0x0423a90e`. This is static analysis, not observed device memory.
Startup instructions at `0x041eb03e` establish `gp = 0x02011688`.

The `e2` branch compares the incoming payload length and payload CRC32 with
retained globals at `gp+0x4c8` and `gp+0x4c4`; equality sets a resume flag at
`gp+0x4dc`. The `e3` branch keeps the cursor at `gp+0x4cc` only if that flag is
set and `0 < cursor < payload_length`; otherwise it resets the cursor to zero.
The source fields match the independently validated outer envelope: payload
length at file byte 6 and payload CRC32 at byte 14.

Response builder `0x0423a278` adds **18 (`0x12`)** to the internal cursor before
encoding the requested file offset as big-endian, and requests
`min(payload_length - cursor, 4096)` bytes. Consequently the captured initial
file offset `0x27bc5` corresponds to internal payload cursor `0x27bb3`
(162,739). It is a payload cursor, not a component boundary.

Evidence: `analysis/ghidra/integrity/function-0423a90e.{c,asm}` and
`analysis/ghidra/integrity/function-0423a278.{c,asm}`. These exports include the
startup-derived RAM mappings described in `analysis/ghidra/findings.md`;
the relevant branch and offset arithmetic also have assembly exports. These
observations establish a resume mechanism and explain the numerical offset.
They do not establish whether this capture resumed earlier persistent state,
an earlier attempt in the current connection, or another retained-state path.

## Remaining work before a custom flashing driver

Derive timeout/retry and resume behavior from code or additional controlled
experiments, especially whether a missing acknowledgment permits retransmission.
Trace the source and lifetime of the retained cursor to determine why this
session resumed at that particular position. Preserve device-driven range
requests and image/model checks; do not blindly stream the whole file.
Establish signature and boot-verification enforcement, recovery routes, and
the target ISA/address map separately. A checksum-valid modified container is
not proof of an accepted or bootable patch. The G2 BLE transport cannot be used
unchanged for this RFCOMM service.
