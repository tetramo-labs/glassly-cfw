# USERIF settings migration (0x38 → 0x40)

Offline firmware validation for installing the Oct 2025-based Glassly application on units whose USERIF settings record was written by the Sep 2025 factory application. The background is in [no-boot-investigation.md](no-boot-investigation.md). Nothing here was run on hardware.

```sh
.venv/bin/python research/userif_migration_audit.py   # JSON report, ~6 s; exit 0 only if every expectation holds
```

The script runs each build's own code through a taint-tracking P-code executor (pypcode with the extended Q32S SLEIGH). Every byte read from USERIF is tainted with its offset. The executor faults on divide by zero, misaligned access, a jump outside code or a settings-derived jump target outside code. It records every settings-derived divisor, shift count, address index, `memcpy`/`memset` length and switch. Execution starts at the application's input/LED initialiser (APP_STA_CREATE: Oct `0x01e0afd8`, Sep `0x01e0b012`) with RAM `.data` and RAM code loaded as startup does. It stops at the emf task creation (Oct `0x01e0bcac`, Sep `0x01e0bc58`), after the LED PWM setup.

Modelling choices:
- The sdfile calls (`fopen/fseek/fread/fwrite`, sector erase) operate on a model of the USERIF sector with NOR write semantics. `malloc` and the ROM `memcpy/memset/memcmp/strlen` are native.
- SDK and Bluetooth calls outside `0x1e03000..0x1e10000` are stubbed to return 0, and MMIO reads return 0. The power key (PB6) reads as held, as at a normal power-on.
- Every case runs in all four positions of the two mode inputs PA1/PA2, which select list map 0, 3 or 4.

This is a bounded model, not the CPU: interrupts, the Bluetooth stack and the emf task itself don't run.

## Results

| Build / USERIF (×4 switch positions) | Outcome |
| --- | --- |
| Oct on the tester's original record | divide by zero at `0x1e0b322` (baseline reproduced) |
| Oct and Glassly on the migrated record | LED setup and task creation reached; divisor 10; **no USERIF writes** |
| Oct on unit1's factory 0x40 record | same as migrated; the event lists are identical in every position |
| Oct and Glassly on an erased sector | reached; erased defaults; first boot erases `0x7d000` and writes 0x4f0 bytes (0x40 format) |
| Sep on its original record | reached; divisor 10; no writes |
| Sep on an erased sector | reached; first boot erases `0x7d000` and writes 0x4e8 bytes (0x38 format) |
| Sep on the migrated record | reached, **no fault**; divisor 3; settings misread; first boot rewrites the sector into a mixed state |

### 1. Oct on the migrated record — proven within the model above

- **The record is a factory 0x40 record.** The migrated `m_storage` (`0x00..0x3f`) equals unit1's and unit2's factory records byte for byte except `+0x01` (`reset_reson`: 0x00, the tester's own value, vs 0x72).
  - `reset_reson` is only compared with 0x72 and cleared (`0x01e0b226..0x01e0b23e`).
  - Map 4 (selected with both inputs high) has the same data as unit1's map 4.
  - Maps 1, 2 and 3 equal the build's own default tables (`0x1e22a7c`, `0x1e22b3c`, `0x1e22bfc`). Map 0 differs from the default only in two key codes (`0x2b`/`0x4a` vs `0x28`/`0x2c`).
  - The default tables are byte-identical in Sep and Oct, so the map content format did not change.
- **List-map checks.** Oct's `api_storage_check_map` (`0x01e06b06`) checks:
  - `max_len == 0xc8` (`0x01e06b12`), `map_len <= max_len` (`0x01e06b18`) and `map_len != 0xffff` (`0x01e06b22`);
  - `map_len % 4 == 0` (`0x01e06b26`, the "map len align err" path);
  - CRC-16/MODBUS over `[2, 8+map_len)`, compared at `0x01e06b5e`.

  `res` is covered by the CRC but never compared, so Sep's `0x0021` is accepted. Running Oct's own `check_map` returns 1 for all six migrated maps and 0 for erased regions.
- **Settings-derived values in the initialiser** (all six migrated-record events are identical to the unit1 run):

  | Use | Site | Migrated value |
  | --- | --- | --- |
  | Divisor `500 / m[+0x3b]` | `0x01e0b322` | 10 |
  | Name-table index from `m[+0x0a]` (`strlen`) | `0x01e07286` / `0x01e072c4` | 0x0008 (unit1: same) |
  | Switch on a mode word from `m[+0x28]`, guarded `jhi r2,#7` | `0x01e068d0` | in range |
  | Switch on `m[+0x02]`, guarded `jhi r0,#3` | `0x01e0bc06` | in range |
  | `memset(0x3060, 0, map_len/12)` | `0x01e06dd8` | 6 (map 3); at most 16 since `map_len <= 0xc8` |
  | CRC table lookups indexed by data nibbles (`& 0xf`) | `0x01e06ade`, `0x01e06af0` | in range |

  No settings-derived shift count was seen. The list index `m[+0x02]` is forced to 0 when ≥ 6 (`0x01e0b134`) and bounded again before the second read (`0x01e0b53c`).
- **Code outside the initialiser,** from a static inventory of every load from `m_storage` (`0x3020..0x305f`) and the list-map buffer (`0x25e0..0x26a7`):
  - Sleep bytes `+0x39/+0x3a` are multiplied by 60000 (`0x01e0e36c`).
  - Screen sizes `+0x34/+0x36` are copied to `0x2c98` and used as multiplicands in the touch path (`0x01e0f66e`, `0x01e0f680`).
  - `+0x2e..+0x3b` are read into vendor GET replies (`0x01e09bc0..`, `0x01e0983c`, `0x01e09a40`).
  - The list map's `map_len` gives a loop bound `map_len/12` (`0x01e0d406`, `0x01e0e72c`), and the entry-type switch is guarded by `jhi r2,#4` (`0x01e0d436`).

  None of these is a settings-derived divisor. Every field has the same value as on unit1, which runs this build.

### 2. Erased sector, both builds — proven within the model

Both builds reach LED setup and task creation in every switch position.

- **Erased defaults:**
  - Oct: `+0x08=1`, `+0x0a=9`, `+0x0c=0xa00` (then adjusted for the mode), `+0x28/2a/2c = 8/0x100/0xa00`, `+0x2e..+0x36 = 0xf00, 393, 852, 1080, 2560`, `+0x39/3a/3b = 10/15/10`.
  - Sep: the same values, with the tail fields 8 bytes lower.
- **List map:** check_map fails, so the build copies the default table for the selected index (`0x01e0bc08..0x01e0bc58`) and calls `api_storage_sync` (`0x01e0bc68`) during the initialiser.
- **What the first boot writes:**
  - Oct: erases the whole 4 KiB sector at `0x7d000` and writes 0x4f0 bytes (`api_storage_write_map` `0x01e06bd0`, `STORAGE_TOTAL_SIZE` 0x4f0 at `0x01e06bd8`). That is the 0x40 record plus the default map at `0x40 + idx*0xc8`; the other map slots are erased.
  - Sep does the same with 0x4e8 bytes in its own format.
  - Either way the result is a self-consistent record for the app that wrote it, with the user's settings lost.

This justifies erasing first. An interrupted sequence leaves the unit booting with defaults, whichever application is active.

### 3. Sep on the migrated record — no fault; settings wrong

The Sep build reaches LED setup and task creation in all four switch positions; its divisor reads 3 (`500/3`).

- Its maps at the 0x38 grid are invalid (`check_map` 0 for all six), so it loads the defaults and syncs.
- That rewrite leaves a mixed sector: a 0x38 record, one default map at the 0x38 grid, and remnants of the shifted maps at the 0x40 grid.
- The misread fields include sleep-on-disconnect 1 and a wrong screen size.

The unit stays recoverable without the dongle, because the Sep app runs and handles Pairing+B. But the coordinator's preconditions then refuse the sector, which is correct, so the flasher needs a defined fallback for an unrecognised sector, such as reprogramming the saved pre-flash USERIF. Under the planned order, Sep never sees the migrated record: step 3 runs only after the header commit.

### 4. Nothing else in USERIF is an address, length or count — proven statically

- `mnt/sdfile/app/USERIF` is opened only by `api_flash_read` (`0x01e06a3a`) and `api_storage_write_map` (`0x01e06bd0`), two references in each build.
- Reads cover `[0, sizeof m_storage)` and `[sizeof + i*0xc8, +0xc8)`. `write_map` reads and rewrites `[0, STORAGE_TOTAL_SIZE)`, and its page loop stops after page 0 (`jhi r14, 0x4ef` at `0x01e06c1a`). **Sector `0x7e000` is never read or written** by either build; it is erased on the tester.
- **Fields actually read:** `+0x01` (compared with 0x72), `+0x02` (bounded index), `+0x08/+0x0a/+0x0c/+0x0d` (mode words, and the name index above), `+0x28..+0x3f` (Oct; Sep `+0x20..+0x37`).
  - Nothing reads `+0x00` as a value, nor `+0x03..+0x07` or Oct `+0x0e..+0x27` (Sep `+0x0e..+0x1f`).
  - `+0x3c` (u32) is used only when not `0xffffffff` (`0x01e0b31a`); the tester has `0xffffffff`.
  - No field is a flash address, length or count. The only length is `map_len`, which check_map validates.
- Bytes after the six maps are never read and are erased by the first sync.
- Separately, the VM items read and written through `syscfg_read`/`syscfg_write` with immediate arguments are the same set in both builds, 12 read and 9 written (`report.syscfg_items`). VM, which is preserved, shows no item-layout change.

### 5. Insertion point and erased maps — proven

- **Code:** aligned Oct/Sep code accesses Oct field `f` where Sep accesses `f` for `f ≤ 0x0d`, and `f − 8` for `f ≥ 0x28`. Neither build accesses the inserted span.
- **Defaults:** the erased-default pairs extracted from both initialisers correspond exactly after a +8 shift at 0x20 (`defaults_correspond_with_shift_at_0x20`).
- **Data:** the migrated record equals the factory 0x40 record. With `old[0x0e:0x20]` erased, any insertion point in `[0x0e, 0x20]` gives identical bytes. 0x20 matches LiteEMF's `api_storage_t`, where `map[]` (at 0x18) grew from 8 to 16 bytes.
- **Erased maps:** an erased region shifted to `0x40 + i*0xc8` is rejected by Oct's check_map. If it is the selected map, the default is loaded and synced. Unit1 and unit2 already have maps 1, 2 and 5 erased and boot.
- **Partial programming:** an interrupted program of the record can't produce a zero divisor. NOR programming only clears bits, the migrated `+0x3b` is 0x0a, and every intermediate value keeps bits 1 and 3 set.

## Conditions the flasher must check before migrating

1. `old[0x0e:0x20]` all `0xff`.
2. Each region at `0x38 + i*0xc8` (i = 0..5) is all `0xff`, or valid under **both** builds' `check_map`: `max_len == 0xc8`, `8 ≤ map_len ≤ 0xc0` (Sep `0x01e06bba`), `map_len % 4 == 0` (Oct), and CRC-16/MODBUS (init 0xffff, reflected poly 0xa001) over bytes `[2, 8+map_len)` equal to the stored `crc`. CRC-valid alone is weaker than Oct's rule.
3. At least one region at 0x38 is valid. No region at `0x40 + i*0xc8` is valid (otherwise the sector is already 0x40 format, or ambiguous).
4. `old[0x4e8:0x1000]` all `0xff`, which implies the coordinator's `old[0xff8:0x1000]` check and refuses any unknown data that the shift would move.
5. `old[0x33] != 0x00` (it becomes Oct `+0x3b`, the divisor). A booting Sep unit can't hold 0 there, since Sep divides by the same byte, but checking costs nothing.
6. Leave `0x7e000` alone, and read the programmed sector back exactly.

If a retry finds a freshly defaulted record (because an interrupted sequence let an application boot), migrating the session's saved pre-flash record restores the user's settings. Both are safe to boot.

## Blockers and limits

Nothing in the firmware blocks a supervised first flash with this migration. Remaining limits:

- The model covers the initialiser up to task creation. The emf task, Bluetooth stack and interrupts were checked statically, and through the field-for-field equality with unit1's record, not executed.
- The tester's unit is the only Sep-format sample (n = 1); keep the preconditions strict.
- The tester's unit is still in the Oct reset loop. A flash on it needs USB_KEY entry first ([no-boot-investigation.md](no-boot-investigation.md)), and per `AGENTS.md` the first flash of a new kind needs that application-independent recovery on hand anyway.
- After an interrupted sequence the flasher needs a defined fallback for an unrecognised USERIF state (section 3).
