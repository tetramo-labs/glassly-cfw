# Vendor sources (local only, proprietary)

Nothing listed here is committed. Paths are on the development Mac.

| Item | Path | Notes |
|---|---|---|
| Stock OTA 0.1.0.15 (`mentros` build, 2026-07-24) | `~/Downloads/NIMO/ota-0.1.0.15-20260724160441-bd9806-mentros.bin` | 1,936,677 bytes, SHA-256 `8eb058b4…3612`; 4 components, no Dynamic Layout, no WASM runtime |
| Stock OTA 0.1.1.1 (`dynamic-v1`, 2026-08-27) | `~/Downloads/NIMO/new_info_correct_fw/ota-0.1.1.1-20260827164351-537cf1-dirty-dynamic-v1.bin` | 1,857,523 bytes, SHA-256 `5e23c574…e433`; 6 components, Dynamic Layout V1, WASM app runtime |
| Dynamic Layout V1 integration guide (EN) | `~/Downloads/NIMO/new_info_correct_fw/dynamic-layout-app-integration-guide-en.md` | wire format, budgets, status codes, golden frames |
| Dynamic Layout proposal (ZH, PDF, two identical copies) | `~/Downloads/NIMO/NIMO_CANVAS_PROPOSAL.pdf` | earlier draft of the same protocol; language table for labels |
| Mentra's questions to the vendor (2026-07-01) | `~/Downloads/NIMO/Nimo_Dynamic_UI_Protocol_Question & Answer(1).pdf` | layout/res ids, chunking, partial updates |
| Mentra's original firmware proposal (2026-06-16) | `~/Downloads/NIMO/nimofont/Adding MentraOS Support to NIMO (1)_260617_134620.pdf` | the draw/commit protobuf design the vendor did not adopt |
| BitFantasy Flutter SDK (`bitfantasy_glasses_sdk`) | `~/Downloads/NIMO/current_nimo_sdk/`, `~/Downloads/NIMO/NEW_sdk_code_sample.zip` | proprietary; `docs/protocol/*.md` document the 0xBF transport, image and audio protocols; the OTA plugin `flutter_ota_upgrade` is referenced but not included |
| Connectivity notes (2026-09-03) | `~/Downloads/NIMO/NEW_sdk_sample_code_mesasge.txt` | one GATT channel on both platforms, BR/EDR ATT bearer, budgets |
| Vendor font | `~/Downloads/NIMO/nimofont/JinzisheTongfang-Regular.ttf` (+ `.ttx`) | the glasses' label face; source for exact glyph advances |
| Flashing screen hint | `~/Downloads/NIMO/content_sent_via_wechat/flash_custom_firmware.png` | tap the device-info title five times in the vendor app to reach its firmware flashing screen |

The copies under `captures/firmware/` are gitignored working copies of the two
OTA images.
