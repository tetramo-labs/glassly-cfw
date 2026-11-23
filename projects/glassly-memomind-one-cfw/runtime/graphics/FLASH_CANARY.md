# Fixed one-shot normal-worker canary

This optional profile tests one fixed external-flash sector from a dedicated normal task. It is not a flash-store binding, arbitrary writer, recovery service, retry engine or performance claim. Source admission is insufficient by itself: the image constructor must pair the reviewed boot-clear/heap carve and exclusive-owner gates with this exact runtime; the parent workflow separately requires a complete backup and boot validation before a mutating start.

Compile with all prerequisite flags and `--flash-canary`. Its reader identity is `H001Y-1.0.3.127-flash-canary-v1`, retaining the four full-store read ranges and fixed diagnostics. Probe identity advertises `flashCanary:122`, `registryBytes:256`, `writableStaticBytes:256`. The extension ELF still has no writable sections/imports; the separately patched native startup clears the reserved SRAM. The larger probe uses bounded owned scratch to avoid increasing its stack frame. Profiles without the flag retain their prior byte output.

Service15 command0x7a accepts exactly one BYTES TLV:

| Request | Effect |
|---|---|
| `[0]` | Passive status; unlimited queries |
| `[1,0x31,0x4e,0x41,0x43]` | Claim the one boot attempt, validate worker/badmap and read both sectors |
| `[2,0x31,0x4e,0x41,0x43]` | Claim the one boot attempt, run the fixed destructive/restorative canary sequence |

The constant token `0x43414e31` is an accidental-use guard, not authentication. Requests carry no address, length, payload, cancellation or reset. Readonly op1 consumes the attempt, so op2 requires a separately validated reboot. The Python module exposes `CanaryClient.verify_profile()`, `status()`, `validate_worker()` and `run_fixed_canary()`. Start requires an observed idle status and a verified exact profile. A lost/invalid reply poisons the client without retries; a separate readonly status client may later observe the registry. After start, reset-to-idle, operation changes, regressing phase/flags, or changed terminal state are protocol errors.

## Ownership and lifetime

The registry is `[0205e128,0205e228)`, originally heap-owned, explicitly excluded and boot-zeroed by the constructor's three pinned edits. It is8-byte aligned; the40-byte scalar registry needs4. Before any registry read/write the command validates the active pool descriptor at0205d5f8: flags2, start0205e228, end020fedc0, context0205e228. A wrong image returns `wrong-image` without touching the region. Unrecognized nonzero registry contents fail closed. There is no registry initialization/reset that could overwrite an active job.

All registry copies/publications use the brief native critical pair0200a23a/0200a264. No allocation, response creation, task creation or flash/KV operation is inside those critical sections. Idle→starting is atomic and consumes the sole attempt even when allocation or task creation fails. The registry contains no job, task, LVGL or screen pointer. Deleting/changing a screen cannot free worker memory. Status callers only copy scalars.

A676-byte private job is allocated with the existing nonasserting allocator. Admission requires96KiB total free, which covers job,8192-byte task stack,124-byte TCB,12-byte native wrapper,768-byte reply scratch and more than64KiB margin. This is a snapshot of total free space, not a contiguous allocation guarantee or an atomic reservation. The native task constructor and JSON internals still use their normal generic OOM behavior and can assert despite this policy.

The native task call is0200f168(entry,job,5,0x800,"glassly_canary"). It may run to completion before creation returns; the return register is treated only as a uintptr_t boolean, never dereferenced or joined. On success the caller never touches the job again. The worker owns the job, frees it, then publishes terminal scalars from its stack. Native trampoline0200f142 later frees its own wrapper and self-deletes; the idle reaper eventually frees stack/TCB. A terminal registry is logical I/O/job completion, not proof that native task reaping finished.

Both the worker entry and the new command entry have32-byte assembly thunks: save originalSP/RA/s0, alignSP down16, call C, restore originalSP/RA/s0, return. Native gp/tp remain unchanged. This supports incoming SP mod16=0 or8. Only cmd0x7a gets this additional command thunk; other service/display paths retain their existing behavior. The service gate is60bytes, below the fixed64-byte entry window.

## Fixed sequence and failure semantics

Target is device1 physical0x7ff000, length4096. Neighbor is0x7fe000, length4096. Before any mutation, the worker acquires key0x6009 through the reviewed native getter and independently checks present-record length/header/CRC/native validity. Status7 with actualLength0 is the distinct native-defined absent default; any partial getter bytes are discarded and the effective map becomes zero. Other unavailable/malformed cases fail. Actual bad bits for both global sectors766/767 (last map byte bits6/7) prohibit any flash read or mutation. The adapter receives the acquired real tail map; no persistent map or ownership exclusion is forged.

The worker reads all32 pages of target+neighbor and requires every byteFF. Op1 then completes without mutation. Op2 does:

1. Erase target through `mm_flash_native_erase`, including correct alias maintenance and sixteen verified readback pages.
2. Program the first256 bytes with byte[i]=`((i*37)^0xa5)&255`, including the adapter's immediate page readback.
3. Read all sixteen target pages: first page must match the pattern and remaining3840 bytes must remainFF. A collateral target write therefore cannot be hidden by restoration.
4. Erase target again, verify all4096 bytesFF, then verify all4096 neighbor bytes remainFF.

This is100 fallible native read/erase/program boundaries, plus three cache maintenance calls. Every error stops immediately; required cache maintenance still occurs after a failed native mutation as specified by the adapter. There is no automatic restore after an earlier error and no automatic retry. A failed canary may leave target contents changed. Reboot clears the registry but does not repair flash; the allFF precheck would refuse another ordinary canary on a changed sector. The fixed read APIs, backup and a separately reviewed recovery operation remain distinct.

## Status

Successful JSON envelopes use `glassly:"flash-canary",abi:1,result:"ok"` and contain state, operation, phase, signed error/nativeStatus, mapSource, mutationStarted/restored/neighborVerified booleans and the fixed target constants. `mapSource` is0 before acquisition,1 validated persisted record,2 native-defined absent default. State is idle, starting, running, passed or failed. Phase1 admission,2 badmap,3 precheck,4 erase,5 program/full-sector verification,6 restore,7 neighbor verification,8 complete. A failed operation is a valid status reply with `state:"failed"` and a nonzero error, never a success claim. Minimal request errors are invalid, wrong-image, registry-invalid, already-used and allocation-failed. Response allocation failure cannot reset the operation.

## Evidence and limits

Final runtime and evidence are recorded under `analysis/flash-canary/`. Host sanitizer tests include early/delayed completion, scheduling between claim/allocation and job-free/terminal publication, all100 native boundary failures, nominal-success corruption, badmap/preimage rejection and response failures. Actual RV32 executes the command, worker, both thunks, exact descriptor guard, native flash adapter and serializers with guarded memory and mocked native APIs. Both BT/worker incoming alignments are exercised; all callee/RA/SP/gp/tp and callee FP checks pass. Gate-only tests exhaust all256 command bytes and original display/input classes. Strict GM/Python checks consume emitted C and RV32 JSON. These tests do not execute a real scheduler, physical flash, peripheral waits, native interrupts or the native wrapper/reaper; independent stock lifecycle evidence remains relevant.

No native watchdog, cancellation, worst-case latency or cumulative stack bound is claimed. Public native flash APIs contain uncancellable locking/MMIO/busy waits and may assert. Native cache maintenance retains the evidenced call sequence; no new global cache mutex or cross-core atomicity guarantee is invented. The mock-observed worker/BT stack use excludes native and interrupt frames. No device operation is performed by these runners.
