# NIMO OTA container

Both vendor images parse with `scripts/nimo_ota.py`, which validates every
checksum layer and accounts for every byte. This is container evidence only;
it says nothing about what the updater or bootloader accept.

## Layout

The container is the WuQi ADK update format also used by the MemoMind One
(`glassly-memomind-one-cfw/analysis/firmware-format.md`), with two
differences: the outer magic is two zero bytes instead of `ME`, and the
component count is not fixed (4 in 0.1.0.15, 6 in 0.1.1.1 and 1.1.5.1). The
parser derives the row count from the table CRC and the first stream's header,
and finds the partition-metadata row by its flash range (2, 0): 0.1.x images
put it first, 1.1.5.1 fourth.

| Field | Offset | Content |
|---|---:|---|
| Outer magic / profile | 0 | `0000 0201 1001` |
| Payload length | 6 | BE32, file length minus 18 |
| Reserved | 10 | zero |
| Outer CRC32 | 14 | BE32 over bytes 18..EOF |
| Inner magic | 18 | LE32 `0xabcd6543` |
| Inner words | 22, 26, 30 | LE32 `1`, `0x1f` (0.1.0.15) / `0x7f` (0.1.1.1), `0xffffffff`; semantics unknown |
| Stream table | 34 | (N+1) × 16 bytes: unpacked size, packed size, flash start, flash end; one row is the partition metadata, flash range (2, 0) |
| Table CRC32 | 50 + 16N | LE32 over bytes 34 .. 50+16N |
| Streams | 54 + 16N | LZMA-alone (`5d 00 80 00 00`, 32 KiB dictionary) with an explicit LE64 size, one per table row in table order |
| Final CRC32 | EOF − 4 | LE32 over all packed stream bytes |

Each component stream decodes to a 32-byte image header (`0xa4e49a17`, body
length, flags, load address, body CRC32, 0, auxiliary address, 0) followed by
the body. The metadata stream holds a 16-row partition table (type, flash
start, load address, body size, allocation size); every component matches one
row.

## Partition map (shared by both images)

| Type | Flash | Load | Role (inferred) |
|---:|---|---|---|
| 0x30 | `0x010000` | `0x14010020` | Bluetooth/system RISC-V image |
| 0x70 | after 0x30 | `0x26000000` | HiFi DSP image |
| 0x20 | after 0x70 | `0x04xxx020` | Main application RISC-V image (LVGL UI, protocol, OTA) |
| 0x90, 0x91 | `0x42c000`/`0x42d000` (0.1.1.1) | 0 | small data (0x90 carries 1,416 bytes in 0.1.1.1) |
| 0xa0 | next | 0 | 0xb0000 data region, empty in the OTA |
| 0x04 | next | 0 | staging area for the OTA (0x28c000 / 0x24c000) |
| 0xc8 | `0x72a000` (0.1.1.1 only) | 0 | 0xc0000 region, empty in the OTA |
| 0xc4..0xc0 | `0x7ea000`.. | 0 | 8 KiB config slots; 0xc2 and 0xc0 carry data |
| 0x07, 0x08, 0x02, 0x09 | `0x7f4000`.. | 0 | tail slots, empty in the OTA |

Application image placement:

| Image | App flash range | Load | Body | Allocation | Headroom |
|---|---|---|---:|---:|---:|
| 0.1.0.15 | `0x254000..0x4ac000` | `0x04254020` | 2,161,680 | 2,457,600 | 295,888 |
| 0.1.1.1 | `0x1b4000..0x42c000` | `0x041b4020` | 2,383,776 | 2,588,672 | 204,864 |
| 1.1.5.1 | `0x1b4000..0x42c000` | `0x041b4020` | 2,505,140 | 2,588,672 | 83,532 |

1.1.5.1 (2026-10-27, commit 8e6f7a, built from `new_arch_0827/focus01-glass-dev`)
is the vendor app's current update; it was rebuilt byte for byte from the
2026-11-09 capture. It keeps the 0.1.1.1 partition map and the WASM runtime
but has no Dynamic Layout page.

The 0.1.1.1 layout shrank the Bluetooth and DSP partitions and grew the
application partition; the two images are not interchangeable at the partition
level, so a CFW must be built against the exact base it targets.

## ISA and platform evidence

Image bodies for the Bluetooth and application partitions start with the same
RV32C reset prologue the MemoMind One uses (`a142 73b0 0230 9302 0008 73b0 4230`:
`li t0,8; csrrc mstatus; addi t0,zero,128; csrrc mie`). The application body
carries:

- WuQi ADK paths (`/builds/adk-internal/bt-service-src/wq-adk/...`) and
  `wq_*.c` drivers (`wq_gatt.c`, `wq_gatts.c`, `wq_ble.c`, `wq_spp.c`,
  `wq_flash.c`, ...).
- LVGL 9.3.0 built from `/home/zgf/code/new_arch/focus01/glass/lvgl/lvgl_9.3.0`;
  the vendor project is called `focus01`.
- OTA: `ota_transport_ble.c`, `ota_transfer_flash_data.c` and `handle_ota_*`
  handlers. The vendor Android app updated `Nimo-4026` from 0.1.0.15 to 1.1.5.1
  on 2026-11-09 (HCI capture in `captures/android-ota-*`) over GATT on the
  classic ATT bearer (L2CAP PSM 31, link MTU 517): requests are
  write-without-response to `2001` (handle 0x10, up to 509 bytes), replies are
  notifications on `2002` (handle 0x12, CCCD 0x13), both in service `7033`
  with the data channel (`2021`/`2022`). Frames use the MemoMind envelope
  `70 07 6e | flags | cmd | len BE16 | body | 33`; requests are `C0` with
  `sequence + parameters`, replies `00` with `status, sequence, result...`.
  Session: device info `02 ff×4` (records: kind 1 = the container's first four
  bytes, kind 2 = two battery percentages), file offset `e1` → (0, 18),
  can-update `e2` + the 18-byte header → 3, enter update `e3` → offset 18,
  4096-byte blocks, per-chunk CRC (1.5 s, staging erase), blocks `e5` as
  492-byte chunks (`offset BE32 | data | CRC32 BE`, own sequence each; the ack
  to the last chunk names the next block, `0,0` at the end), complete `e6` → 0,
  sync status `e8` → 1 then 0 (the second arm), reset `03 00`. 1.93 MB took
  125 s. The iOS vendor app timed out at device info on the same glasses. From
  the Mac, the RFCOMM OTA service (SDP UUID 0x7034, channel 6) answered device
  info on 2026-11-09 as well; the Glassly flasher uses GATT on every platform.
- 0.1.1.1 only (not 0.1.0.15 or 1.1.5.1): the Dynamic Layout screen (`[DYNAMIC_LAYOUT]`,
  `cli_dynamic_layout`, "V1 Dynamic", preflight/render rejection logs) and a
  WASM application runtime (WAMR-style interpreter strings, `csdk_*` host
  modules: `csdk_h_dash`, `csdk_h_disp`, `csdk_h_render`, `csdk_h_notif`,
  `csdk_h_ota`, `csdk_h_sys`, `csdk_h_time`, `csdk_perm`, `csdk_reg`,
  `csdk_framer`; `installed wasm app='%s' surfaces=%u caps=0x%x`,
  `install msg key=0x%02x`, `wasm: engine up, %u apps mounted`, a mounted
  filesystem with a log volume). Nothing in 0.1.0.15 refers to WASM.

## Reproduce

```sh
python3 scripts/nimo_ota.py inspect captures/firmware/<image>.bin
python3 scripts/nimo_ota.py extract captures/firmware/<image>.bin analysis/extracted/<name>
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

`analysis/container-manifest-*.json` are the inspect reports (hashes and sizes
only) for both vendor images.
