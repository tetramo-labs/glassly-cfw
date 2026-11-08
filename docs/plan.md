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

- [ ] Recover the BLE OTA framing: Ghidra on the 0.1.1.1 application body
      (`handle_ota_*`, `ota_transport_ble.c`), cross-checked against the
      MemoMind envelope (`70 07 6e | flags | cmd | len16 | payload | 33`) and
      the vendor SDK's `OtaController` step order (device info → file offset →
      can-update → enter update mode → blocks → complete → sync → reset).
- [ ] If a NIMO device is available: capture one vendor-app OTA (Android HCI
      snoop) to confirm the framing and the resume/offset behaviour.
- [ ] Offline flasher core (Python, then Swift/Kotlin for the Glassly App) that
      replays a recorded session byte for byte before any live mode.

## Phase 2 — first accepted custom image

- [ ] Same-length text patch of a visible string in the 0.1.1.1 application
      body (the MemoMind "first text patch" pattern), repacked with
      `nimo_ota.py`, to learn whether the updater checks anything beyond the
      CRC layers. Boot and visual confirmation recorded under `analysis/`.
- [ ] Version-string patch so the glasses report `GLASSLYCFW/N` through
      `getVersionDetail`; the Glassly App classifies on that string.

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
