# No boot after a verified flash on the IINE-layout unit

Report of 2026-11-13 (tester's date), analysed offline. No hardware was attached, nothing was built or flashed, and no backup was modified. Reproduce everything below with:

```sh
.venv/bin/python research/noboot_audit.py      # JSON report; exit 0 only if every expectation holds
```

## Result

**Root cause (high confidence): a settings-format mismatch in the USERIF partition, not the hardware, the flash part, the layout or the Glassly hooks.** The Sep 2025 factory application stores its LiteEMF settings record (`m_storage`) as 0x38 bytes followed by 0xc8-byte list maps. The Oct 2025 application, and the May 2026 factory build the development units shipped with, use a 0x40-byte record. The flasher preserved USERIF, as designed. On first boot the Oct-based Glassly application read the Sep-format record with its own layout, loaded the high byte of list map 0's header (`0x00`) as a divisor, and executed `500 / 0` at `0x01e0b322`. That runs during the application's input/LED initialiser, before the LED PWM setup and before the button handler exists. `debug_init` enables the divide-by-zero exception (`EMU_CON = 0x80000017`), and the exception handler resets the chip. The result is a reset loop with no lights, and Pairing+B can't help because the application handles that combination.

The **stock** Oct 2025 application would fail in exactly the same way on this unit, and so would the May 2026 factory build. The development units boot because their USERIF already holds the 0x40-byte format, written by their May 2026 factory application.

| Step | Status |
| --- | --- |
| Sep build reads 0x38 bytes of `m_storage`; Oct, May and Glassly read 0x40 | Proven from code |
| Tester's USERIF is Sep format; dev units' USERIF is 0x40 format | Proven from data (CRC-valid list maps) |
| Oct/Glassly divisor on the tester's data is 0; on dev-unit data it is 10 | Proven by executing the actual instructions (P-code) |
| `debug_init` enables the div0 exception before any task runs | Code proven; bit meaning from Jieli's AC632N source |
| `div.u` by zero traps on hardware, and the handler resets | Inferred (vendor-defined enable bit; handler traced in `boot-failure.md`); not observed live |
| uboot hands control to the Glassly app on this layout | Inferred: bytes match IINE's own image; no live trace |

## Inputs

| Item | SHA256 |
| --- | --- |
| Tester pre-flash dump `research/device-backup-20261113-tester/flash-pass1.bin` | `4d6d2481…df89` |
| unit1 / unit2 factory dumps | `9b7c5738…7cb3` / `221856d2…66f5` |
| Sep 2025 factory app (from tester dump), 198,760 B | `e8584016…21af` |
| Oct 2025 official app, 198,824 B | `2fb44f42…f259` |
| May 2026 factory app (dev units), 196,224 B | `902aedc3…7c97` |
| Glassly app, 199,232 B | `495ce913…f432` |
| Image written to the tester (rebuilt offline) | `af4af1e6…c8a7`, matching the flasher's verified readback |

The audit rebuilds the written image with `stock_update.build(tester_dump, glassly_app)`, which is what that install's `plan()` did; `plan()` has since gained the USERIF migration ([userif-migration.md](userif-migration.md)). It checks that the image carries the Glassly app and that USERIF (`0x7d000..0x7f000`) is byte-identical to the pre-flash dump.

## The fault

### 1. Record size in code

LiteEMF `api_storage_init` (pinned LiteEMF `9abcfb35`, `api/api_storage.c`) calls `api_flash_read(0, &m_storage, sizeof m_storage)`. It then reads the selected list map from `sizeof m_storage + index*0xc8`. In the Jieli port, `api_flash_read` opens `mnt/sdfile/app/USERIF` (string at `0x1e20dc2` in Oct), so the record lives at flash `0x7d000` on both layouts.

| Build | Read call | `sizeof m_storage` | `m_storage` (RAM) | Divisor byte |
| --- | --- | --- | --- | --- |
| Sep 2025 | `0x01e0b14c mov r2,#0x38` → `0x01e06adc` | 0x38 | `0x3724` | `m_storage+0x33` |
| Oct 2025 | `0x01e0b128 mov r2,#0x40` → `0x01e06a3a` | 0x40 | `0x3020` | `m_storage+0x3b` |
| May 2026 | `0x01e0a952 mov r2,#0x40` | 0x40 | | `m_storage+0x3b` |
| Glassly | same bytes as Oct | 0x40 | `0x3020` | `m_storage+0x3b` |

Oct 2025, right after the read:

```text
01e0b30a lb.u  r0, [r10 + 0xbb]      ; m_storage+0x3b (r10 = 0x2fa0)
01e0b30e jne   r0, 0xff, 0x1e0b31a   ; only 0xff is replaced by the default 10
01e0b314 mov   r0, #0xa
01e0b316 sb    r0, [r10 + 0xbb]
01e0b31a lw    r1, [r10 + 0xbc]
01e0b31e mov   r2, #0x1f4
01e0b322 div.u r0, r2, r0            ; 500 / byte, no zero check
```

The Sep build has the same sequence on `m_storage+0x33` at `0x01e0b318..0x01e0b330`. The only path that avoids the division is the battery-protect power-off (`[0x2a98] == 2` at `0x01e0b27a`). The charging branch (`0x01e07590`) returns and continues to the division.

### 2. Record size in data

The list maps carry a CRC-16/MODBUS (init 0xffff) over `res, max_len, map_len, map[]`, which pins down where they start:

| Dump | CRC-valid maps at `0x38 + i*0xc8` | at `0x40 + i*0xc8` |
| --- | --- | --- |
| tester | 0, 1, 2, 3, 4, 5 | none |
| unit1, unit2 | none | 0, 3, 4 |
| written image | 0–5 (preserved) | none |

```text
tester 0x7d000: ff 00 00 ff ff ff ff ff 01 00 08 00 00 01 ff ff
       0x7d010: ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff
       0x7d020: 08 00 00 01 00 0a 00 0f 89 01 54 03 38 04 00 0a
       0x7d030: 00 0a 0f 0a ff ff ff ff dc 4b 21 00 c8 00 c0 00   <- map 0 header at 0x38
unit1  0x7d020: ff ff ff ff ff ff ff ff 08 00 00 01 00 0a 00 0f
       0x7d030: 89 01 54 03 38 04 00 0a 00 0a 0f 0a ff ff ff ff
       0x7d040: 1a b7 ff ff c8 00 c0 00 …                         <- map 0 header at 0x40
```

The fields match earlier USB queries: screen `{8, 0x100, 0xa00, ios_ver 0x0f00, 393, 852, 1080, 2560}` and sleep `{discon 10, con 15}`, then the divisor byte 10. On the tester, Oct's `m_storage+0x38..0x3b` falls on map 0's `crc = 0x4bdc, res = 0x0021`, so byte `+0x3b` is `0x00`. Any Sep-format USERIF with map 0 written gives the same zero.

### 3. Divisor per application and USERIF

`noboot_audit.py` executes each build's own instructions from the byte load to `div.u`, with `m_storage` loaded from each dump's USERIF:

| App ↓ / USERIF → | tester (Sep format) | unit1 | unit2 |
| --- | --- | --- | --- |
| Sep 2025 | 10 → 50 | 3 → 166 | 3 → 166 |
| Oct 2025 | **0 → div0** | 10 → 50 | 10 → 50 |
| May 2026 | **0 → div0** | 10 → 50 | 10 → 50 |
| Glassly | **0 → div0** | 10 → 50 | 10 → 50 |

### 4. Divide by zero is an exception on this chip

`debug_init` at `0x01e10a5a` stores `0x80000017` to `EMU_CON` (`0x1be1c0 + 0x40`), the same in all four builds. Jieli's own AC632N (BD19) source, `Jieli-Tech/fw-AC63_GP_MCU` `sdk/bsp/AC632N/src/debug.c` (blob `3695681`, last commit `53fd6bc`, 2026-05-30), defines `EMU_MISALIGN_EN 1<<0`, `EMU_ILLEGAL_EN 1<<1`, `EMU_DIV0_EN 1<<2`, `EMU_PC_LIMIT_EN 1<<4`, `EMU_SYS_ERR_EN 1<<31`, and its `debug_init` ORs exactly these: `0x80000017`. The same file's `emu_msg` table reads bit 2 as `div0_err`. The pinned SDK's `debug.c` bitcode has the same table (`@.str.68`). A local copy is kept, ignored, at `research/q32s-analysis/noboot/ac632n-debug.c`; it was fetched with:

```sh
gh api -H 'Accept: application/vnd.github.raw' repos/Jieli-Tech/fw-AC63_GP_MCU/contents/sdk/bsp/AC632N/src/debug.c
```

Order: `main` (`0x01e1d364`) calls `setup_arch` (`0x01e10adc`), which registers the exception handler at `0x5e20` (`0x01e10bc6`) and calls `debug_init` (`0x01e10bd8`), before any task is created or the OS starts (`0x106da8`). The application initialiser that divides runs in a task, after that. The handler path `0x5e20 → 0x01e0f898` stores marker `0xab` and soft-resets (`boot-failure.md`). Startup recognises the marker as `soft_reset_exception` (`0x01e107e6`) and continues booting normally, so the fault repeats.

### 5. What the user sees

The LED is driven by a three-channel MCPWM table (Oct `0x1e2258c`, 12-byte entries, first bytes 3/4/5). It is set up by the MCPWM loop from `0x01e0b610` (log strings `[MCPWM] MCPWM_CON0`, `mcpwm clk`), and the emf task, which runs the button handler, is created at `0x01e0bcac`. Both come after the division in the same initialiser, so the LED never lights and no button is ever processed. Unit1's withdrawn image faulted later, inside the hooks after LED setup, and showed white triple-blinks. Faulting before LED setup fits "no lights" here; this comparison is an inference.

## What is ruled out

**(a) Hardware revision / board config.** The Sep and Oct builds make the same 15 GPIO input-configuration calls with the same pins and modes (11 distinct pins: PB6, PB4, PB5, PB3, PA7, PB7, PA0, PB8, PB9, PA1, PA2). They have identical LED PWM tables and an identical 91-record, 945-byte GATT profile. The battery/charger state function (`0x01e0a95c` in Oct) aligns completely; its only differing bytes sit in relocated call offsets, the RAM base (`0x29b0` → `0x3170`) and string addresses. Its thresholds and PB4/PB5 charger inputs are the same. The initialised RAM data image (0xc60 bytes) differs only in relocated pointers and one initialised config struct at RAM `0x8c0` that gained a byte field. Nothing in the Oct build treats this hardware differently from the factory build that runs on it. That is not a live test of the Oct build on `cd7013` hardware.

**(b) Flash part.** No build contains `cd7013`/`cd7113` (or the byte-swapped forms) as an immediate. No Sep/Oct code difference falls in the SFC, flash driver or `sdfile` code; the OTA update code differs only in struct offsets and log calls. `isd_config.ini` (`SPI 2_3_0_0`) is identical. The identified fault does not involve flash access.

**(c) VM/storage partitions.** Partition locations are read from the tables through `sdfile` ("VM size: 0x%x @ 0x%x"), so VM at `0x34000` with 284 KiB is fine. The problem is the *content* of USERIF, which `flash_layout` correctly classifies as runtime storage.

**(d) uboot hand-off / header fields.** `build()` of the **stock** Oct app on this layout is byte-identical to IINE's own update image (`research/unpacked/decrypted.bin`) over the whole used area `0x2000..0x33cba`. The Glassly image differs only in the sizes and CRCs `build()` rewrites, exactly as on the dev units. The fault above is after hand-off. Without a live trace, a uboot rejection can't be excluded absolutely; the discriminating check under Recovery separates the two.

**(e) Glassly hooks.** Glassly equals Oct byte for byte over the whole initialiser `0x01e0afd8..0x01e0bca0`. Before the fault, only two patches execute: the BSS count at `0x01e0013a` (+4 bytes) and the `debug_init` text limit at `0x01e10a92`. Both are virtual-address changes, independent of layout, and boot on unit2. The task stack (0x840) and the payload are never reached. The audit's matrix shows the unpatched Oct app fails identically.

## Is the Sep 2025 build a different target?

No. It is an older build of the same product firmware:

- Same Bluetooth controller library `BTCTRLER-@20241105-$2db2c60`, same single-bank update framework ("single bank update", `nor_ota.bin` …), same reported firmware version `0x300` (`emf_api_init … sw version` argument). May 2026 is a dual-bank build with `BTCTRLER-@20241225-$7bce326`, version `0x600`.
- 955 vs 958 strings (`strings -n 6`). Apart from build dates, the differences are LiteEMF debug messages (`trp init` → `api_mode_init`/`emf_api_init`, map length checks) and one removed BLE name helper (`ble_comm_set_config_name`, Sep `0x01e03440`).
- Byte alignment (`difflib.SequenceMatcher`, `autojunk=False`, ~3 min) matches 94.1% of the Oct app. The 7.6% "same offset" figure came from address shifts. Real code changes cluster in LiteEMF/IINE code: `button_report_handler`, `emf_task`, the vendor frame/command code, USB endpoint setup and the storage/initialiser at `0x01e0afd8`, plus field offsets of a few BSS structs (RCSP/update, GATT). Board pins, LED, battery and GATT are unchanged.
- Startup is identical in shape: Sep BSS `0x1cc0..0x4878`, RAM code at `0x4880` (`0x1d68` B), text end `0x1e2dfa8`; Oct BSS to `0x40b8`, RAM code at `0x40c0`, text end `0x1e2dfc8`.

## Supporting units like this one

Keep `install` and `restore` refused on this kind until one of the options below has been reviewed and has booted on a developer-owned unit with application-independent recovery available (USB_KEY, below). `restore` (official Oct app) bricks such a unit in the same way.

A better guard than the layout fingerprint is the USERIF format itself. Refuse to put a 0x40-format application (Oct, May, Glassly) on a unit whose USERIF holds CRC-valid maps at `0x38 + i*0xc8`. That also covers a two-slot unit that ever carried a Sep-era record.

### Option A: keep the Oct-based Glassly app, migrate USERIF (recommended)

One reviewed binary, already proven with the hooks. The only incompatibility found is data, and the fix is deterministic and checkable offline. It also makes `restore` to the official app safe on these units.

- Convert one sector at `0x7d000`: `new = old[0:0x20] + ff*8 + old[0x20:0x38] + old[0x38:0x38+6*0xc8]`, the rest `0xff`. The maps move as whole units, so their CRCs stay valid. Require `old[0x0e:0x20]` to be all `0xff` (true here and on the dev units, so the insertion point inside that span doesn't matter) and every map to be CRC-valid; otherwise refuse. The alternative is erasing the sector: every field the initialiser reads has an explicit `0xff`/`0xffff` default (`0x01e0b30e`, `0x01e0b344`, `0x01e0b364..0x01e0b3da`), but that loses the user's modes and key maps.
- Still to check offline: Oct's map checks ("map len align err", "map max_len err,len=%d,max=%d") against Sep maps with `res = 0x0021` (Oct/May write `0xffff`); any other `m_storage` field Oct uses as a divisor or index; a P-code run of the whole `api_storage_init` path on the converted record (the audit already shows the divisor becomes 10).
- Flasher: this is the first deliberate write outside the application area. Make it an explicit, format-checked, one-sector step with readback. `restore-backup` must also put back the backup's USERIF when it restores a Sep app over a migrated record. The written app area must end before `0x33fe0` (see side findings).

### Option B: port the hooks to the Sep 2025 build

No data migration, and the base app is the one already running on this hardware and data. Everything maps one to one (verified by disassembly in the audit):

| Oct 2025 | Sep 2025 | Item |
| --- | --- | --- |
| `0x01e034b4` | `0x01e03570` | `gb_stock_att` |
| `0x01e041b6` | `0x01e04272` | `gb_stock_ccc` (tail jump to `0x1e13aa0`) |
| `0x01e0520c` | `0x01e052be` | `gb_stock_ble_event` |
| `0x01e0ce10` | `0x01e0cdae` | `gb_stock_handler` |
| `0x01e14114` | `0x01e1411c` | `gb_stock_set_ccc` |
| `0x01e0ee68` | `0x01e0eea4` | `gb_stock_task_entry` (`add sp,#-0x58`, same 88-byte frame) |
| `0x01e0bcac` / `0x01e0bcb6` | `0x01e0bc58` / `0x01e0bc62` | task create / stack `0x800` |
| `0x01e0f194` | `0x01e0f1a4` | task tick call |
| `0x01e04b86` | `0x01e04c38` | CCC setter call |
| `0x01e05270`, `0x01e05256`→`0x01e05276` | `0x01e05322`, `0x01e05308`→`0x01e05328` | BLE moves, unchanged-state branch |
| `0x01e10a90` (`0x1e2dfc8`) | `0x01e10a98` (`0x1e2dfa8`) | `debug_init` text limit |
| `0x01e00138` (`0x23f8`), epoch `0x40b8` | `0x01e00138` (`0x2bb8`), epoch `0x4878` | BSS count / reserved word |
| RAM `0x29b0`+: connection `0x29e2`, keys `0x2a78`, tick `0x2adc` | `0x3170`+: `0x31a2`, `0x3238`, `0x329c` | same field offsets in the scanner |

The GATT handles (AE42 `0x54`, CCC `0x55`) are identical. Work: a second payload link and pinned hash; per-build guards in `custom_image.patch_app` and `boot_audit.py`; a re-run of the P-code hook and scanner checks against Sep bytes, including the pushed-register list of the BLE setter at `0x01e052fa..`; flasher selection of the Glassly build by factory build; `restore` for this kind becomes `restore-backup`. The cost is two Glassly binaries to maintain, and these units keep the older IINE application.

## Recovery

### What the code and documents say

- **Pairing+B is handled by the application.** The button handler (`0x01e0d7c4`) and a vendor command (`0x01e08ea0`) call `api_boot` (`0x01e075ca`). That calls RAM `0x4ebe`: `nvram_set_boot_state(2)` (ROM `0x106f40`; 2 is `UPGRADE_USB_SOFTKEY` in the SDK's `cpu/bd19/chargestore.c` enum), then a reset into the ROM's USB mode. Both callers run only after the faulting initialiser, so **Pairing+B cannot enter update mode while the Glassly or Oct app is installed on this unit**. This matches "no restart on the pairing button".
- **Documented, application-independent: USB_KEY** (kagaimiq `jl-uboot-tool` `docs/how-to-enter-uboot.md`, pinned `adb3f18`). At every boot the mask ROM looks for key `0x16EF` clocked on D-/D+. It acknowledges by pulling both lines low for 1–2 ms, then the dongle hands the bus to the host and the chip enumerates as UBOOT1.00. The ROM then calibrates its clock from SOFs, so the bus must be quiet: use a USB 2.0 hub or a separate controller. Jieli's "USB updater" dongle and forced-upgrade tool do this; Jieli's AC63 hardware guide pairs forced-upgrade tool 4.0 with an AC6321A (BD19) board (links in `recovery.md`). kagaimiq lists BD19 as "unknown" for his tool.
- **Documented but not applicable: ROM fallback.** The ROM enters USB mode by itself when there is no valid firmware. The flash holds a valid image.
- **Not a recovery path.** `isd_config.ini` `RESET PB01_08_0` is the SDK default 8-second long-press reset on PB1, active low. It only resets into the same loop, and the application configures no button on PB1, so whether any control is wired to it is unknown. Letting the battery drain eventually takes the battery-protect power-off before the fault (`0x01e0b27a`), which stops the loop but doesn't open USB mode. `uboot.boot` is a compressed BANKCB image (flag 0x40, one bank of `0x12cf` B loaded at `0x2000`). It was not decompressed, so nothing is claimed about any key check inside it.
- **Inferred, untested:** because the unit resets continuously, every cycle passes the ROM's USB_KEY check, so a dongle sending the key repeatedly should catch a boot without a manual power cycle. A microcontroller bit-banging the documented key is plausible but unproven on BD19. Don't short pads or the in-package flash.

### What the tester can do, in order

1. **Discriminating check, no writes:** plug the unit in with no buttons held and watch for the update device (`4c4a:3442`, "BR34UBOOT1.00"/BD19). This hypothesis predicts it never appears, with or without Pairing+B. If it does appear on its own, the chip is falling back to ROM USB mode, which points at a boot rejection rather than this fault. Record which happens; it is the one live observation that separates the two.
2. **If the update device appears at all:** run `restore-backup` with the tester's own first-session `flash-pass1.bin` (same bytes as `research/device-backup-20261113-tester/flash-pass1.bin`, SHA256 `4d6d2481…`). Offline, `plan(written_image, oem, 'restore-backup', backup=…, flash_id=0xcd7013)` writes the same 50 sectors (`0x2000..0x33000`) and reproduces the original dump exactly; `install` and `restore` stay refused. The Sep app reads the untouched Sep-format USERIF and computes divisor 10.
   ```sh
   .venv/bin/python -u research/flash_gamebrick.py restore-backup --backup <session>/flash-pass1.bin   # Windows: .venv\Scripts\python
   ```
3. **Otherwise:** a Jieli USB updater dongle or forced-upgrade tool in USB_KEY mode, passing the bus through to the PC, then step 2. Don't use IINE's updater or `restore`: both install a 0x40-format application over this USERIF.

## Side findings

- Every dump holds a 32-byte non-erased record at the fixed address `0x33fe0..0x34000`; tester `90c0143002…2283…6aabfc3bcfe00c00`, the dev units differ in bytes `0x11` and `0x18..0x1d`. On the IINE layout these are the last 32 bytes of the application area. All our images preserve them, but `stock_update.build` only requires the app to end before `0x34000`, so a larger payload could overwrite them. Add `end <= 0x33fe0` for this layout. Their purpose is unknown; the SDK reserves 32 bytes of burner info (`CONFIG_BURNER_INFO_SIZE`).
- IINE's public Oct update can't be safe for Sep-format units unless IINE's updater resets USERIF. Its UFW covers only `0..0x34000` and carries no USERIF data, so how it treats USERIF is unknown.
- Latent bug in the Oct and May builds: any path that stores 0 in that settings byte (`m_storage+0x3b`) bricks the next boot the same way. Which vendor `set_*` command writes it was not traced.

## Limits

The disassembly comes from the extended SLEIGH via pypcode, with linear sweeps. The P-code run here covers only the seven instructions around the division; `research/userif_migration_audit.py` runs the whole initialiser (see `userif-migration.md`). Every `sb`/`sh`/`sw` in the Oct app decodes to a STORE of the right size. Function boundaries come from the earlier Ghidra export of the Oct app. No live trace, reset-cause register or UART log exists for this unit; UART TX would be PA5 at 1 Mbaud per `isd_config.ini`, the same pin as one LED channel.
