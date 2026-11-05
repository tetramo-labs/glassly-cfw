# Revision 13: default text at the G2's size

On the MemoMind dashboard the bottoms of text lines were cut off. The phone lays
default text out for the Even G2's builtin font (20 px glyphs, 24–27 px rows:
`LINE_H` 24 and `CAL_LINE_H` 27 in the dashboard, 25 px in the MemoMind display
profile) and the mirror draws it with the 20 px system font, but the MemoMind
scene draws TEXT_INLINE with the glasses' default resource font, a 34 px line
with its baseline 7 px up (`analysis/ghidra/font-adapter/report.md`). The
descenders of every line fell below its clip box. The glasses carry no smaller
Latin face (default 34/7, large 41/9, a 27/9 1-bit fallback of unknown coverage).

## Change (`runtime/graphics/native_text.c`, `native_text.h`)

- `mm_native_text_api` gains `scale_num`/`scale_den`; the firmware API draws at
  `MM_NATIVE_TEXT_SCALE_NUM/DEN` = 4/5 (`native_text.h`). 34 → 27 px line,
  baseline 7 → 22 px down from the line top: the G2 builtin font's metrics.
- Glyph boxes, offsets, advances and the baseline scale; the cursor keeps 1/den
  px so advances do not drift along a line; control shifts (bytes 1..31) stay in
  panel pixels, as the phone encodes them.
- Each output pixel is the rounded mean of a 2×2 sample of the glyph box
  (`((4·o+1)·box)/(4·out)` and `((4·o+3)·box)/(4·out)`); the transparent option
  skips a zero mean. At 1/1 (or 0/0, the host tests' zero-initialised API) the
  samples coincide and the adapter is the previous one bit for bit, which the
  pinned G2 differential (`run_text_command_tests.py`, 963 reference cases)
  checks.
- `test_native_text.c` gains `scaled`: 2/3 of the 3×2 fixture glyph, inverse,
  a control shift, a negative offset clipped at the panel edge, the fallback
  font's baseline, and 1/1 = unscaled.
- `tests/rv32/scene_runtime_emulator_test.py` derives the mock glyph's scaled
  pixels (`scaled_glyph`, `glyph_top`, `glyph_left`) and both it and
  `text_command_runtime_emulator_test.py` check the actual RV32 adapter against
  them: 3×2 at 4/5 is `{(0,0):3,(1,0):8,(0,1):13,(1,1):8}` at the line's y.

## Phone side (glassly)

`MemoMindOneRenderer` sets the scene's inline row pitch to the profile's 25 px
(it was the G2CfwScene default, 27), so rows land where the engine wrapped them.
The mirror is unchanged: 20 px system font, 25 px rows.

## Build and evidence

- `build-13-01/build.json`: blob `ebb6ec0e8c0b57b8dacad70891027f8d9ac460f34873f047433c98f2f3a63122`,
  94,288 bytes (V12: 94,000), `linker_relaxation: true`, `cfw_revision: 13`.
- `image-13-01/manifest.json`: image `5c638151d3a29d7847e7e8cfbdcc3362648cf3c4185c61a054f79b73aef9a1de`,
  2,249,152 bytes, streams 1/2/4/5/6 byte-identical to V12; container header
  `547a16092929877521ca07a9a341b02703c5d7a6bc2ee7512f9d89bc102d2803`; app header
  `ab7f6e4e131582cd4c9e5ec5747724f2353f5fdeac1d4f552ec860b5684e1904`.
- `boot-selector-13.json`: first-run boot selector passes on the new build.
- Host: `run_native_text_tests.py` and `run_text_command_tests.py` pass;
  emulator: `scene_runtime_emulator_test.py` 8/8 and
  `text_command_runtime_emulator_test.py` 5/5 through `run_rebuilt.py` on fresh
  `--scene-session` and mode-15 ladder builds.
- `regression-13-02/`: `tests/run_tests.py` with `--demos-dependencies`/`--g2-media` on `~/dev/glassly-g2-cfw` (the G2 checkout was renamed from `~/dev/g2flash` on 2026-11-05; the suite defaults to the new path since the follow-up commit); the rect-copy ladder rung now links with `--relax` like the rungs above it, since the adapter put it 160 bytes over its 64 KiB bound (see `checkpoint.json`).
- Mac tool catalog: `text-scale-001`. Not flashed; the Mac cannot reach the
  glasses (`RFCOMM SDP timed out` since the V12 attempt) and no hardware pixel
  check has been made. Expected on the glasses: dashboard lines the size of the
  G2's, no clipped descenders. The 2×2 mean of 2-bit coverage gives 4-bit output;
  whether the result reads as clean as the native renderer is unverified.
