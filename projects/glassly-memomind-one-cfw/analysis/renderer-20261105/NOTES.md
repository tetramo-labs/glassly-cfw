# Revision 12: partial scene renders

The phone-side fixes of 2026-11-05 left the MemoMind dashboard slow on iOS: a
clock tick or a tween frame cost the glasses as much as a cold frame, because
`cfw_scene_render` cleared and redrew the whole 600x350 canvas on every SHOW and
every animation tick. `tests/rv32/scene_render_benchmark.py` (new) replays the
iOS renderer's dashboard commands (`tests/rv32/fixtures/dashboard-scene-commands.json`)
through the linked runtime in the RV32 emulator and attributes instructions to
functions; `benchmark-v11.json` is the baseline.

## Renderer (shared scene core, G2 CFW revision 51)

The change is made in `~/dev/g2flash` (`e889569`, pushed to `tetramo/main`) and
regenerated into `runtime/portable` by `prepare_scene_port.py`, so both targets
run the same code:

- Every active object remembers the box its last render may have touched
  (`cfw_object.drawn`, `CFW_DRAW_VALID|DIRTY`). A render clears and redraws the
  union of the boxes of objects that changed (ops, PUT, re-assert, tween/rotation
  ticks, asset replacement), arrived, left, or moved behind an object they used to
  precede in the paint order; every object overlapping that box is drawn clipped
  to a view of it and the box is what the panel receives.
- Bounds come from the record: geometry from the parameter masks (+stroke),
  images from the asset header, inline text from its box plus the native font's
  reach above/left, cached-font strings from the glyph headers. Paths, rotated
  shapes and built-in strings without a box redraw everything, as do a new
  background, a raster takeover, HIDE and an invalidated shadow.
- `cfw_raster_clear` clears a view narrower than its stride row by row; the box
  and rotation helpers copy fields (the freestanding build has no memcpy).
- `shapes_host_test.c` gains `test_partial_render` (23 CHECKs; the reported
  rectangle, untouched pixels across move/arrival/departure/HIDE/reopen/tween).

## MemoMind-only speedups

- `scene_assets_external.inc`: resident images and glyphs are drawn from their
  2-byte header (`mm_external_image_head`); the token-by-token validation stays at
  commit (`mm_external_content`). The render loop stops at the last pixel.
- `scene_store.c`: a cursor read served from the 256-byte window skips the
  per-read `valid`/`data_alias` checks; both run when the window is filled.
- `scene.c`: `mm_scene_memcpy` copies words (volatile, no memcpy idiom); the
  45 KiB rollback snapshot was 65% of a clock tick.
- `compile_memomind_graphics.py --relax`: the linker shortens calls and jumps
  (`-mno-relax` dropped, `--relax`), with an assertion that the disassembly uses
  no `gp`. 98,480 -> 94,000 bytes in the 96 KiB region. `scene.c` is `-Os` from
  the diagnostic-commands rung up so the 64 KiB ladder builds still fit.

## Emulator instruction counts (dashboard fixture, V11 -> V12)

| step | V11 | V12 |
|---|---|---|
| cold open: RESET | 687,310 | 703,462 |
| cold open: PUT fonts (387 B) | 409,310 | 169,117 |
| cold open: PUT mono font (8185 B) | 476,710 | 252,292 |
| cold open: PUT icons+objects (288 B) | 1,733,256 | 1,077,928 |
| cold open: SHOW (608 B) | 3,476,637 | 2,620,590 |
| clock tick SHOW (149 B) | 3,400,384 | 249,089 |
| tween SHOW (165 B) | 3,401,810 | 372,387 |
| HIDE | 542,894 | 543,543 |
| reopen SHOW (171 B) | 3,393,563 | 2,495,595 |

Native fonts, flash and LVGL are mocked, so these compare the runtime's own work;
they are not times on the glasses. Animation ticks after the tween still execute
236 instructions in this harness (the display timer does not fire there; unchanged
from V11, not investigated).

## Build and evidence

- `build-12-05/build.json`: blob `48323d0c77fdc3ed4bb8deb80fdfc2db32699add2592e8ee15dcf3ce8753e17a`,
  94,000 bytes, `linker_relaxation: true`, max frame 512 B, no undefined symbols.
- `image-12-05/manifest.json`: image `fc6c4d1f14bdc1d04e610b25b80140d7e2b82375cf57b3f34b21ae54fd1df31c`,
  2,248,988 bytes; expected app header `1a522f71f4eacee1c76aa629240f7e292969102b28daa0e0058735667d4e891b`.
- `boot-selector-12.json`: first-run boot selector test passed on the build.
- `regression-12-05/report.json`: the full offline suite (see checkpoint.json).
- Mac tool: `partial-render-001` added to the catalog (`FirmwareImage.swift`);
  `swift test` OTA/protocol suites pass (52 tests).
- Test pins moved with the layout: undo allocation 46,756 -> 48,824 bytes
  (`cfw_undo` base 45,468 -> 47,536), store fault sweep `render_faults=13`,
  inventory assertion sites 746 -> 769 / 622 -> 645.

## Flash and boot

See checkpoint.json. Physical display behaviour on the phone is user-confirmed
separately; this directory records the Mac transfer and header readback only.
