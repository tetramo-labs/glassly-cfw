# MemoMind One 1.0.3.127 OTA container

Offline analysis of the captured 2,185,697-byte
`captures/firmware/ota-1.0.3.127-jhv3_release.bin`:
SHA-256 `08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`.
All claims below distinguish byte observations from interpretation. This is
ordinary Python/local binary evidence, not a REA Evidence record.

## Container and checksums

Every byte is accounted for. There is an 18-byte outer `ME` envelope, a
132-byte inner header/table, seven consecutive LZMA-alone streams and a
four-byte trailing CRC32. No separate opaque signature block was identified.
This does **not** establish that modified images will be accepted by the updater
or bootloader; verification may occur elsewhere or depend on header fields.

| Field | Offset | Observation |
|---|---:|---|
| Outer magic/profile | 0 | `4d45 0201 1001`; semantics beyond magic retained as unknown |
| Payload length | 6 | BE32 = file length minus 18 |
| Uninterpreted outer word | 10 | Four zero bytes |
| Outer CRC32 | 14 | BE32; standard zlib CRC32 of bytes 18 through EOF |
| Inner magic | 18 | LE32 `0xabcd6543` |
| Packed version | 22 | LE32 `0x1000307f`, consistent with 1.0.3.127; encoding inferred |
| Unknown inner words | 26, 30 | LE32 `0x7f`, `0xffffffff` |
| Metadata unpacked/packed sizes | 34, 38 | LE32 344 / 166 |
| Uninterpreted words | 42, 46 | LE32 2 / 0 |
| Component table | 50 | Six 16-byte records: unpacked size, packed size, flash start, flash end, all LE32 |
| Table CRC32 | 146 (`0x92`) | LE32 zlib CRC32 of bytes 34..145 |
| LZMA streams | 150 (`0x96`) | Metadata then six table-ordered components |
| Final CRC32 | EOF minus 4 | LE32 zlib CRC32 of all packed stream bytes, excluding the trailer |

All seven streams use LZMA-alone properties `5d00800000` (dictionary 32 KiB,
lc=3, lp=0, pb=2) and a known LE64 decompressed size. Every stream decodes to
its declared length, reaches the end marker, and leaves no unused data within
its declared boundary. The final stream ends exactly four bytes before EOF.

Each component begins with an eight-word/32-byte LE header:
magic `0xa4e49a17`, body length, unknown version/flags, load address candidate,
body CRC32, zero, auxiliary address of unknown meaning, zero. All six stored
lengths and body CRC32 values match. The load-address field also matches the
separate partition metadata. It is not assumed to be a proven runtime entry.

## Components and partition metadata

The 344-byte metadata stream contains six header words followed by 16 records
of five LE32 words: type, flash start, load address, body size, allocation size.
The count word is 16. Every OTA component matches exactly one partition's
start/end, load address and body length. Empty partitions are not included in
this update; the OTA is therefore not a complete physical flash dump.

| Stream | Packed offset | Packed bytes | Unpacked bytes | Flash range (end exclusive) | Load address | Inferred role |
|---|---:|---:|---:|---|---|---|
| 0 | `0x96` | 166 | 344 | n/a | n/a | Partition metadata |
| 1 | `0x13c` | 481265 | 909676 | `0x10000..0x123000` | `0x14010020` | Bluetooth/system RISC-V image; BT stack strings |
| 2 | `0x7592d` | 437783 | 695512 | `0x123000..0x1eb000` | `0x26000000` | DSP; `xtensa_intr.c`, HiFi and audio algorithm strings |
| 3 | `0xe0744` | 914600 | 1773208 | `0x1eb000..0x3eb000` | `0x041eb020` | Main application RISC-V image; UI, OTA, device services |
| 4 | `0x1bfbec` | 283737 | 284300 | `0x3eb000..0x481000` | 0 | Resource/data image; precise meaning unresolved |
| 5 | `0x205045` | 986 | 3616 | `0x77a000..0x77c000` | 0 | Configuration/data; precise meaning unresolved |
| 6 | `0x20541f` | 67006 | 81594 | `0x6df000..0x6f8000` | 0 | `SRRD` data container; precise meaning unresolved |

The complete 16-partition inventory and hashes are in
`analysis/firmware-container.json`. `analysis/extracted/validated-1.0.3.127`
contains compressed streams, full images and bodies with their 32-byte image
headers removed. Never confuse a body offset with an image or container offset.

## ISA and platform evidence

Image 1 and 3 bodies start with little-endian bytes
`a142 73b00230 93020008 73b04230`, decoding as RISC-V compressed `li t0,8`,
`csrrc zero,mstatus,t0`, `addi t0,zero,128`, `csrrc zero,mie,t0`.
The code also contains RISC-V exception names `mcause`, `mepc`, `mtval`, and
32-bit register formatting. These support RV32 with compressed instructions;
the complete extension set remains unestablished. Both starts look like reset
initialization and are candidate entrypoints, not dynamically observed entries.

The flash starts and load addresses are consistent with image 1 using the
`0x14000000` alias and image 3 using `0x04000000`, with code starting after the
32-byte header. These mappings are derived from two agreeing metadata sources.

Image 1 contains a Jenkins source path under `wq-adk`; image 3 contains
`ADK-VERSION-v1.3.11.19-Release` and `FW-VERSION-v1.0.3.127-jhv3-Release`.
Image 2 contains `xtensa_intr.c` and HiFi/audio DSP messages. WuQi's
[official WQ7033 overview](https://www.wuqi-micro.com/Public/Uploads/uploadfile2/files/20230522/WQ7033EN.pdf)
documents a mixed RISC-V/HiFi DSP design consistent with this evidence.
The exact silicon part is **not** established by this match.

## Useful native plugin lead

The application body contains `gm_plugin_host_app.c`, `gm_plugin`, `plugin_flash`
and a capability JSON format at body offset `0x1a5694`. It names package format,
ABI, LZ4 block compression, chunk size, streamed install, flash XIP, cache resume,
single SPP link, capacity/runtime queries, display properties and capabilities.
The string is a strong lead for an existing native plugin installer/runtime.
Static strings alone do not establish the query opcode, ABI, reachability or
permission requirements. Trace references from `bt_data_handler.c` before use.
Relevant strings and file offsets are in `analysis/firmware-feature-strings.txt`.

## Reproduction and limits

```sh
python3 scripts/memomind_ota.py inspect captures/firmware/ota-1.0.3.127-jhv3_release.bin
python3 scripts/memomind_ota.py extract captures/firmware/ota-1.0.3.127-jhv3_release.bin /tmp/new-memomind-extraction
python3 -m unittest discover -s scripts -p test_memomind_ota.py
```

The parser validates all checksum layers, all decompression boundaries and all
component/partition joins. The repacker preserves uninterpreted header fields
and all unchanged compressed streams. An unchanged repack is byte-identical to
stock. Optional same-length body replacements require the exact source hash;
they update the component body CRC, compressed lengths and all container CRCs,
then parse the result again. This is an offline construction capability only.
No modified artifact was sent to the glasses, and no boot/security enforcement
claim is made. Resizing, flash-map changes and version changes are unsupported.
