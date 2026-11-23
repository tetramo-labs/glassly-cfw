# Explicit 256-byte CFW registry reservation

**The proposed carve is coherent on the pinned normal app startup and heap-registration paths.** It is an explicit change to the memory layout, not reuse of an unexplained native slot. This review produced proposed byte witnesses and read-only evidence only: no image, production code, tests, or device state was patched.

Source app1.0.3.127 SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`. Original BSS is `[02011878,0205e128)`; sole registered heap is `[0205e128,020fedc0)`, raw size000a0c98, flags2. Reserve `[0205e128,0205e228)` and register `[0205e228,020fedc0)` instead, raw size000a0b98 (658328bytes). Raw heap capacity decreases exactly256bytes; flags, end address, pool count, initialized-data copy, code copy, gp02011688, stack locations, and native globals remain unchanged.

The reservation begins at an **8-byte-aligned** address. Its size is256bytes; its address is not256-byte or16-byte aligned. Use a registry whose required alignment is at most8 and whose full size is at most256; ordinary RV32 uint32/pointer fields need4. If stronger alignment is required, explicitly reserve padding within this span or revisit the carve, rather than claiming more alignment.

## Exact witnesses

[proposed-edits.json](heap-carve/proposed-edits.json) records byte-verified edits, with no patch applied:

| Address / original body offset | Before | After | Meaning |
|---|---|---|---|
|041fb238 /00010218|`93878712`|`93878722`|ADDI a5,a5,128hex becomes228hex; prior LUI at041fb234 remains0205e|
|04399550 /001ae530|`28e10502980c0a00`|`28e20502980b0a00`|Pool record start0205e128→0205e228 and size000a0c98→000a0b98|

Pool flags word at04399558 remains`02000000`; table end remains0439955c. Both instruction/table edits must be applied together and pinned to exact old bytes. Patch only the immediate instruction, not the native BSS globals or the startup source/destination mappings. No body-size change is needed; app/container integrity fields must still be rebuilt by the constructor.

At [041fb1ec](../ghidra/memory-capacity/startup/function-041fb1ec.asm), startup first copies SRAM code and initialized data. Instructions041fb234..041fb24e form `end-(gp+1f0)`, then call native memset with destination02011878/value0. The proposed immediate changes its length from4c8b0 to4c9b0. Thus the new registry is zeroed on every normal app entry before it can hold a worker/context pointer. This is not a warm-resume or live hot-patch guarantee. Applying only the pool edit would leave unspecified registry contents; applying only the BSS edit would let the allocator own/overwrite the registry.

## Heap consumers and metadata

[Registration0433c5a8](../ghidra/memory-capacity/pool-registration.asm) reads the12-byte record and writes the existing registered-pool array at0205d5f8: flags at+0, start at+4, end=start+size at+8, allocator context at+12. This array remains at its original native address below the carve.

[Initializer0433c1ce](../ghidra/memory-capacity/pool-init/function-0433c1ce.c) uses the supplied start, places a16-byte accounting prefix there, and initializes TLSF at start+16. It checks sufficient size for prefix/control/minimum pool overhead. [0433cb62](heap-carve/function-0433cb62.c) initializes TLSF control at the passed pointer and adds its payload pool at that pointer+2000bytes. The minimum-overhead getters return2000 and12bytes, respectively. The new region remains far larger than that minimum. These are relative placements; no old heap base must be retained for allocator bookkeeping.

The following recognized consumers derive bounds/state from the registered array, so they follow the new pool automatically:

- try-allocation0433c294 and capability-aware allocation/reallocation helpers;
- pointer-owner lookup0433c190, which accepts start<=pointer<end only for a live registered allocator;
- free020099a0 and TLSF/accounting paths;
- current free0433c3c6/0433c460 and minimum-free0433c4a4;
- pool inventory0433c4e8 and associated inspection/accounting helpers.

[pool-references.txt](../ghidra/memory-capacity/pool-references.txt) and the existing [memory report](../ghidra/memory-capacity/report.md) enumerate their references. The registry is outside this registered range: it must never be passed to heap free/realloc or treated as an allocator block. Heap pointers stored inside the registry retain their ordinary ownership; reserve storage for pointers does not automatically manage their targets.

## Boundary search and fixed globals

The [raw little-endian literal scan](heap-carve/literal-search.json) searches all extracted component bodies for old base0205e128, proposed base0205e228, old size000a0c98, and fixed end020fedc0. Old base and old size appear only in the one app pool-table record; proposed base/end have no raw literal matches. The [recognized-reference scan](heap-carve/proposed-region-refs.txt) finds no incoming references to addresses in the proposed reservation. The [LUI0205e instruction scan](heap-carve/upper-base-sites.txt) additionally retains nearby native globals and the startup end construction.

Native globals close to the boundary are real and must remain intact, including accesses at0205e124 (the final word before the old BSS end). This carve starts at0205e128 and does not move or resize those native objects. The empty region-reference result is bounded by recovered Ghidra references; it is not proof against every dynamic pointer calculation, other-core address construction, DMA path, memory-corruption bug, or unsupported factory mode. Some LUI scan entries are SRAM/XIP copies of the same native code. Do not count them as independent owners or blindly replace every0205e constant.

The intended allocation pool already owned the whole proposed region, so ordinary correct heap clients could not rely on fixed bytes there. Excluding those bytes from registration and zeroing them before registration is the specific ownership argument. This is stronger than interpreting zero-filled captured RAM as unused space.

## Lifecycle enabled by the carve

A fixed registry inside this explicitly excluded span can remain discoverable across LVGL owner deletion. It can contain ABI/magic, an operation generation/nonce, bounded state/result, and a pointer to separately owned worker/job memory. Initialize it after normal boot clear and before exposing commands, publishing magic/state last under the short native critical section. No stock CUS8 singleton or task slot is repurposed.

For a first canary, a one-operation-per-boot state machine can remain discoverable even if the initiating graphics owner disappears. Host status queries can locate the fixed registry independently of a deleted screen. An active worker owns its private buffers until native operations/required restoration finish; screen deletion must not free them or mark the transaction idle. Completion can be retained until explicit host acknowledgment, while the registry continues to reject a second active operation. A future persistent worker may keep its queue/context pointer here rather than reconstructing ownership from task names.

Only firmware profiles containing both layout edits may access this registry. An unchanged profile still owns these bytes as heap. Mixing a new runtime with an old layout is a real corruption path and must fail constructor/runtime-profile validation, not rely on a lucky magic value. Registry state is not durable across reset: boot deliberately zeroes it. Persistent flash transactions need their own recovery metadata if interruption is to be recoverable.

## Required implementation validation

Before claiming the carve is integrated, execute the real patched startup clear and pool initializer with guarded memory: preserve the final original BSS word, prove all256reserved bytes clear, prove no writes beyond new BSS end, then prove heap registration/TLSF initialization and allocation/free never touch the reserved span. Compare original/new registration end and initial accounting; expected raw-size delta is256, with identical allocator overhead. Exercise native pointer-owner lookup at old/new boundaries. Check both8/16-byte alignment assumptions of registry/worker ABI separately.

Pin exact instruction/table witnesses, unchanged flags/table length, unchanged other components, both edits present together, and rebuilt image integrity. Keep direct references to the registry behind the same build-profile contract; static RX-only extension policy alone does not prove absence of writes to this newly assigned address. Real cold/OTA boot plus fixed read-only registry/heap status can later corroborate initialization, but this review performed no such device action.

## Executed offline guard evidence

Root executed the frozen [native runner](heap-carve/emulate.py) successfully: [full result](../heap-carve-native-001/report.json), [summary](heap-carve/execution-summary.json). Both original and carved variants passed; 74 native calls in total. The real startup clear span, pool constructor, TLSF initialization, owner lookup, allocation, ordinary no-fit, capability filtering and free executed. Only the native short critical enter/exit pair was mocked. The old/new initial accounting differs by exactly256bytes. The carved256-byte registry cleared, then its nonzero guard survived constructor/allocation/free; clear stopped at the new heap front, end/pre-BSS guards survived, and original BSS globals changed only in the existing pool-registration slot during initialization. No firmware image was written or device touched. This narrows the implementation boundary; it is not whole-boot or hardware/interrupt/concurrency evidence.

Reproduce into a new output directory:

```sh
.tools/rv32-tests-venv/bin/python analysis/flash-worker-lifecycle-20261101/heap-carve/emulate.py --output analysis/heap-carve-native-NEW
```
