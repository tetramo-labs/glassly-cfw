# Device1 XIP spans and write completion

Pinned stock H001Y app 1.0.3.127, SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`. This is static evidence from the real extracted body and startup-derived SRAM mapping, with a new read-only/noanalysis export. No device operation, runtime edit, or performance measurement occurred. [Provenance](provenance.json), [byte witnesses](byte-witnesses.json), and [machine-readable profile](profile.json) accompany this report.

## Concrete result

Device1 physical offset `p` is read as a CPU XIP pointer at **`0x05000000+p`**, while its unified flash address is `0x01000000+p`. Thus reserved physical `[00700000,00800000)` corresponds to unified `[01700000,01800000)` and CPU XIP `[05700000,05800000)`. The unified address is a flash-address convention; this investigation does **not** establish it as an uncached CPU-readable alias. Do not cast `0x01...` unified addresses to pointers.

The public program and erase wrappers alone do **not** establish device1 XIP freshness. They perform cache maintenance using `physical+04000000` for both devices. Stock CUS8 callbacks add the correct device1 alias maintenance after the public call. A custom writer must preserve that second step, verify completion/readback, and publish a new immutable map epoch only afterward. No evidence establishes unrestricted raw XIP loads while the same flash is programming or erasing.

## Address and cache witnesses

[Raw store callback disassembly](reused/native-store-callbacks.asm) proves:

| Native path | Physical call | CPU alias handling |
|---|---|---|
| Read `042a3e20` | `04329ad8(1,00500000+relative,dst,len)` | No pointer returned |
| Program `042a40c4`, callsite `042a40f2` | `04329b1e(1,00500000+relative,src,len)` | `042a40f6..042a4102` calls `04324bea(0,05500000+relative,len)` |
| Erase `042a411e`, callsite `042a414c` | `04329a14(1,00500000+relative,len)` | `042a4150..042a415c` calls `04324bea(0,05500000+relative,len)` |

The callbacks bound relative offset and length against 3 MiB, clear package-validation flag `02011e50`, perform the operation, perform alias maintenance even when it failed, then normalize status to 0 success / -1 failure. They are **store-owned callbacks**, not recommended custom writer entry points: using them would mutate package state and apply the original store bounds. The shared project lacks function definitions at their exact starts; the retained raw instruction/byte disassembly settles the ABI without creating functions or changing the project.

[Package completion `042a48f0`](reused/function-042a48f0.c) returns `entry_offset+05500000` and its declared length, then frees/nulls the store context. This establishes that the mapping is not owned by that heap context. [Incremental writer `042a3ee0`](native/function-042a3ee0.c) writes bounded chunks through the store and on subsequent progress uses native memcpy directly from `entry_offset+05500000` to inspect the package header. Together these are concrete stock write→correct-alias-maintenance→direct-read witnesses. They do not prove simultaneous read/write behavior.

[Program wrapper `04329b1e`](reused/function-04329b1e.asm) holds the native device lock through program, busy completion, and optional callback; releases it at `04329b6c`; then maintains `physical+04000000` at `04329b70..04329b7a`. [Erase wrapper `04329a14`](reused/function-04329a14.c) performs its same-alias maintenance before unlocking. Do not interpret either lock boundary as publication of fresh device1 XIP data.

`04324bea(cache_index,cpu_alias,length)` tail-jumps to [0432dd00](reused/function-0432dd00.asm). For index0 it subtracts `04000000`, looks up the cache controller at `0200f7f8` (initialized value `01740000`), writes range start aligned down to 32 bytes into controller+80 and exclusive end rounded up to 32 into controller+84, writes control `(old & ffdfffee) | 00200001`, then polls control bit4 until set. For device1 `05700000`, the programmed range starts at unified `01700000`, which is the intended normalization. Passing physical `00700000` or unified `01700000` directly to this helper is wrong.

This operation is the stock range-invalidation/cache-maintenance mechanism, established by its use around mutated flash. No hardware register manual was used to assign additional undocumented meanings to the control bits. There is no software deadline, internal mutex, explicit fence.i, or demonstrated other-core invalidation in this helper. It is not evidence for cross-core executable-code publication. The helper's own frame is 16 bytes; wrapper `04324bea` restores its 16-byte frame before tail-jumping.

## What native locking does and does not protect

`04329912/0432994a` select the device mutex at `0201233c+4*device` when byte `0201233a` is zero, otherwise the stock critical enter/exit pair. Read `04329ad8`, program, and erase use this mechanism. Raw CPU loads from `057...` do not acquire it. Do not acquire the native mutex around a public wrapper, and do not change its lock mode.

Lower SRAM command code waits for controller busy to clear, configures the transaction, and launches it. [020082ae](reused/function-020082ae.c) copies outgoing source bytes into device1 FIFO `01108000` (device0 uses `01104000`) before launching. Public completion [02005b1c](reused/function-02005b1c.asm) polls flash busy and sleeps one scheduler unit between polls. Other tasks can therefore run while programming/erasing is outstanding. Native wrappers have no cancellation deadline; host timeouts cannot revoke a running operation.

The controller and flash might arbitrate/stall XIP requests during writes, but that behavior has not been established here. Native stock writes are evidence of supported stock operation, not proof that arbitrary readers of an erased sector see a coherent snapshot. Reading different sectors of the same chip concurrently also remains unproved. Explicit SPI reads through `04329ad8` are serialized with cooperating writes; they return owned copied bytes. Raw XIP spans bypass that safety property.

Cache controller0 is shared across alias ranges. The maintenance helper contains no private synchronization and stock device0/device1 callers can reach it. This review does not establish a global cache-operation mutex or atomicity against every possible preemption/cross-core operation. Reproduce the established stock completion sequence; do not invent a new long critical section, disable assertions, or claim a stronger hardware ordering guarantee.

## Bounded immutable-span contract

The following is a proposed adapter contract derived from the evidence, not an existing firmware API:

1. Validate the fixed device1 reservation, bad-sector map and map epoch before obtaining any span. Physical mapping must remain per-sector; adjacent logical sectors need not be physically adjacent. For logical position `x`, mapped physical sector `s`, return at most `min(requested,4096-(x&4095),object_remaining)` bytes at `05000000+(s<<12)+(x&4095)`. Reject overflow, out-of-reservation sectors, bad sectors, and stale/uncommitted epochs.
2. A render operation pins one immutable epoch for its entire synchronous traversal, including any two-pass text/layout work. No remap, replacement, erase, or program of its backing storage may proceed until all readers of that epoch have finished. Checking the epoch only after reading cannot repair mixed data or a fault during mutation.
3. A span is borrowed for the bounded callback only. Do not retain it in LVGL image descriptors, timers, event userdata, decoder caches, or cross-task jobs after releasing the pin. Such retention would require a longer-lived explicit owner and deferred reclamation. Copy the final raster into the already-owned display buffer if that is the selected rendering design.
4. One custom normal worker owns mutation. Drain/pause custom XIP readers without blocking the display task; keep the old epoch unpublished for mutation or use independently owned spare extents. Complete native erase/program, perform correct-alias maintenance, perform explicit native readback and integrity checks, and only then publish the new epoch. On any failure, leave the affected epoch unavailable and do not silently continue or retry.
5. Excluding only overlapping custom writes is not proof of chip-level read-while-write support. Conservatively exclude **all custom device1 program/erase** while custom XIP reads run. Stock resource/plugin writers are a separate coordination boundary: this pass does not prove a universal stock-writer exclusion mechanism. An implementation must either establish that coexistence boundary or use copied SPI-read data when it cannot keep the chip in a qualified read-only phase.

The physical pointer remains numerically valid after store-context destruction and across unrelated heap churn; its **contents** are valid only while its allocation/map ownership, flash initialization, and generation remain valid. Reset invalidates all runtime leases. The map/pin mechanism cannot itself confer flash allocation ownership.

## Normal task context for writes

Stock [042a97d4](native/function-042a97d4.asm) allocates and copies an owned job, creates queue `0200ee6a(0xe6,1,4)` at `042a9926`, and creates task at `042a995e` with:

```c
void *create_task(void (*entry)(void *), void *argument,
                  unsigned priority, unsigned stack_depth, const char *name);
// 0200f168: stock uses (042a90ba, NULL, 5, 0x800, "plugin_flash")
```

[0200f168](reused/function-0200f168.c) allocates a 12-byte wrapper, stores entry/argument, and passes trampoline `0200f142` to the native scheduler. [The trampoline](native/function-0200f142.asm) calls `entry(argument)`, frees only its wrapper, then deletes the current task if entry returns. It does **not** free the argument. The stack-depth argument is recorded exactly; this report does not reinterpret it as bytes or establish a new custom worst-case stack bound. Task names may override the requested priority through a native table. Task creation allocates scheduler/stack state and requires a separate lifecycle/headroom review before integration.

[Worker 042a90ba](reused/function-042a90ba.c) blocks on `0200ef04(queue,&job)`, runs store operations in normal task context, and sends the owned completed job to display class16/event4. [Receive 0200ef04](native/function-0200ef04.c) checks native task context and waits with timeout ffffffff; send `0200ee8c` is a zero-wait copy to the queue and returns boolean success. The queue holds copied pointer values, not a deep copy of pointed-to payloads. Stock admission explicitly copies bytes into the allocated job before queueing.

This establishes a concrete suitable **dedicated normal task entry** and owned-job pattern. It does not expose a generic callback slot in the existing plugin worker: stock operations, global busy flags, queue depth1, completion ownership, and job layouts are hardcoded. Do not send invented jobs to that queue or steal its singleton. A custom worker should own its argument/queue/context, use the native ABI and gp/tp, preserve callee-saved registers and 16-byte stack alignment, and keep all native flash calls outside observers, LVGL/display callbacks, interrupt context, and caller-held critical sections. Creating/deleting a custom worker safely is follow-on implementation, not performed here.

## Remaining limits

The translation, correct-alias completion sequence, and normal worker model are concrete. Same-chip simultaneous read/write arbitration, cross-core coherence, universal stock-writer exclusion, cache-operation concurrency under every preemption, custom task stack/heap budget, and sustained render latency remain unmeasured or unproved. No claim is made that zero-copy flash rendering is faster, that all physical reservation ownership is settled by this review, or that this report alone admits a hardware mutation. The smallest defensible next step is an offline map/epoch/span adapter with explicit borrowed lifetime and worker ownership, keeping direct XIP use restricted to a qualified immutable/read-only phase.
