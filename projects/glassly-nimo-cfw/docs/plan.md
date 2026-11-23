# Plan

Goal: a Glassly custom firmware for the NIMO glasses with the capabilities the
G2 and MemoMind One CFWs give the Glassly App (retained scenes, vector shapes,
cached assets, firmware-side animation, sensor and notification access),
installed and reverted from the Glassly App. Phase 0 needs no firmware change
and ships first.

## Phase 0 — stock Dynamic Layout renderer (glassly repo)

- [x] Scene-frame encoder for the V1 frame on iOS and Android, with golden
      tests from the vendor guide (`NimoDynamicLayout*`).
- [x] Driver integration: launch/exit the 0xFD page, full-replace updates,
      last-wins coalescing, ACK-driven `scene_frame_presented`, firmware gate
      (≥ 0.1.1.1), ASR text fallback below it.
- [x] Engine: 500×220 positioned canvas, shapes rect/circle/line, 16 gray
      levels, a `NIMO` display profile for host text layout (glyph advances
      approximate until measured from the vendor font).
- [ ] Hardware pass on 0.1.1.1: launch, a rect+label frame, a bitmap frame,
      budget edges, page exit on a native switch, input events on the page.
- [ ] Measure label metrics (line pitch per font size, advances of the 16 px
      face from `JinzisheTongfang-Regular.ttf`) and replace the approximations.

## Phase 1 — OTA path

- [x] OTA framing recovered from the vendor app's update of `Nimo-4026`
      (2026-11-09 HCI capture; `docs/firmware-format.md`): GATT `2001`/`2002`
      in service `7033`, MemoMind envelope and command set.
- [x] One flasher for phone and Mac: `ios/Source/sgcs/NimoOta.swift` in the
      Glassly SDK (`FirmwareFlashable` on the iOS NIMO driver), symlinked into
      `mobile/modules/bluetooth-sdk/tools/nimo-mac` (CoreBluetooth). Tested
      against a simulated device; not yet run against the glasses.
- [x] Mac: CoreBluetooth reaches `7033` over the classic link
      (`retrieveConnectedPeripherals`, 512-byte writes); `nimo-mac check` with
      the 1.1.5.1 GLASSLYCFW/1 image got can-update 3 on 2026-11-09.
- [ ] Android: Kotlin port of the flasher on the NIMO driver.

## Phase 2 — first accepted custom image

- [ ] `GLASSLYCFW/1` (`patches/glasslycfw-1/{0.1.1.1,1.1.5.1}.json`, built by
      `scripts/build_cfw.py`; the glasses now run 1.1.5.1):
      the waiting-for-phone title reads "Glassly CFW running" (English) or
      "Glassly 就绪" (Chinese), and the `FW-VERSION-` build tag carries
      `GLASSLYCFW/1` with the numeric version unchanged. Built and verified
      offline (0.1.1.1 base `3c2be1c5…16cf`, 1.1.5.1 base `6f6e9043…aa5d`;
      7-Zip decodes the repacked stream identically); not yet flashed. Open: whether the updater
      checks anything beyond the CRC layers, and whether `getVersionDetail`
      returns the `FW-VERSION-` string.

## Phase 3 — runtime

Two candidate routes; decide after Phase 2 evidence.

- Appended RV32 runtime in the application partition (204,864 bytes of
  headroom in 0.1.1.1), hooked at the Dynamic Layout update handler, porting
  the MemoMind scene core (`runtime/graphics`) with a NIMO display adapter.
  Known shape, known risks (callback hook, heap, display worker).
- The WASM application runtime that 0.1.1.1 ships (`csdk_*` host API,
  `wasm install`, surfaces). If apps can be installed over BLE, a Glassly WASM
  renderer would need no native patching and could not brick the glasses.
  Needs: the install message format, the host API surface, interpreter speed
  on RV32 for a 500×220 frame.

## Phase 4 — Glassly App integration

- [ ] `FirmwareFlashable` on the NIMO drivers with the stock 0.1.1.1 image
      bundled next to the CFW, so a user can leave the CFW.
- [ ] `hasCustomFirmware` on the NIMO capability profile, CFW classification,
      canvas/vector publication, dashboard eligibility.
