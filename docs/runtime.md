# NIMO runtime (GLASSLYCFW/3 and later)

Target: the mainline 1.1.5.1 application (`ota-1.1.5.1-20261027111705-8e6f7a`),
the firmware Nimo-4026 runs. Same approach as the MemoMind CFW: a freestanding
RV32 blob appended to the application partition, entered from byte-guarded
patches of stock call sites, binding stock functions by address.

## Memory map (from the startup code)

| What | Address | Notes |
|---|---|---|
| App XIP body | `0x041b4020`..`0x044179d4` | load base; stock body 2,505,140 B |
| Runtime blob | `0x044179e0`.. | 16-aligned after the body; room to `0x0442c000` = 83,488 B |
| RAM code copy | `0x02000000`..`0x0200fa3c` | from XIP `0x041b4084` (memcpy `0x02000000`, memset `0x020000da`) |
| `.data` | `0x0200fa40`..`0x02011b24` | from XIP `0x04415898` |
| `gp` | `0x02011b20` | set at `0x041b403e` |
| `.bss` | `0x02011bd0`..`0x0209be74` | zeroed by init `0x041c3b4e` |
| Stack top | `0x02100000` | |

Ghidra: `scripts/ghidra-local.sh analysis/ghidra nimo-1.1.5.1 ...` (project in
`analysis/ghidra/`, raw import at the load base, `MapStartupCopies.java`
adds the copies and gp). `ExportInventory.java` writes `functions.tsv` and
`strings.tsv`; `ExportFunctions.java` and `CallSites.java` decompile and list
call sites.

## Command channel

The phone's 0xBF requests (`[cmd][key][len LE16][payload]` on `2021`) reach the
router `0x0426dfa8(cmd, key, payload, len)`. A route table at `0x04377c88`
(74 rows `[cmd][key|0xff][2][family u32]`) maps them to handler families held
in RAM at `0x02084250`; anything absent is family 8 and answered
NOT_SUPPORTED (status 5) through `0x0426df70`. Stock uses cmds 02 03 04 05 07
08 09 0a (06 for reports). Glassly uses **0x7E**.

Hook `router-unrouted` (`0x0426e02e`, witness `378637044a87d287`) jumps to
`glassly_router_gate` with `s1=cmd s2=key s5=payload s4=len`; the gate calls
`glassly_command` and either leaves through the router epilogue (`0x0426e112`)
or replays the replaced bytes and continues the stock unrouted path at
`0x0426e036`.

Replies: `send_response(cmd, key, data, len)` at `0x0426e2d6`; `data[0]` is
the status. `build_response` frames into a 608-byte stack buffer, so keep a
reply under ~590 bytes. The router runs on both arms; `send_response` skips on
the slave (`0x041fc24e` returns nonzero on the master).

## Build

`python3 -I scripts/build_runtime.py <stock 1.1.5.1 OTA> <revision>` applies the
string edits (`patches/glasslycfw-2/1.1.5.1.json`, version tag set to
`GLASSLYCFW/<revision>`), compiles `runtime/nimo/` with xPack GCC 15.2
(`rv32imac`/`ilp32`, freestanding, no writable statics), patches the hooks,
appends the blob with `nimo_ota.replace_body`, and writes
`captures/firmware/ota-1.1.5.1-glasslycfw-<revision>.bin` plus
`captures/build/glasslycfw-<revision>/build.json`. Flash with
`mobile/modules/bluetooth-sdk/tools/nimo-mac` in the glassly repo.

## Commands (0x7E)

| Key | Request | Reply |
|---|---|---|
| 0x01 | — | `{"version":"GLASSLYCFW/N","platform":"nimo","base":"1.1.5.1","arm":"master"}` |
| 0x02 | bytes | the same bytes (echo) |
| other | — | status 5 |

## Display

- Panel `iv00654dsf` (descriptor `0x0430c3fc`, ops `0x0430c408`): 540×280,
  4-bit gray, 270-byte rows, high nibble = even x. Each arm drives its own
  panel; orientation comes from the left flag (`0x02011b18`) and mirror flag
  (`0x020121bd`) through panel registers 0x17/0x36, not from the framebuffer.
- Stock framebuffers: `0x0202f064` and `+0x12750` (75,600 B each), back index
  `0x020120fb`, dirty rows `0x020120f4`/`0x020120ee`, pending `0x020120ec`.
  Frame task `0x041fd3e2` flushes under the display mutex.
- Row flush `0x04200db2(fb, x, row0, w, nrows)`: x/w ignored, sends
  `fb + row0*270` for `nrows` rows over SPI DMA, blocking; 0 = sent, 1 = panel
  down (`0x020121be`). Take the display mutex (`0x041fc706()`, then
  `os_lock 0x0200ed06` / `os_unlock 0x0200ed7e`) around it.
- LVGL 9.3: logical display **500×220** (physical 540×280), color format L8,
  one 27,500-byte partial buffer at `0x02026798`; flush cb `0x041f7958`
  converts L8 to 4-bit and offsets into the framebuffer (x `0x02011976`,
  y `0x02011978`). Default font `0x0431ee44` (line height 18).

## UI task

- `gui_post_async(fn, arg)` `0x04206cf2` runs `fn(arg)` on the UI task (48-slot
  ring, no copy, nonzero when queued); `0x04206d96` is the 8-slot priority ring.
- Heap: `malloc 0x041fa772`, `free 0x041fa784`.
- UI messages: `post_ui_msg 0x04206964(id, payload, len, ...)` (copies ≤ 0x180 B,
  coalesces repeats of the tail id); dispatcher `0x04208dd2`, ids 0x81..0xd7.

## LVGL entry points (selection; full table in analysis/ghidra/lvgl-api/)

lv_screen_active `0x0424143c`, lv_layer_top `0x04241452`, lv_obj_create
`0x0422fde2`, lv_obj_delete `0x04239418`, lv_obj_set_pos `0x04232c74`,
lv_obj_set_size `0x04232f4c`, lv_obj_add_flag `0x04230d74`, lv_obj_remove_flag
`0x0423050e`, lv_obj_move_to_index `0x04239a06`, lv_obj_invalidate
`0x04233f3a`, lv_label_create `0x0425ac90`, lv_label_set_text `0x0425ba4a`,
lv_image_create `0x04254938`, lv_image_set_src `0x0425525a`, lv_timer_create
`0x0423f7f8`, lv_timer_delete `0x0423f89e`, lv_refr_now `0x0423b3f8`,
lv_malloc `0x04241a46`, lv_free `0x04241a98`. Style setters (prop ids from the
9.3 enum, not string-pinned): bg_color `0x04238830`, bg_opa `0x04238856`,
text_color `0x042388ea`, text_font `0x04238928`, border_width `0x042388a8`,
radius `0x04238980`, pad_top/bottom/left/right `0x0423877c`/`90`/`a4`/`b8`.

## Display ownership (planned for GLASSLYCFW/5; static analysis, not yet on hardware)

- Runtime RAM: carve 4 KB off the start of the only heap region. Heap table
  entry `0x04414f5c` = `{0x0209be74, 0x6314c, caps 2}` → `{0x0209ce74, 0x6214c, 2}`,
  and widen the boot bss clear at `0x041c3b96` (`lui a5,0x209c` → `0x209d`), so
  `0x0209be74..0x0209ce74` is zeroed every boot and untouched by stock code.
- Gate the single panel write in the frame task: call site `0x041fd63c`
  (witness `4a87 8149 9c4b 8297` = `c.mv a4,s2; c.li s3,0; c.lw a5,0x10(a5);
  c.jalr a5`, return `0x041fd644`). While owned, return 0 without writing; all
  pending/dirty/token bookkeeping still runs. Release: clear the flag, call
  `0x041fe71a()` (all rows dirty), then `lv_obj_invalidate(lv_screen_active())`.
- Auto-off: about 3 ticks of a black stock canvas turns the display off. Each
  owned frame (and at least every second) set `*(u8*)0x02011a3a = 1` and
  `*(u8*)0x02012a38 = 0`; `0x04268164(2)` also cancels an armed off. Display
  state `0x02011fa6` (1 = on); off routine `0x041f6c4a`, on `0x041f6d06`.
- Brightness 0..32: non-persistent `0x041fec90(level)` (takes the display mutex).

## Code space beyond the app partition (static analysis)

- The whole 8 MB flash is XIP-mapped at `0x04000000 + offset`. The updater
  writes every container row to its own flash range (rows carry start/end) and
  the app-side check does not restrict which partitions rows target.
- Best: the log filesystem partition 0xa0 (`0x42e000`, 704 KB, littlefs
  "wq7036a_log_fs", logs only). Ship a 0xa0 component at `0x42e000` (body XIP
  `0x0442e020`) and patch the log port constants (XIP `0x044176e0` base,
  `0x044176e4` block count, from 0x42e000/0xb0 to e.g. 0x4ae000/0x30); the
  log volume reformats once. Unproven: execution from outside the app range,
  and the applier accepting the new row.
- Fallbacks: the staging tail above the OTA image (erased by later updates),
  neutralising the WASM interpreter (~75 KB, entry `0x042812dc`).
