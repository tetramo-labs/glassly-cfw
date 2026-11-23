# GLASSLYCFW/12

Built-in text, head events from the detector and an accelerometer stream, on
top of GLASSLYCFW/11. Built and verified offline; not flashed or physically
accepted.

## Runtime changes

- Mode 15 (standalone and as a bundle segment) and TEXT_INLINE / TEXT shapes
  draw in the stock UI's face, LVGL Montserrat 16 (`0x0431ee44`, 4 bpp, 18 px
  line, baseline 3), through the font's own `get_glyph_dsc` (`0x04243e8a`) and
  its bitmaps in place. See "Built-in text" in [runtime.md](runtime.md).
- Coverage: U+0020..U+007E, U+00B0, U+2022 (and LVGL's symbol icons). A string
  with anything else, or malformed UTF-8, draws nothing; mode 15 answers
  status 1 and counts as `rejected`.
- No kerning: each glyph advances by its own width rounded to whole pixels,
  the numbers the Glassly App wraps with.
- Identity: `scene.text` is true and `scene.modes` lists 15. The app sends
  text inline only when `scene.text` is true; revision 11 and older keep the
  phone raster.

- Head-up and head-down go to the phone from the accelerometer detector
  (hook `head-event`, `0x0422c7c8`) under the input or display lease, before
  the stock HUD flag and screen mask that kept most stock screens from making
  0x86 at all. The stock copies the dispatcher sees are swallowed, not
  forwarded, so each event arrives once as `7e/26 [00][86|87][00]`.
- `7e/2a [01|00]` leases accelerometer samples for 90 s; each FIFO drain
  (hook `imu-batch`, `0x0422c5e0`) arrives as `7e/2b [00][batch u16]
  [overruns][count][ms u32][count x (x, y, z int16 LE)]`, 8196 counts per g,
  about 26 a second, right arm only. While leased the stillness time is
  zeroed so the sensor never enters wake-on-motion.

`runtime/nimo/text.c` adds 1,350 bytes; with the head and IMU code the runtime
is 46,135 of 83,488 bytes (37,353 free). Static UI frame chains stay at 2,192 B; the emulator measured
1,664 B for `nimo_ui_scene` with the text steps.

## Matching app changes

The Glassly App's NIMO drivers (iOS and Android) send default and builtin
labels as TEXT_INLINE objects when the identity reports `scene.text`, on 18 px
rows, and the engine wraps them with the face's measured advances
(`NIMO_CFW_TEXT_PROFILE`). Text the face lacks is still drawn by the phone.
Both drivers take the IMU lease while a miniapp subscribes to accelerometer
data, renew it with the input lease, and publish each sample as an
`accel_event` in g (raw sensor axes).

## Verification

```sh
python3 tests/run_tests.py --revision 12 --g2-source <pinned-G2-reference> --output <new-evidence-directory>
```

All six stages passed (G2 reference `e889569fe77775ed5822af6f7e47210f2984f15d`).
Host tests compare mode-15 and TEXT_INLINE output with an independent render
(pen bytes, levels, inversion, UTF-8, clipping, nine refusals, bundles). The
RV32 emulator now maps the stock application image and runs the stock
`get_glyph_dsc` over the real font tables, checks each test line's ink against
the advances read from those tables, and replays `tests/hardware/steps-12.json`
(52 steps) with the canvas checksums of the text scene and the mode-15 line,
and the head and IMU gates against mocked stock calls.

Image and source hashes are in [the manifest](../analysis/cfw12-manifest.json).
The image is 1,960,831 bytes, SHA-256
`cdcc375a756ea9ef5c65feeb1a1fd73919372b658260996076b2dca5ea87be56`.

## Physical acceptance still required

Steps 31-37 of `steps-12.json`: the text scene on both eyes (legibility at the
panel's size, descenders, same height on both eyes), the canvas checksums
(they prove the stock tables and glyph call behave as the emulator ran them),
the mode-15 line, and the refused string leaving the glasses running. Then the
Glassly App's labels on the glasses. Steps 45-52: head-up and head-down from
the detector with the stock screen anywhere, accelerometer batches that read
about 8196 on the gravity axis at rest, and the axis orientation against the
G2's for `session.imu`.
