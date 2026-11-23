# MemoMind memory capacity and asset-storage boundaries

Read-only static investigation of stock 1.0.3.127. No device commands, runtime
changes, writes to the G2 checkout, or persistent Ghidra changes. Every headless
export used `-readOnly -noanalysis`; logs and disassembly are retained here.

## Result

**No additional allocatable RAM pool was identified.** The stock application
registers one 658,584-byte SRAM range. The runtime's mask-0 allocator already
considers every registered pool. Mask 1 is a capability filter, not a second
pool selector: it matches none of this image's boot registration. Mask 2 selects
the same pool. SDK plugin allocation and LVGL allocation also use this heap.
This establishes the inspected application's allocation topology, not the
absence of other physical RAM or heaps belonging to other processors.

The unused app-partition tail can support **firmware-bundled immutable XIP
assets** within the existing append/rebuild bounds. It is not yet a reserved,
safe runtime-writable asset store. Native erase/program mechanics are present,
but ownership, update persistence, power-loss recovery and execution safety
have not been established for that tail.

## Source and exact pool registration

Stock OTA SHA-256:
`08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`.
Application body SHA-256:
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`,
1,773,176 bytes at XIP base `0x041eb020`. SDK checkout commit
`171098bff25934a534a49f95b88df58fbed404c7`.

`0x041fb27e` calls `0x0200f6ce(0x020ffe00)` at `0x041fb2aa`;
`0x0200f6ce` stores that pointer and calls `0x0433c5a8`.
The latter was not a defined Ghidra function: its actual raw RV32 disassembly,
not a newly invented function, is retained in `pool-registration.asm`.
It iterates 12-byte linker records from `0x04399550` to exclusive `0x0439955c`:
exactly one record (`initial-pool-table.json`).

| Property | Value |
|---|---:|
| Start | `0x0205e128` |
| Raw size | `0x000a0c98` = 658,584 bytes |
| End, exclusive | `0x020fedc0` |
| Capability flags | `0x2` |
| Descriptor array | `0x0205d5f8 .. 0x0205d648`, five 16-byte slots |
| Descriptor layout | flags, start, end, allocator pointer |

Startup `0x041fb1ec` copies code into `0x02000000 .. 0x0200f8b4`, initialized
data into `0x0200f8b8 .. 0x02011730`, and clears BSS
`0x02011878 .. 0x0205e128`. The heap begins exactly at that BSS end. The gaps,
stack-adjacent bytes and other processors' address ranges are **not** established
as spare or safely reclaimable RAM.

Pool constructor `0x0433c1ce` places a 16-byte accounting wrapper at the base,
then creates TLSF through `0x0433cb62(base+16,size-16)`. Its initial current/free
low-water accounting is `size - 16 - 2000 = 656568` bytes (`0x0433c990` returns
2000; `0x0433c9a0` returns 12 for the constructor's minimum-size guard).
This initial accounting is not current device availability or a largest-block
guarantee. The parent-reported earlier diagnostic `0x51884` is exactly 333,956
bytes; `0x4e104` is 319,748 bytes low-water. Those were earlier live samples,
not measurements made during this read-only task.

## Allocation ABI and ownership

| Address | Established behavior |
|---|---|
| `0x0433c294(size,mask)` | Try each nonzero pool whose `(flags & mask)==mask`; return allocation or zero; native critical section around search/allocation. |
| `0x0433c320(size,flags)` | Nonasserting frontend; lower 16 bits are capability mask, upper encoding requests extra alignment. Checked size addition. |
| `0x02009904(size,flags)` | Similar alignment frontend, but invokes OOM policy on failure. |
| `0x020099a0(ptr)` | Recognizes aligned-pointer marker, recovers allocation base, locates owning pool, updates accounting and frees under critical section. |
| `0x0433c3c6(mask)` | Sum current free accounting in matching pools. |
| `0x0433c460()` | Sum current free accounting in all registered pools. |
| `0x0433c4a4()` | Sum per-pool minimum-free accounting. |
| `0x0433c370(mask)` / `0x0433c418()` | Raw registered byte totals, filtered / all. |
| `0x0433c4e8(out)` | Enumerate start/size/flags triples under critical section; five-slot bounded table, stops at empty slot. Not invoked on device here. |

In `0x0433c320`, alignment extra is `(flags >> 13) & 0x78`.
**`0x10000` requests eight-byte alignment with mask zero; it does not select
external RAM.** Correct free must receive the original returned owned pointer,
exactly once. Native critical enter/exit are `0x0200a23a/0x0200a264`.
Never free borrowed display buffers or manually selected address ranges.
The existing try-allocator can fail cleanly on ordinary no-fit; generic
`0x0434e6da -> 0x02009904` may assert through the registered OOM callback.

SDK host table `0x0436609c` alloc/free slots point via
`0x0429b85c/0x0429b86a` to `0x042a8bac/0x042a8c42`.
Allocation adds 20 bytes, calls `0x0434e6da`, and maintains a plugin-owned lifetime
list, 16-byte header and trailing `0x504c5547` guard. Free validates/unlinks and
`0x042a8986` calls `0x0434e6ee`. This is bookkeeping on the same heap, not a
second allocator pool, and requires a valid plugin lifetime context.
SDK `GlassSDK/include/gm_plugin.h:398` promises suitably aligned owned memory
or NULL, freed using the paired Host free. The public SDK contract does not
prove the pinned implementation's complete OOM behavior. Its below-100-KiB
static-RAM build limit excludes dynamic heap, stack and Host bookkeeping
(`GlassSDK/docs/ABI.md`), and is not an extra RAM reservation.

LVGL `0x042b3a3c` directly uses `0x0434e6da` for nonzero allocation;
`0x042b3a56` uses `0x0434e6ee`, and `0x042b3a74` uses generic realloc.
The zero-size sentinel is not usable storage. These exports are in
`../display-adapter/memory/`; no private LVGL heap was found.

The bounded search included the five-slot descriptor references, sole boot
registration and constructor call site, generic/SDK/LVGL allocator chains,
startup ranges and string searches over all six CRC-verified component bodies.
No PSRAM/SDRAM/SRAM identifier established an alternative resource. Other
components contain heap-related strings, but their heaps were not mapped as
app-owned memory. No silicon datasheet, physical-memory probe, ROM-wide proof,
live descriptor dump or largest-free-block measurement was performed.
`cap-mask1-sites.txt` is a broad literal scan, not evidence of an extra pool.

## App-tail budget: bytes, sectors and staging are distinct

The concrete basis is offline `captures/firmware/input-observer-001/verification.json`,
**final_bounds**, not the earlier pre-hook append audit and not a current flash read.
Output SHA-256 is
`bbc777895ef3c56af8ff3b5cbac85c8e7acb429eadfdc194cd407f5255c12f85`.

| Quantity | Bytes |
|---|---:|
| App partition | 2,097,152 |
| Final app body | 1,822,432 |
| Final app including 32-byte header | 1,822,464 |
| Remaining app address space | **274,688** |
| OTA file | 2,221,167 |
| Final staged payload, excluding 18-byte outer header | 2,221,149 |
| Staging allocation | 2,482,176 |
| Exact payload headroom | 261,027 |
| Payload rounded to 4096 bytes | 2,224,128 |
| Headroom after that rounding | **258,048** |

The earlier append-stage values (2,221,202 payload / 260,974 free) precede
hook recompression and must not be labeled final. Compression means raw app
headroom cannot be substituted for packed staging headroom. Rebuild and check
both constraints for each asset bundle.

App physical partition is `[0x001eb000,0x003eb000)`; body starts at
`0x001eb020`, with the `+0x04000000` XIP alias. Final body ends at
`0x043a7f00`; remaining XIP range is `[0x043a7f00,0x043eb000)`.
A 4-KiB sector-aligned subrange begins at `0x043a8000`, leaving **274432** bytes
(67 sectors). The first 256 tail bytes share a sector with existing app bytes;
erasing that sector would erase part of the image. These are address-space
bounds, not a proof that contents are erased or that another service cannot use
the tail. Native font resources elsewhere are owned resources, not spare flash.

## Proven flash mechanism and remaining write boundary

`0x043299aa(device,address)` serializes through `0x04329912`, dispatches sector
erase through SRAM wrapper `0x02005cde` and device-table offset `0x14`, polls busy
through `0x02005b1c`, calls an optional post-operation callback, unlocks through
`0x0432994a`, then invalidates the XIP cache range
`((address+0x04000000)&~4095,4096)`. The lock path is per-device RTOS mutex
`0x0200ec3a/0x0200ecb2`, or nested critical section when flag `0x0201233a` is set.
`0x0432dd00` aligns cache maintenance to 32-byte lines and waits for completion.

`0x04329b1e(device,address,source,length)` uses the same synchronization/busy/
callback/cache sequence. Its helper `0x043296c8` splits requests at
**256-byte page boundaries** and calls table offset `0x10`. No app-tail bounds,
asset ownership or transaction layer was found in these wrappers.

Initialization `0x0432984c` selects one of two driver tables via manufacturer
query `0x02005bec`; `flash-driver-tables.json` records initialized table values:
`0x02010898` uses program `0x0432a620`, erase `0x0432a522`;
`0x020107f0` uses program `0x0432a06e`, erase `0x04329f5c`.
Both erase drivers issue command `0x20` through SRAM `0x020080c0`; program
selects command `0x02` or `0x32` and invokes SRAM `0x020082ae`.
The 4096-byte erase range is supported by the caller's cache range and concrete
native ring-store loop `0x0420fd64`, which advances by 4096 for sector erases
and can use 65536-byte block erases. This is sufficient to establish the native
sector/page conventions; it does not prove chip datasheet guarantees or power
failure behavior. The actual selected runtime table was not read on device.

Stock OTA metadata commit `0x043169ce` uses device 0 erase/program wrappers at
physical `0x007fc000/0x007fd000`; native recording uses device 1. These existing
call sites establish real flash use, not permission to borrow their partitions.
Low-level SRAM entry points help explain operation while flash is busy, but
interrupt/DMA/source-buffer constraints and safe arbitrary app-task calling
have not been exhaustively traced. Do not invoke these as a ready asset API.

## Concrete capacity path

1. Keep the proven nonasserting allocator and measured admission/budget checks;
   implement bounded streaming/lazy workspaces to avoid simultaneous full-wire,
   canvas, scene-undo and two-inflater allocations. The inflater report accounts
   for 39,944 bytes per RV32 zlib context before transport buffers.
2. Add immutable asset bytes to the existing CRC-covered app append construction,
   with an explicit directory, length/hash bounds and read-only XIP views. This
   saves RAM for immutable data without inventing another RAM pool. Native
   mutable scene/cache semantics still require an adapter and RAM metadata;
   immutable XIP storage alone is not full cache parity. No such adapter or image
   was implemented here.
3. A mutable flash cache needs a formally reserved sector range, update/CRC and
   boot ownership analysis, bounded RAM driver/source staging, erase/program
   serialization, recoverable directory commits and wear/power-loss policy.
   Tail carving is not complete until those facts and tests exist.

The full-G2-capacity goal remains open. No safe allocator switch eliminates the
current SRAM constraint, and no native runtime-write asset partition is claimed.
