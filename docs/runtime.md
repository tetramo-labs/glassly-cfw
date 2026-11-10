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
| Runtime RAM block | `0x0209be74`..`0x0209ce74` | heap carve (GLASSLYCFW/5+), zeroed at boot (below) |
| Breadcrumbs | `0x0209ce74`..`0x0209cf74` | heap carve (GLASSLYCFW/6+), kept across resets (below) |
| Heap (only region) | `0x0209cf74`..`0x020fefc0` | stock `0x0209be74`; table entry `0x04414f5c` |
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

Requests larger than one packet are reassembled before the router sees them
(`0x0426d700`, three 0x3000-byte chains at `0x0207b1f0`, `0x0207e210`,
`0x02081230`, one per transport, 50 s timeout): the chain holds
`[cmd][key][len LE16][payload]`, so a payload is at most **12,284 bytes**
(`0x0426d548` drops anything shorter than the 4-byte header). The payload
pointer is that chain buffer, valid only during the router call.

## Build

`python3 -I scripts/build_runtime.py <stock 1.1.5.1 OTA> <revision>` applies the
string edits (`patches/glasslycfw-2/1.1.5.1.json`, version tag set to
`GLASSLYCFW/<revision>`), compiles `runtime/nimo/` and the portable scene core
(`scene`, `geometry`, `vector`, `rle`, `raster_commands`, `rect_copy_commands`)
with xPack GCC 15.2 (`rv32imc`/`ilp32`, `-mstrict-align`, `-Os`, freestanding,
`-Wcast-align=strict` on `runtime/nimo`, one object per source, no writable
statics, every stack frame static and at most 512 bytes except
`glassly_command`'s 624 on the router task), runs `scripts/runtime_scan.py` on
the listing (fails on any instruction outside RV32IMC, on a multi-byte load or
store through a pointer derived from packet bytes, or on a UI-task frame chain
over 8 KiB; records the chains in `build.json`), applies the data patches
and code hooks after checking their witness bytes, appends the blob with
`nimo_ota.replace_body`, and writes
`captures/firmware/ota-1.1.5.1-glasslycfw-<revision>.bin` (or `--image`) plus
`captures/build/glasslycfw-<revision>/build.json` (or `--out`). It fails when
the blob exceeds the room after the stock body. The checks it makes on the
output: every hooked site disassembles to `auipc`/`jalr` into its gate, no
branch in the containing stock function lands inside a hook, each gate replays
the displaced instructions, the heap entry and the `lui`/`addi` pair decode to
the RAM block bounds (and `runtime/nimo/ram.h` agrees), no stock instruction
computes an address in the carve except the boot clear's end bound, and no
other byte of the body or of any stream except the metadata row changed. Flash with
`mobile/modules/bluetooth-sdk/tools/nimo-mac` in the glassly repo.

Excluded from the blob: `keyboard`, `ancs_ingress`, `notifications`,
`flash_store`/`scene_store`, `transport`/`inflater`/zlib, `upstream`, `wake`.
GLASSLYCFW/6 is 41,131 bytes (scene 21.8 KB, vector 5.2 KB, geometry 3.9 KB,
glassly 3.4 KB, display 2.7 KB, scene_session 1.9 KB, rle/rect copy/raster
2.1 KB, gates 112 B), leaving 42,357 bytes.

## Tests

`python3 -I tests/run_tests.py --output <new dir>` runs every offline suite as
numbered stages and writes `summary.json` (result, duration, logs per stage);
it exits 0 only when every required stage passed and no source changed during
the run. It never contacts a device.

| Stage | What | Required |
|---|---|---|
| 01_container | `scripts/test_nimo_ota.py` | yes |
| 02_cfw_string_builds | each `patches/*/*.json` rebuilt from `captures/firmware` | no (skipped without the stock images) |
| 03_runtime_build | `build_runtime.py` for `--revision` (default 6) into the run directory | yes |
| 04_portable_host | `runtime/portable/tests/run_tests.py` and `run_scene_tests.py`: geometry/RLE/vector/scene against the pinned G2 reference, read in place from `~/dev/glassly-memomind-one-cfw/tests/g2_compat/upstream` (hash-checked; `--g2-source`/`GLASSLY_G2_REFERENCE` to move it) | yes |
| 05_session_host | `runtime/nimo/tests/run_session_tests.py`: the real runtime C with the stock functions replaced by host stand-ins, the scene demos, breadcrumbs across a simulated reset, and the reply expectations in `tests/hardware/steps-<revision>.json` | yes |
| 06_rv32_emulator | `tests/rv32/runtime_emulator_test.py`: the linked blob from stage 03 under Unicorn with every stock entry point mocked (heap on a real arena, 4-aligned blocks, UI jobs on their own 32 KiB stack), both gates' register contracts, and `tests/hardware/steps-<revision>.json` replayed in order with the heap the glasses reported. As strict as the core: instructions outside RV32IMC, misaligned halfword/word accesses and any access outside the runtime's own memory (RAM block, breadcrumbs, the stock flags it reads, live heap blocks, the task's stack, the read-only request) raise a device fault; peak stack depth per task is recorded | no (skipped without `~/dev/glassly-memomind-one-cfw/.tools/rv32-tests-venv`) |

`tests/hardware/steps-6.json` is the on-glasses check list for revision 6 (the
Mac harness runs it in order; step 1 shows the breadcrumbs); generate its
scene files first with
`python3 -I scripts/scene_packets.py demo captures/scenes/demo-geometry.bin`
and `python3 -I scripts/scene_packets.py retained captures/scenes`.

## Commands (0x7E)

Replies are `[status][data...]`. Status: 0 ok, 1 invalid (malformed, out of
range, or the stock call failed), 2 no memory, 3 display not owned, 4 too
large, 5 unsupported, 6 busy (UI queue full or 4 scene messages already
waiting). Keys marked *UI* are copied and run on the UI task, which sends the
reply once the work is done; a busy refusal is answered at once.

| Key | Request | Reply |
|---|---|---|
| 0x01 | — | identity JSON: `version`, `revision`, `platform`, `base`, `arm` (master/slave), `eye` (left/right), `canvas` `{width 540, height 280, stride 270, format gray4}`, `eyes`, `scene` `{modes, store 65536, objects 128, assets 128, show_eye_bits, eye_objects, text false}`, `max_message` 12284, `owned` |
| 0x02 | bytes (≤ 499) | the same bytes |
| 0x03 | bytes (≤ 12,284) | `[0][len u32 LE][crc32 u32 LE]` of the payload (zlib CRC-32), to verify multi-packet transfers |
| 0x04 | — | status JSON: `owned`, `session`, `boot` and `last_crash` (breadcrumbs, below), `heap_free`, `heap_largest`, `display_on`, `panel_brightness` (stock level), `brightness` (last 0x23 level, 255 none), counters `gate_skips` (stock panel writes and frame kicks held off), `repins`, `presents`, `present_rows`, `deferred`, `flush_errors`, `scenes`, `rejected`, `settled`, `busy`, `alloc_failures`, `pump_ticks`, `commands`; at most 548 bytes with the status byte (reply buffer 560) |
| 0x10 | `[pattern]` | *UI* GLASSLYCFW/4 test frame (0 bars, 1 border + diagonal, 2 black): `[status][flush rc][left]` |
| 0x20 | one scene message `[mode][...]` | *UI* `[status][cache reply...]`: the message is dispatched to the session (modes below); cache modes 37–41 and bundles append the core's reply (`[mode][request u16][status][epoch u16][revision u32][extra]`); status 3 when not owned |
| 0x21 | — | *UI* acquire: `[status][flush rc][display on][eye]`. Pins the stock framebuffers and borrows one as the canvas (status 1 if the index bytes are not 0/1), creates the session (status 2 if the heap cannot spare it + 32 KB), starts the pump, sets owned, presents the whole canvas (black on a new session, the retained scene on a repeat) |
| 0x22 | — | *UI* release: `[0]`. Stops the pump, frees the session and every scene allocation, gives the canvas buffer back (below), clears owned, then `0x041fe71a()` and `lv_obj_invalidate(lv_screen_active())` |
| 0x23 | `[level 0..32]` | *UI* `[status][stock rc]` from `0x041fec90` (not persisted) |
| 0x24 | — (notification) | unsolicited `[0][tag u16 LE]` when a SHOW with the TAG flag has settled; follows the 0x20 reply that started it |
| 0x25 | — | *UI* `[status][crc32 u32 LE][eye 1/2]`: zlib CRC-32 of this arm's 75,600-byte canvas (status 3 when not owned). Only the master (right arm) answers, so hardware steps compare the right canvas with the emulator's render |
| other | — | status 5 |

Scene modes (the MemoMind 0x7d channel's raw messages, minus built-in text,
diagnostics and the flash store): 37 PUT, 38 SHOW, 39 HIDE, 40 STATE,
41 CONTROL (RESET/DROP/period), 8 bundle (segments of 3, 6, 9, 19, 20, 36,
37–41), 19 image and 20 string immediates, 36 geometry, 3/6 raster (RLE),
9 rectangle copy. Mode 15 and text shapes draw nothing (no font yet).

Per eye. Each arm drives its own panel and both arms run every command, so
both keep the same retained scene. A standalone SHOW whose flags carry 0x10
(left) or 0x20 (right), MemoMind revision 22, renders on both arms but only
the named arm flushes; the other arm keeps the rows pending and sends them,
joined with its next change, the next time a present is for its eye (bundles
and every other mode present to both). Objects whose id has bit 31 belong to
one eye (bit 30 set = right, MemoMind revision 23); each arm's scene context
has its eye fixed at creation (`MM_SCENE_FIXED_EYE`), so it draws only its own
tagged objects, in one pass. The arm's eye is the left flag `0x02011b18`
(1 = left).

## Display

- Panel `iv00654dsf` (descriptor `0x0430c3fc`, ops `0x0430c408`): 540×280,
  4-bit gray, 270-byte rows, high nibble = even x. Each arm drives its own
  panel; orientation comes from the left flag (`0x02011b18`) and mirror flag
  (`0x020121bd`) through panel registers 0x17/0x36, not from the framebuffer.
- Stock framebuffers: `0x0202f064` and `+0x12750` (75,600 B each), back index
  `0x020120fb`, front index `0x0201198a`, per-row dirty flags `0x0202ef4c`
  (280 B), dirty rows `0x020120f4`/`0x020120ee`, pending `0x020120ec`. Frame
  task `0x041fd3e2` flushes under the display mutex.
- Every stock function that forms an address inside them (lui/auipc pairs over
  the XIP code and the startup RAM-code copy; the build re-checks this list):
  the LVGL flush `0x041f7958` → `0x041fd0ac` → RAM `0x0200023a` (L8 to GRAY4
  into the back buffer, marks dirty rows); the frame task (clears the margins
  of the buffer it flushes); the commit `0x041fdb08`, reached only from the
  kick `0x041f703c` (copies back to front, or flips: front = back, back ^= 1,
  then copies the whole frame), with its helpers `0x041fd2c4` and `0x041fcd42`;
  the scroller `0x041fe23e` (draws into the back buffer) and `0x041fe51c`
  (reads it); the clear `0x041febb2` (zeroes the back buffer, from the display
  power paths); and `0x041fe6f2`, the front-buffer pointer for the stock
  screenshot command `0x041f30f6` (read only). The index bytes are reached
  only through gp: every load is a read, and only the commit stores to them
  (`0x041fddd8`, `0x041fdde0`) or takes their address for writing.
- Row flush `0x04200db2(fb, x, row0, w, nrows)`: x/w ignored, sends
  `fb + row0*270` for `nrows` rows over SPI DMA, blocking; 0 = sent, 1 = panel
  down (`0x020121be`). Take the display mutex (`0x041fc706()`, then
  `os_lock 0x0200ed06` / `os_unlock 0x0200ed7e`) around it.
- Brightness: `0x041fec90(level)` takes the display mutex and calls panel op
  `0x04202646` (ops +0x1c): 0 = set, 1 = panel down (`0x020121be` = 0) or
  level > 32. On success the op keeps the level in `*(u16*)0x0201198e`.
- LVGL 9.3: logical display **500×220** (physical 540×280), color format L8,
  one 27,500-byte partial buffer at `0x02026798`; flush cb `0x041f7958`
  converts L8 to 4-bit and offsets into the framebuffer (x `0x02011976`,
  y `0x02011978`). Default font `0x0431ee44` (line height 18).

## UI task

- `gui_post_async(fn, arg)` `0x04206cf2` runs `fn(arg)` on the UI task (48-slot
  ring, no copy, nonzero when queued); `0x04206d96` is the 8-slot priority ring.
- The UI task is `gui_task`, created at `0x04207004` through `0x041fa81c`
  (attributes `0x0430d148`: name, priority 3, stack 32,768 bytes); the GUI loop
  (`0x04206762`, 64 B) and the async drain (`0x04206342`, 512 B) sit above a
  posted job. Static frame chains (`build.json` `stack_chains`, indirect calls
  to every hook, stock callees excluded): UI jobs at most 2,208 B, the router
  672 B; measured in the emulator: `nimo_ui_scene` 1,872 B, the pump 1,664 B,
  the mode-36 path 1,264 B, the router 656 B. `send_response`'s own static chain
  is about 1.4 KB.
- Critical section: `0x041fa74e` enter / `0x041fa760` exit (to `0x0200a432` /
  `0x0200a45c`: `csrrci mstatus, MIE` with a nesting count); the GUI task guards
  its async ring with them. The core has no A extension: no AMO/LR/SC appears
  in any of the 9,076 stock functions, so the runtime is built `rv32imc` and
  its one shared read-modify-write (the scene job count) runs inside these.
- Heap: `malloc 0x041fa772`, `free 0x041fa784`. `0x042f7aea()` returns the free
  bytes summed over the five region slots at `0x0209b3bc` and
  `0x042f7a38(caps)` the largest free block, both inside a critical section
  (`0x0200a432`/`0x0200a45c`); the stock boot trace `DIAGHEAPCHK ... free=%d
  largest=%d` (`0x041e3aba`) prints exactly these two.
- Clock: `0x041fa73c()` returns the FreeRTOS tick count `*(u32*)0x02013368`
  (through `0x0200f898` → `0x02008bfa`), which is milliseconds: the GUI loop
  (`0x04206762`) times `lv_timer_handler` with it against a 30 ms budget and
  logs every 10,000 ticks, and `0x041f7674` multiplies the same tick by 1000 for
  the reassembler's microsecond trace.
- `lv_timer_create(cb, period, user_data)` (`0x0423f7f8`) fills `period`,
  `timer_cb`, `user_data`, `repeat_count = -1` and asserts forever when LVGL is
  out of memory; `lv_timer_delete` is `0x0423f89e`. The GUI loop drains the
  async ring before `lv_timer_handler`, so a posted job never runs inside it.
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

## GLASSLYCFW/5 on the glasses (2026-11-09) and the fix in GLASSLYCFW/6

Steps 1-6 of `steps-5.json` passed (acquire, status: owned, 280 rows
presented, heap 117,620 free). Step 7, the first scene message (0x7E/0x20,
the 242-byte mode-36 demo), got no reply and the glasses reset. Cause: the
revision 5 blob was built `rv32imac` and the scene job count used
`__atomic_fetch_add/sub`, which GCC emits as `amoadd.w`: four in
`glassly_command` (`post_scene`, first at `0x04417da6`) and one in
`nimo_ui_scene` (`0x04418772`). They are the first A-extension instructions the
runtime ever executed (steps 1-6 never touch the count), and the core does not
implement A, so the router task took an illegal-instruction trap before
anything was posted or answered; the stock crash handler resets. The strict
emulator reproduces this from the flashed blob (`runtime_sha256 fa22dbba…`):
steps 1-6 pass and step 7 faults at `0x04417da6`; with AMOs allowed, steps 1-7
pass with no misaligned access, no access outside owned memory and 1,264 B of
UI stack. GLASSLYCFW/6 builds `rv32imc` (an AMO no longer compiles; the build
also rejects any listed one), counts jobs inside the stock critical section,
adds `-mstrict-align`, and records breadcrumbs.

Separate from the crash: a retained scene needs about 170 KB of heap (cache
45.5 KB, the 64 KiB store, 10.8 KB undo, 48.8 KB vector work) on top of the
48 KiB headroom, but after the acquire the glasses have about 117 KB free. With
those numbers the emulator answers `scene-retained.bin` and the later SHOW
steps with cache status 2 (MISSING: the store was refused), without a reset.

## GLASSLYCFW/6 on the glasses and the borrowed canvas in GLASSLYCFW/7

`steps-6.json` ran with no reset: identity, status, echo, the 1200-byte
checksum, acquire, the mode-36 demo (the frame that reset /5), the 40 s hold,
brightness and release all passed. The five retained-scene steps answered
cache status 2 (MISSING), as predicted: measured on RV32, the scene's cache
block is 45.5 KB, the undo workspace 47.5 KB plus saved granules, the vector
workspace 10.8 KB and the store 64 KiB, about 167 KB, while the heap had
117 KB after the 75.6 KB canvas, 48 KB of which the policy keeps for the stock
firmware.

GLASSLYCFW/7 stops allocating the canvas. The two stock framebuffers (Display,
below) have a small, closed set of writers, and the acquire pins them so that
one buffer has none (Lease, below). The canvas is that buffer: the lease now
costs the 1.3 KB session. The scene capacities drop to 128 objects and 128
assets with a 64 KiB store (`-DCFW_CACHE_OBJECTS=128u -DCFW_CACHE_ASSETS=128u
-DCFW_TEXTURE_CACHE_SIZE=65536u`; the portable defaults stay 256/256/256 KiB):
about 124 KB with allocator headers, leaving about 69 KB free on the glasses'
heap. Borrowing the second buffer too (it needs gates on the LVGL flush, the
frame task, the scroller and the clear routine) would bring back 256/256.

On the glasses (2026-11-10, `ota-1.1.5.1-glasslycfw-7.bin`, sha `b4b66fbe…`):
all 25 steps of `steps-7.json` passed (`captures/suite-7.json`). Heap 194,344
free before the lease, 193,052 owned, 68,980 with the retained scene resident,
194,432 after release. Every retained-scene reply was APPLIED, the glide
settled (key 24, tag 3), and the right canvas checksums matched the emulator
at all five points, including after the 40 s hold (no stock writer touched the
borrowed buffer); `repins` and `flush_errors` stayed 0. The first flash
attempt stopped at 45 % when the Mac's Bluetooth controller turned off (the
glasses kept running GLASSLYCFW/6); the retry took 73 s.

## Breadcrumbs (GLASSLYCFW/6)

The heap region starts 256 bytes past the RAM block (`0x0209cf74`, size
`0x6204c`, same end), and the boot clear still ends at `0x0209ce74`, so
`0x0209ce74`..`0x0209cf74` belongs to the runtime and survives a reset that
keeps RAM. Layout (`nimo_crumbs` in `ram.h`; the top 16 bytes stay unused):

| Offset | Field |
|---|---|
| 0x00 | `magic` `"NCB6"`, 0x04 `check` = `~magic`: both must match before anything is trusted (power-on RAM is noise) |
| 0x08 | `boot`: 1 when the record started fresh, plus one per boot that found it intact |
| 0x10 | three lanes of 12 bytes: router, UI job, pump tick. Each `{seq u32, len u32, stage u8, key u8, mode u8, 0}` |

Each lane has one writer. The router lane starts at `router` (seq = the
command number, key, mode = first scene byte, len) and ends at `posted` (the
UI task owns the job) or `reply` then `done`. A UI job starts its lane at
`dispatch` with the same seq, then `render` (scene work about to draw; also
the draw test), `present` (a panel flush), `reply`, `done`. A pump tick that
has the lease starts the pump lane at `tick` (seq = tick count), passes
`render`/`present`/`reply` when it animates or settles, and ends at `done`.
`idle`, `posted` and `done` are resting stages.

The first 0x7E command after a reset (the zeroed block has no magic yet)
copies the lanes into the block (`last`, offset 0x58), bumps `boot` and clears
the lanes. The status JSON then carries `"boot":N` and `"last_crash"`: `null`
when every lane of the previous boot was at rest or no record survived, else
`{"lane","stage","seq","key","mode","len","open"}` for the first unfinished
lane in the order UI, pump, router (`open` is a bit per unfinished lane: 1
router, 2 UI, 4 pump). Example after a reset while the mode-36 demo was
presented: `"last_crash":{"lane":"ui","stage":"present","seq":4,"key":32,"mode":36,"len":242,"open":2}`.
Whether this RAM survives the stock crash reset is not yet known: a `boot` of
1 after a crash means it did not.

## Display ownership (GLASSLYCFW/5 and later)

### RAM block

Data patches (witness → patched):

| Patch | Address | Stock bytes | Patched bytes | Effect |
|---|---|---|---|---|
| heap-region-start | `0x04414f5c` | `74be0902 4c310600 02000000` | `74cf0902 4c200600 02000000` | the only heap region `{0x0209be74, 0x6314c, caps 2}` becomes `{0x0209cf74, 0x6204c, 2}` (same end `0x020fefc0`; revision 5 had `{0x0209ce74, 0x6214c}`); heap init `0x042f7c32` walks exactly this one 12-byte entry |
| bss-clear-end | `0x041c3b96` | `b7c70902` | `b7d70902` | `lui a5,0x209c` → `0x209d`: the boot clear (`addi a5,a5,-396` follows) now ends at `0x0209ce74` |

So `0x0209be74..0x0209ce74` (4 KB) is zeroed every boot, the breadcrumbs
above it are not, and no stock code allocates either. Its layout is `runtime/nimo/ram.h` (zero is valid for every
field; RV32 offsets):

| Offset | Field | |
|---|---|---|
| 0x00 | `magic` | `"NRM7"` once a 0x7E command has run this boot |
| 0x04 | `session` | heap session (scene context, canvas pointer, pending rows, eye, settled queue); UI task only |
| 0x08 | `owned` (u8) | 1 while the runtime owns the panel; read by the flush gate |
| 0x09 | `brightness`, 0x0a `brightness_set`, 0x0b `eye` | last 0x23 level; eye at the last acquire |
| 0x0c | `gate_skips` | stock panel writes and frame kicks the gates skipped |
| 0x10 | `timer` | `lv_timer_t` of the scene pump; UI task only |
| 0x14 | `jobs` | scene messages queued, not yet run (changed only in the critical section) |
| 0x18 | `epoch` (u16) | last scene epoch; a new session starts at epoch + 1 |
| 0x1c..0x4c | counters | `commands`, `scene_messages`, `scene_failures`, `presents`, `present_rows`, `presents_deferred`, `flush_errors`, `settled_sent`, `busy`, `alloc_failures`, `acquires`, `releases`, `pump_ticks` |
| 0x50 | `boot` | breadcrumb boot count at this boot's first command |
| 0x54 | `crumbs` (u8) | 1 record started fresh, 2 previous boot's record kept; 0x55 `lane`: lane the UI task runs |
| 0x58 | `last[3]` | the previous boot's lanes (12 bytes each), as the first command found them |
| 0x7c | `pinned` (u8), 0x7d `front`, 0x7e `back` | 1 while the framebuffer indices are pinned; the front index the lease found (restored at release) and the back index it pinned |
| 0x80 | `repins` | pump ticks that found the indices moved and pinned them again (expected 0) |

The rest of the 4 KB is reserved. The canvas (540×280 GRAY4, stride 270,
75,600 B) is the borrowed stock framebuffer; the session and the scene's own
allocations come from the stock heap, the scene under the MemoMind policy (at
most 170 KiB tracked, never leaving under 48 KiB free; a refused allocation
becomes a CAPACITY reply, not a crash). A full retained scene (128 objects,
128 assets, 64 KiB store) peaks near 124 KB; `0x7E/0x04` reports
`heap_free`.

### Hooks

| Hook | Kind | Address | Stock bytes | Patched bytes | Gate |
|---|---|---|---|---|---|
| router-unrouted | jump (`auipc t1; jalr x0`) | `0x0426e02e` | `378637044a87d287` | `17a31a006700239b` | `glassly_router_gate` `0x44179e0` |
| frame-flush | call (`auipc ra; jalr ra`) | `0x041fd63c` | `4a8781499c4b8297` | `97a02100e780403d` | `glassly_flush_gate` `0x4417a10`, returns to `0x041fd644` |
| frame-kick | jump (`auipc t1; jalr x0`) | `0x041f703c` | `83c7514891cf0111` | `17132200670043a1` | `glassly_kick_gate` `0x4417a50`, rejoins at `0x041f7044` / `0x041f705c` |

(Patched bytes and gate addresses are those of the revision 7 build; the build
recomputes and checks them, and scans the whole stock body so that no direct
branch lands inside any hook.)

The flush gate replaces `c.mv a4,s2; c.li s3,0; c.lw a5,16(a5); c.jalr a5`,
the frame task's only panel write. It replays the two moves, then, when
`owned` is 0, loads the panel op and tail-calls it (`lw a5,16(a5); jr a5`, so
the op returns straight to `0x041fd644`); when owned it bumps `gate_skips`,
writes the auto-off flags and returns 0 (sent) without touching the panel.
All the frame task's pending/dirty/token bookkeeping still runs. It uses only
`t0`–`t2`, which the replaced call clobbers anyway.

The kick gate replaces the kick's first three instructions, `lbu a5,1157(gp);
c.beqz a5,0x041f705c; c.addi sp,-32`. When `owned` is 0 it replays them (the
branch becomes a jump to `0x041f705c`, the frame-task tail call, with no
frame) and rejoins at `0x041f7044`; when owned it bumps `gate_skips` and
returns 0 to the kick's caller, so the commit (and the frame task behind it)
does not run. Callers: the LVGL refresh (`0x0423b150`, return ignored), the
wrapper `0x041f65be` (app pages, the WASM host), and `0x041feaf4`/`0x041feb22`,
which are posted to the UI task's rings.

### Lease

- Acquire (UI task): pin (below), session, pump timer `lv_timer_create(pump,
  10, 0)`, `0x04268164(2)` (cancel an armed auto-off), then the whole canvas
  is flushed.
- Pin: with the display mutex held (the frame task does all its work under
  it) and interrupts masked, the runtime records both index bytes, sets the
  front index to the back one, and sets `pinned` and `owned`. From then every
  stock writer below uses the back buffer, the kick gate keeps the commit from
  copying into the other buffer or moving an index, and the other buffer,
  `0x0202f064 + (back ^ 1) * 0x12750`, is the canvas (cleared to black).
- Every pump tick checks both indices still equal `back`; if anything moved
  them it pins them again, counts `repins` and resends the whole canvas.
- Presents (UI task): the dirty boxes of a render become a row range; the rows
  go out through `0x04200db2(canvas, 0, row0, 540, rows)` under the display
  mutex (`0x041fc706`, `os_lock`/`os_unlock`). A refused flush (panel down)
  keeps its rows pending for the next present. Immediate and raster modes
  present the whole canvas; a new cache's first render does too.
- Pump: every 10 ms the timer refreshes the auto-off flags, advances the scene
  (elapsed time, no backlog), presents and sends settled notices.
- Auto-off: about 3 ticks of a black stock canvas turn the display off
  (`0x04268558`: lit flag `*(u8*)0x02011a3a`, black-tick counter
  `*(u32*)0x02012a38`, a word: `lw`/`sw` at `0x04268182`). Every owned present,
  every pump tick and every gated stock frame sets lit = 1 and the counter = 0.
  Display state `0x02011fa6` (1 = on); off routine `0x041f6c4a`, on `0x041f6d06`.
- Release (UI task): delete the timer, save the epoch, free the session, then
  unpin: under the display mutex the canvas buffer gets a copy of the back
  buffer, and with interrupts masked the recorded front index returns and
  `pinned`/`owned` clear. Then the stock repaint: `0x041fe71a()` (all framebuffer rows dirty;
  stock callers do not hold the display mutex for it) and
  `lv_obj_invalidate(lv_screen_active())`. Stock pairs `0x041fe71a` with
  `0x041f703c` (frame kick) at `0x041feb14`; not called here.

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
