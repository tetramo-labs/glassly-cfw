# NIMO OTA container

Both vendor images parse with `scripts/nimo_ota.py`, which validates every
checksum layer and accounts for every byte. This is container evidence only;
it says nothing about what the updater or bootloader accept.

## Layout

The container is the WuQi ADK update format also used by the MemoMind One
(`glassly-memomind-one-cfw/analysis/firmware-format.md`), with two
differences: the outer magic is two zero bytes instead of `ME`, and the
component count is not fixed (4 in 0.1.0.15, 6 in 0.1.1.1). The parser derives
the count from the table CRC and the metadata stream that follows it.

| Field | Offset | Content |
|---|---:|---|
| Outer magic / profile | 0 | `0000 0201 1001` |
| Payload length | 6 | BE32, file length minus 18 |
| Reserved | 10 | zero |
| Outer CRC32 | 14 | BE32 over bytes 18..EOF |
| Inner magic | 18 | LE32 `0xabcd6543` |
| Inner words | 22, 26, 30 | LE32 `1`, `0x1f` (0.1.0.15) / `0x7f` (0.1.1.1), `0xffffffff`; semantics unknown |
| Metadata sizes | 34, 38 | LE32 unpacked / packed size of the partition-metadata stream |
| Words | 42, 46 | LE32 `2`, `0` |
| Component table | 50 | N × 16 bytes: unpacked size, packed size, flash start, flash end |
| Table CRC32 | 50 + 16N | LE32 over bytes 34 .. 50+16N |
| Streams | 54 + 16N | LZMA-alone (`5d 00 80 00 00`, 32 KiB dictionary) with an explicit LE64 size: metadata first, then one per table row |
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
- OTA over BLE: `ota_transport_ble.c`, `ota_transfer_flash_data.c` and
  `handle_ota_*` handlers (device info, inquiry-if-can-update, enter update
  mode, firmware block with CRC and offset checks, refresh firmware status,
  sync state, reboot). The command set matches the MemoMind One's RFCOMM OTA
  (`02, e1, e2, e3, e5, e6, 03`); the GATT characteristics are 0x2001 (write)
  and 0x2002 (notify) per the vendor SDK. The glasses also advertise the
  MemoMind-style RFCOMM OTA service (SDP UUID 0x7034, channel 6) and the
  recording service (0x2024 "COM6", channel 4); the 0x7033 data channel is
  GATT over the classic ATT bearer (L2CAP PSM 31, handles 1..19), which macOS
  does not let user space open. On 2026-11-09 the Mac tool opened RFCOMM 6 on
  `Nimo-4026` and the read-only attach (`70 07 6e c0 02 ...`) was answered
  with the MemoMind reply layout: field 1 = `00 00 02 01`, the first four bytes
  of the NIMO OTA container, plus fields 0 (`00 0F 00 0F 02`), 2 (`bc`), 3, 4
  and 5. The NIMO OTA transport is therefore the WuQi RFCOMM protocol the
  MemoMind flasher already speaks; the BLE 0x2001/0x2002 path is an
  alternative, not a requirement. Channel opens only succeed on a fresh
  baseband link and are intermittent; a half-open session from an earlier host
  run answers nothing until the link drops.
- 0.1.1.1 only: the Dynamic Layout screen (`[DYNAMIC_LAYOUT]`,
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
