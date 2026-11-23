# Stock Dynamic Layout (app 0xFD) in our own words

Firmware 0.1.1.1 adds a screen the phone can draw into without any custom
firmware. The Glassly App uses it as the NIMO scene renderer
(`NimoDynamicLayout.swift` / `NimoDynamicLayout.kt` in the glassly repo); the
vendor guide listed in `docs/vendor-sources.md` is authoritative for the bytes.

## Lifecycle

Everything travels on the existing 0x7033 channel (write 0x2021, notify
0x2022) inside the 0xBF transport frames and `cmd 0x07` control commands:

| Step | cmd/key | App payload | Reply payload |
|---|---|---|---|
| Launch | `07/01` | `FD 00` | `status FD` (and an app-state report `FD 01`) |
| Update | `07/04` | `FD 00 00 00` + V1 frame | `status FD 00 00 00` (five bytes, or `status` alone on early rejection) |
| Exit | `07/03` | `FD` | `status FD` (and an app-state report `FD 03`) |

Launch needs the glasses' TWS link and the phone GATT path up, otherwise
status 7. Any native page switch destroys the dynamic page and reports
`FD 03`; after that (or a reconnect) launch again and push one full frame.
Update status 0 means the frame passed validation and was queued; rendering
is asynchronous and there is no render acknowledgement. There is exactly one
dynamic page per device, with no busy reply, so one owner must serialize.

## V1 frame

`object_count u16 | clear_all u8 | objects...`, little-endian. `clear_all=1`
replaces the frame atomically (staged, failure keeps the previous frame);
`clear_all=0` appends. Objects paint in wire order, later over earlier. Each
object is `type u8 | payload_len u16 | payload`.

| Type | Payload | Notes |
|---|---|---|
| 0 line | `x0 y0 x1 y1 (u16) stroke u8 (1..32) intensity u8` | points inside 500×220 |
| 1 rectangle | `x y w h (u16) stroke u8 (0..32) radius u8 intensity u8 filled u8` | box inside the canvas, w,h > 0 |
| 2 circle | `cx cy r (u16) stroke u8 intensity u8 filled u8` | whole circle inside the canvas |
| 3 label | `x y w h (u16) language u16 font u8 intensity u8 text_len u16 text` | UTF-8, 1..2048 bytes, no NUL; wraps inside the box; font 0=16 px (full repertoire), 1=20, 2=24, 3=32 (ASCII only beyond a few CJK units) |
| 4 bitmap | `x y w h stream_id total_chunks bitmap_len (u16) image packet` | stream_id 0, total_chunks 1; the image packet is the vendor 15-byte header + body |

Image packet: `id u8 | w u16 | h u16 | bpp u8 | compression u8 | original u32 | compressed u32 | body`.
Raw bodies are 8 bpp only; 2 bpp bodies must be RLE (`0x03`) or zlib with
header (`0x07`). 2 bpp packs four pixels per byte, MSB first, `00` dark →
`11` brightest.

Budgets, enforced on the phone before sending: 64 objects, 2048 bytes per
label, 8192 text bytes and 110,000 bitmap pixels per page, 12,280 V1 bytes per
update (12,288 reassembled including the 4-byte app header, minus the 4-byte
`FD 00 00 00` envelope). Fragments carry their own 0xBF header, CRC and index
(1, 2, ..., then 0 for the last) and must complete within 50 s.

Status codes: 0 accepted, 1 generic failure, 2 timeout, 5 unsupported, 6 bad
parameter, 7 not ready, 8 device locked.

## Input

While the dynamic page is up, the glasses report taps and long presses as
input events (`06/01`, payload `00 event`): 0x03/0x05 right tap/long press,
0x13/0x15 left. Head up/down are reported by the stock firmware as 0x01/0x02.

## What the Glassly App does with it

The driver treats the page as a full-replace canvas: every scene frame becomes
one `clear_all=1` update, last-wins coalesced while a launch or update is in
flight. Text, rectangles, circles, lines and images map one to one; arcs,
pies, triangles, quads, beziers and SVG paths are skipped until a CFW draws
them. Element gray levels 0..15 become intensity 0..255. The feature is gated
on the reported firmware version being at least 0.1.1.1; older firmware keeps
the ASR note page text fallback.

## Open questions for the vendor

- Whether the 500×220 canvas can grow to the 540×280 panel, and what the
  label line pitch is at each font size (needed for exact host wrapping).
- Whether partial updates addressed by object id (the `0x07/0x05` idea from the
  2026-07 questions) are planned; V1 has only replace and append.
- The exact glyph repertoire of fonts 1..3 and whether the 16 px face covers
  the full `JinzisheTongfang` set shipped in `nimofont/`.
