# Native flash ABI and canary constraints

Pinned stock app 1.0.3.127, body SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`. App body XIP base `041eb020`; SRAM mappings and `gp=02011688` are from the existing startup-derived Ghidra project. Native calling convention is the existing RV32 integer ABI; the apparent fifth/sixth parameters in some decompiled helpers are register-liveness artifacts, not required public inputs. `core/*.asm` settles the four-register program interface.

```c
int program(unsigned device, uint32_t physical, const void *source, uint32_t length); // 04329b1e
int erase(unsigned device, uint32_t physical, uint32_t length);                    // 04329a14
int read(unsigned device, uint32_t physical, void *destination, uint32_t length);   // 04329ad8
```

All use physical per-device offsets, not XIP or unified device1 addresses. Zero is success. Program does not erase. Erase rejects unaligned address OR length with status1 before locking. Program splits exactly at256-byte page boundaries. These wrappers contain no total-capacity, partition, ownership, integer-overflow, source-lifetime or caller-context admission checks; the custom boundary must provide them. Zero length should reject in the custom boundary even though native helpers can perform a no-op followed by completion/cache handling.

## Serialization and completion

`04329912(device)` reads byte`0201233a`. Zero selects mutex pointer`0201233c+4*device` and `0200ec3a`; nonzero selects nested critical enter`0200a23a`. Unlock`0432994a` pairs mutex give`0200ecb2` or critical exit`0200a264`. Init`04329ce2` creates the native mutex with type9, installs the manufacturer-dependent driver table through`0432984c`, and records initialization. No initialization or lock-mode mutation is needed in an already-running application. Existing lock-mode setter`04329996` is used by diagnostic read path`041fb776`; do not call it for a canary.

Program`04329b1e` saves a0..a3, locks, calls`043296c8`, saves its status, polls busy`02005b1c`, invokes the optional callback at`02012344+4*device`, unlocks, invalidates the requested XIP range with`04324bea(0,physical+04000000,length)`, and returns the saved status. Erase`04329a14` holds the same lock through its optional callback **and cache invalidation**, then unlocks. This ordering difference is real. The optional callback is invoked without a declared custom argument contract; do not install or call it yourself. No direct callback-table write was found in the retained reference scan, which is not a runtime assertion that it is NULL.

Erase uses64KiB blocks only for aligned starts with at least64KiB remaining; all other chunks are4KiB sectors. A4KiB request at`003d1000` reaches exactly one sector operation (`0432975e -> 02005cde`, driver-table +14). It cannot take the64KiB branch. Program`043296c8` calls driver-table +10 with `(device,address,source,min(remaining,256-(address&255)))`; missing driver pointer asserts. Each lower driver emits write-enable06 and page program02/32 or erase20 through the SRAM controller path. Lower source staging`020082ae` copies the requested bytes synchronously to device0 FIFO`01104000` before launching. Supply an owned SRAM source anyway, retained until the entire public call returns; avoid flash-backed or request-owned buffers.

`02007ede` reads controller register+4 bit31. SRAM command functions wait for it to clear, configure address/length and FIFO, then`02007efa` sets bit31 to launch. `0433389a` chooses operation timing/configuration and writes controller+40; it is not an extra software lock. `02005b1c` polls flash status bit0 with one scheduler-delay unit between polls until clear. There is **no software deadline/cancellation** in that loop. A success return does not replace readback verification. A nonzero return can leave partial programming/erasure and must stop ordinary progression.

Cache helper`0432dd00` normalizes the alias according to cache index, aligns start down and end up to32-byte lines, and waits for completion. Public wrappers use cache index0; that matches device0 app XIP. No new direct XIP reads or private cache controls are necessary: use the public read API for verification. Other-core cache invalidation and interrupt/hardware arbitration are not exhaustively established by this local wrapper. Stock device0 KV and bootmap writes show this is the existing normal application mechanism; bypassing it with raw SRAM calls would discard that evidence.

## Execution constraints

Use one initialized, ordinary native task with the original native gp/tp and normal ABI. Preserve s-registers and16-byte stack alignment; use the established no-global append veneer. Do not invoke from ISR, LVGL deletion/timer callback, an externally held critical section, or while holding a flash mutex. Let the native wrapper acquire its own serialization. The app-side task mutex serializes cooperating callers; it does not grant tail ownership or make a multi-call transaction atomic.

Public program and erase each have48-byte frames, the page splitter48, selected page driver80; additional SRAM/helper/RTOS/callback/interrupt frames exist. These witnesses are **not a complete worst-case stack bound**. Keep custom frames small, source/readback storage in a bounded nonasserting owned allocation, and return through the established correlated-response path only after readback. No writable-global pointer or borrowed TLV may survive request cleanup. Do not keep device operations running after response construction failure, silently retry uncertain writes, change protection bits, or reset before an operation returns. A host timeout leaves the native operation potentially active.

`04329b90` is a separate erase/read-modify-write convenience interface. It can allocate4KiB through the asserting allocator, rewrites sectors, and does not stop its loop on every lower error. It is inappropriate for a bounded canary. Use the explicit erase/program/read interfaces and exact extent checks instead.
