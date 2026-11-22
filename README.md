# NIMO custom firmware investigation

Tooling, analysis and plan for a Glassly custom firmware (CFW) on the NIMO
smart glasses (BitFantasy, vendor project `focus01`). The sibling projects are
`glassly-g2-cfw` (Even Realities G2, Thumb) and `glassly-memomind-one-cfw`
(MemoMind One, WuQi RISC-V); the NIMO runs the same WuQi ADK platform as the
MemoMind One, so that project's container tooling and appended-runtime
approach are the starting point here.

Nimo-4026 runs GLASSLYCFW/10, flashed from the Glassly repo's
`mobile/modules/bluetooth-sdk/tools/nimo-mac` harness. Boot verification and
the full 35-step hardware suite passed, including physical touch input, and the
wearer confirmed both eyes look correct. Live iPhone notification delivery remains
unverified. See [the flash record](docs/hardware-cfw10-2026-11-16.md) and
`docs/runtime.md` for the revision details. The claims below are offline
evidence from the two vendor OTA images.

GLASSLYCFW/11 is prepared and verified offline, with matching app fixes; see
[the v11 release record](docs/release-cfw11.md). It has not been flashed.
GLASSLYCFW/12 adds built-in text in the stock font
([release record](docs/release-cfw12.md)); also offline only.
GLASSLYCFW/13 adds ambient light readings from the left arm's sensor
([release record](docs/release-cfw13.md)); offline only as well.

## Established (2026-11-08)

- **Container.** Both vendor images (0.1.0.15 of 2026-07-24 and 0.1.1.1
  "dynamic-v1" of 2026-08-27) are WuQi ADK update containers: 18-byte outer
  envelope, `0xabcd6543` inner header, a component table (4 rows in 0.1.0.15,
  6 in 0.1.1.1), LZMA-alone streams and three CRC32 layers.
  `scripts/nimo_ota.py` parses, extracts and repacks them; an unchanged repack
  is byte-identical. See `docs/firmware-format.md`.
- **Platform.** RV32C application and Bluetooth images (same reset prologue
  as the MemoMind One), HiFi DSP image, LVGL 9.3.0 UI, WuQi `wq_*` drivers.
  The application partition has 204,864 bytes of headroom in 0.1.1.1.
- **OTA.** Over BLE GATT (0x2001 write / 0x2002 notify per the vendor SDK),
  with the WuQi command set the MemoMind One uses over RFCOMM (device info,
  can-update, enter update mode, firmware blocks with CRC32, status, sync,
  reboot). The BLE frame envelope is not yet recovered.
- **Dynamic Layout.** 0.1.1.1 ships a phone-drawn page (app 0xFD): lines,
  rectangles, circles, labels and bitmaps on a 500×220 canvas, full replace or
  append, 64 objects per frame. The Glassly App renders scene frames onto it
  without any firmware change. See `docs/stock-dynamic-layout.md`.
- **WASM runtime.** 0.1.1.1 also embeds a WebAssembly application runtime
  with a `csdk_*` host API (display, render, dashboard, notifications, OTA,
  time, permissions, registration), app installation messages and per-app
  surfaces. 0.1.0.15 has none of it. This is a candidate route to a Glassly
  renderer that needs no native patching; see `docs/plan.md`.

## Layout

| Path | Content |
|---|---|
| `scripts/nimo_ota.py` | container inspect / extract / repack (stdlib only) |
| `scripts/test_nimo_ota.py` | synthetic-container tests plus vendor-image roundtrips when the images are present |
| `docs/firmware-format.md` | container, partition map, ISA and module evidence |
| `docs/stock-dynamic-layout.md` | the 0xFD page in our own words and how the Glassly App uses it |
| `docs/plan.md` | phases from the stock renderer to a flashable CFW |
| `docs/vendor-sources.md` | where the proprietary vendor material lives locally |
| `analysis/container-manifest-*.json` | inspect reports (sizes and hashes) for both vendor images |
| `captures/`, `analysis/extracted/` | local only: vendor images and their extracted segments |

## Reproduce

```sh
python3 scripts/nimo_ota.py inspect captures/firmware/ota-0.1.1.1-20260827164351-537cf1-dirty-dynamic-v1.bin
python3 scripts/nimo_ota.py extract captures/firmware/ota-0.1.1.1-20260827164351-537cf1-dirty-dynamic-v1.bin analysis/extracted/dynamic-v1
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

## Licensing

Original project code is MIT (`LICENSE`). The vendor firmware, SDK and
documents are BitFantasy's and are not distributed here. Code later derived
from the G2 or MemoMind CFW keeps its own notices.
