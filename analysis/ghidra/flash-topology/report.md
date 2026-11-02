# Flash topology and CUS8 context lifecycle

The stock paths have **different controller instances, different pin/CS setup, and incompatible successful manufacturer-ID predicates**. This is stronger evidence than different API names: the supported general-SPI OTA endpoint cannot also be the successfully identified XIP device1 endpoint under stable, correct ID responses. No physical board/netlist measurement or live ID query was performed here. A small passive diagnostic can corroborate the initialized endpoints without issuing a new SPI transaction.

A normal OTA reset into the inspected app entry **does discard the old CUS8 context before the new initializer runs**. An all-`ff` directory does not by itself prove that no transient RAM context exists. Neither issue blocks construction of an offline2MiB CUS8 profile with the previously audited bounds; hardware admission should pin that image and collect the fixed diagnostic evidence described below.

## Sources and fixed mappings

Stock app1.0.3.127 body SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, XIPbase`041eb020`, nativegp`02011688`. All exports used the existing startup-mapped database with `-readOnly -noanalysis`. No source/runtime/device writes were performed. Controller table values are read from the static initialized-data mapping, not a live RAM capture; see[controller-tables.txt](controller-tables.txt).

| Path | Controller base | Data/address namespace | Identity admitted by native initialization |
|---|---|---|---|
| XIP device0 | `01100100` | Per-device physical offsets, FIFO`01104000`, app alias`04000000+offset` | Command90 manufacturer85 orc8 |
| XIP device1 / CUS8 | `01100200` | Per-device physical offsets, FIFO`01108000`; CUS8device1`[00500000,00800000)`, unified`[01500000,01800000)`, XIP`[05500000,05800000)` | Command90 manufacturer85 orc8 |
| General SPI0 / PY25/BY25 backend | `01480000` | Four-byte raw addresses; command13 read /12 program | Command90 four bytes exactly`68 18 68 18` or`68 19 68 19` |
| General SPI1 (not selected here) | `01490000` | Separate general-SPI instance | Not evaluated here |

XIP controller pointers are initialized words`020114f4/020114f8`; general-SPI pointers are`0201150c/02011510`. This establishes distinct hardware register blocks. It does not alone prove external chips are distinct, hence the additional ID and routing analysis.

## XIP identity, capacity and probe cache

`04329ce2(device)` initializes a mutex and calls`0432984c`. The latter checks controller readiness through`04333944`, then reads legacy manufacturer/device ID through`02005bec(device)`: command90, two returned bytes. This is **not** a newly discovered9f JEDEC interface. It selects table`02010898` for manufacturer85, or`020107f0` forc8. The only recognized driver-pointer assignment is in this initializer. Unknown manufacturers do not install another supported table; the subsequently dereferenced driver pointer is not a general fallback. The cold BSS starts those pointers at zero.

The existing device1 directory acquisition succeeded through the initialized XIP reader. Together with the stock init path, this supports the inference that the working device1 endpoint uses one of the supported85/c8 families; it is not a direct observation of its raw ID. The byte`0201234d` alone is insufficient evidence: `04329ce2` marks initialized even when the initializer returns an error. Normalize the driver pointer at`02012334` as well, and retain unknown/null rather than guessing a family.

`04329d62(device)` performs another command90 read; it is **not a cached capacity getter**. Its native result is zero when device-code byte<19hex, otherwise`1 << (code-0x13)`. The CUS8 initializer converts that result to a byte-capacity check equivalent to at least8MiB for its intended inputs. Examples: code16hex gives8;18hex gives32. Do not report the result as bytes without this conversion, and do not assume a live ID from the static table.

Family85 setup`0432a28c(device)` reads command90, command5a at address32hex through`02005c3e`, and16bytes of command4b data through`02005c8e`. It caches a **probe composite**, not the full unique ID:

```
code = (legacy_id_u16 << 16) | (extra_id_byte << 8) | uid_bytes[0]
valid = *(u8 *)(0205c8d8 + 8*device)
code  = *(u32*)(0205c8dc + 8*device)
```

Device1 therefore uses valid`0205c8e0`, code`0205c8e4`. Known code comparisons include`1485f941`, `1485f942`, `1485f141`, `1585f942`, `1685f942`; they choose timing data. Full UID bytes remain a local16-byte read and are not needed for topology diagnostics. `02005c8e(device,out16)` returns zero without propagating its lower read status, so it should not be repurposed as a reliable health query.

Familyc8 setup`0432a1c8` has a **shared, non-device-indexed** cache: valid`02012350`, timing index`02012351`, composite`02012354` formed from command90 shifted16. It recognizes`14c80000`, `15c80000`, `16c80000`. Do not attribute that shared cache to device1 without establishing which device initialized it. Driver-family normalization is still per-device.

## General SPI0 endpoint and CS routing

`04345f4c` installs table`02010c6c` from`043470c8`, calls its initializer`04346966`, and sets readybyte`020124d4=1` **only after success**. Its read/program dispatchers refuse when that flag is zero or their table slot is missing. Calls occur in ordinary application initialization and diagnostic/OTA paths; the native code is not proof that this physical endpoint is present or initialized on the captured device.

The initializer calls`04320432(0)` and`043206f0(0,config,pins)`. Its literal pins are clock5, manual-CS token102(`66`hex), output/TX3 and input/RX4. Pins are cached at`0205c26c` as four32-bit fields, with manual/hardware flag at`0205c27c`. `04320628` reserves/configures the CS as a GPIO and replaces its hardware-CS pin argument with`ff`; `04333bca` configures clock/TX/input mux functions. Output mux writes use`01848400 + 4*pin` via`020076aa`; input mux uses`01848000 + 4*function` via`020075f8`.

Actual transaction start`04320126` drives the cached manual-CS GPIO low through`02004406`; end`02003fec` drives it high. This GPIO API accepts tokens below128;102 is a valid software token, not an uninitialized sentinel. It resolves through the GPIO registry before changing the output state. No board pad/net name or electrical connection is inferred from the token. XIP device1's dedicated controller routing is inherited from platform/boot configuration; its external pad wiring was not recovered in this bounded pass.

General-SPI init sends release-from-powerdownAB, polls readiness, enables four-byte modeB7, checks status15 bit0, then calls`0434633e(out20)`. That helper reads command90 with three zero address bytes and requires alternating manufacturer/device bytes`68,18` or`68,19`. It returns code6818/6819 and a bounded name string; despite the source filename`gm_flash_py25q256lc.c`, the returned name is`BY25Q256FS`. Names alone are not used as topology proof. The ID result is local to initialization; no persistent raw general-SPI ID cache was found. Readybyte is the retained successful-init witness.

A fixed-ID chip correctly returning manufacturer85/c8 cannot simultaneously return68 to the other stock legacy-ID transaction. Thus a successful supported initialization on both paths is inconsistent with them addressing the same ordinary endpoint. Distinct controller/CS setup reinforces that inference. Unmeasured board switching, incorrect/stale ID responses, corrupted state or factory access are outside this conclusion; no universal hardware-isolation claim is needed to prepare the offline constructor.

## Sector-map address translation if aliasing existed

Generic OTA mapper`04239a66` seeds768 logical4KiB sectors using a13-bit physical sector cursor from KV`e00/e89` or a random seed. The initial table is`physical_sector[i]=(seed+i)&0x1fff`; retries/remapping can change entries. `04239ea4` uses the current16-bit table at`020135f4` and computes:

```
physical_byte = map[logical_offset >> 12] * 4096 + (logical_offset & 4095)
```

That byte address goes directly through`0434609a/0434603c` into command12/13 four-byte addressing. There is **no CUS8+500000 or unified-device+1000000 translation**. Physical indices0..8191 span32MiB; indices700hex..7ffhex correspond exactly to`[00700000,00800000)`.

Therefore, **if** the endpoints were physically the same, the generic mapper could select the proposed device1 reservation directly. The3MiB logical bound would not protect it. This is why API separation alone was insufficient. The successful ID predicates and controller/CS evidence instead support distinct endpoints on the supported stock paths; the passive snapshot can corroborate the actual initialized state.

## CUS8 all-ff directory and old-context lifetime

The two acquired64KiB directories are all`ff`; native mount`042a0e46` returns-1 for that unformatted state, as established in[native-store-inventory](../native-store-inventory/report.md). The pointer`02011e48` is not inferred from those bytes.

`042a43c8(param1,param2)` allocates a`1210`hex-byte context if the pointer is NULL. In read/query mode`param1!=0`, if mount returns-1 and`param2!=0`, it zeroes context directory state, sets capacity+40 to300000hex, cursor+44 to10000hex, sets flag+119c, and reports success **without formatting flash**. Thus a successful RAM context can coexist with an all-ff directory. The known capacity-query caller`042a4628` invokes exactly`(1,1)`, uses it, then frees and zeros the singleton before returning. This particular context is transient, not an established long-lived mounted store.

Write/install caller`042a4598` first tears down the old context and calls`(0,0)`; erased mount then formats through`042a1812`. Other store sessions can retain the singleton until cleanup or completion. `042a439e` clears verification state, frees the context, clears the active flag and pointer. Successful package completion`042a48f0` also frees/zeros the context but can leave active package offset/validation state in`02011e4c/02011e50`; therefore context-NULL alone does not prove no package is active.

For the ordinary OTA reset path, bootloader handoff selects app entry`041eb020`. At`041eb04e` it unconditionally calls`041fb1ec`. Instructions`041fb234..041fb24e` zero BSS`[02011878,0205e128)`, which includes`02011e48`, `02011e4c`, `02011e50`, all the flash initialization globals above, and the store-related runtime pointers. Startup then recreates normal heap/task state. The old capacity context is not reused by a new2MiB initializer when this normal entry path is taken. This does not describe hot-patching a running context or a warm-resume route bypassing startup.

## Concrete next evidence

[diagnostics.md](diagnostics.md) specifies fixed passive scalar fields and optional initialized-only legacy-ID calls. Prefer the passive snapshot first: it introduces no mount, GPIO configuration, flash mode change, unique-ID disclosure or arbitrary memory-read command. The future diagnostic must use the pinned code/layout and return semantic fields, not raw pointers. No diagnostic implementation or device query was performed here.
