# Display task adapter investigation

**Do not render directly from the Bluetooth handler using the stock raw-slice
API if bounded execution is required.** The stock implementation contains an
infinite semaphore wait and an unbounded scanout-queue retry loop. A small drawing
payload does not bound those waits. This pass establishes an enqueue/dispatch
route and exact drawing/ownership contracts, but does not certify a complete
bounded drawing implementation. No active firmware image or device was changed.

All addresses are pinned to the inspected H001Y 1.0.3.127 app body. The previously
reviewed text/runtime patches preserve these routines. [proof.json](proof.json)
contains compact addresses, structure layouts and proposed hook byte guards.
The SDK reference is `.tools/memomind-open-platform/GlassSDK`, commit
`171098bff25934a534a49f95b88df58fbed404c7`.

## Execute work on the display task

[Initialization 0x0425aa40](queue-init/function-0425aa40.c) creates two separate
queues, each holding eight 4-byte pointers, and starts `display_app_task` at
[0x0425bd9e](deeper/function-0425bd9e.c). The worker drains up to 16 messages,
calls dispatcher `0x0425b38a` at instruction `0x0425c00e`, then frees the envelope
at `0x0425c016`. It subsequently runs application updates and the LVGL processing
path before sleeping. Queue callbacks therefore run before that loop's LVGL pass.

The usable enqueue entry is [0x0425abe8](deeper/function-0425abe8.c):

```c
uint32_t enqueue(uint32_t class_id, uint16_t event,
                 const void *payload, uint32_t length, uint32_t priority);
```

For nonzero class IDs, [0x0425a764](queue/function-0425a764.c) allocates an envelope
and copies `length` payload bytes synchronously. Its layout is class in byte 1
(low 6 bits), event `uint16_t` at offset 4, length `uint16_t` at 6, and inline
payload at 8. Use a small fixed-length command with no pointers or callbacks in
the wire payload. Class zero uses different pointer/cleanup semantics and is
unsuitable for this new inline command.

Candidate class `0x3f` with a private fixed event/magic can be recognized only by
an appended display gate; it is not an existing generic callback service.
Priority **2** is preferable to wrapper `0x0425add2`'s default priority 1:
[0x0425a8b8](queue/function-0425a8b8.c) admits priority 2 only when the priority
queue contains fewer than six entries, and its full-send branch drops the new
message rather than evicting existing display messages. The underlying
[queue send 0x0200ee8c](rtos/function-0200ee8c.c) uses timeout zero and requires
normal task context. Allocation/scheduler locks are still stock operations.

**Return 0 is not proof of queue acceptance or execution:** admission rejection
also returns 0 after freeing the new envelope. Return `0xb` represents several
explicit setup/allocation failures. Keep submissions sparse; do not describe
receipt of an enqueue result as a rendered-frame acknowledgment. A later
execution acknowledgment needs its own reviewed design.

### Preferred callsite gate and byte guards

The preferred second hook is at **0x0425c00a**, body offset `0x70fea`,
replacing exactly `032504f9eff0cfb7`:

```
0425c00a  lw a0,-0x70(s0)
0425c00e  jal ra,0x0425b38a
0425c012  lw a0,-0x70(s0)   // preserved continuation
```

Use an eight-byte AUIPC/JALR call to the appended gate; it sets return address
`0x0425c012`. The gate must first replay the displaced load **before any prologue
changes s0**, then inspect the envelope. Its ordinary path tail-jumps to
`0x0425b38a`, preserving the worker's return address, stack, and arguments. The
custom path returns to the same continuation, where the worker frees the
envelope. Never retain or free that borrowed pointer. Check the exact private
class/event/length/magic; expose no arbitrary function pointer in commands.

[Incoming-reference evidence](worker-hook-refs.txt) finds only the stock branch
from `0x0425bff4` to the start, and no incoming references to the overwritten
interior `0x0425c00e`. Raw aligned/unaligned u32 searches found no encoded pointers
to the start/interior/continuation. This is static evidence, not proof against
unknown computed jumps. Guard all original bytes and instruction boundaries in
the patcher. This design supersedes the earlier dispatcher-prologue hook: normal
messages need no additional stack frame. A compiled gate still needs independent
instruction/ABI review before use.

## Raw framebuffer contract and timing limitation

The native host table at `0x0436609c` is 112 bytes, ABI `0x0100`. Framebuffer
callbacks at offsets `0x20`/`0x24` resolve to
[lock 0x0429a088](queue/function-0429a088.c) and
[unlock 0x04299fc4](function-04299fc4.c). Both require plugin host state at
`0x02011e24`; lock ownership is stored in that lifecycle object at offset `0x34`.
An appended runtime must not fake this state or call these wrappers blindly.

The wrappers expose this lower native contract:

| Function | Contract |
|---|---|
| [0x0425f20e](slices/function-0425f20e.c) | `bool lock(uint32_t y1,uint32_t y2,uint32_t auxiliary,uint8_t *mask)`; inclusive rows, use auxiliary 0; checks display-active before and after acquisition. |
| [0x0425f7fa](slices/function-0425f7fa.c) | `uint8_t *pixels(int x,int y,int auxiliary)`; use `(0,slice_y,0)` only while owning the corresponding slice. |
| [0x0425f292](deeper/function-0425f292.c) | `bool submit(uint32_t mask,const uint16_t rect[4],bool present)`; `rect={x1,y1,x2,y2}` with **inclusive endpoints**, not SDK `{x,y,width,height}`. `rect=NULL,present=false` releases without submission. |

Logical geometry is 600×350, GRAY4 (even x high nibble). **Backing stride is 320
bytes, not 300.** The host exposes two slices: y=0,height=175,mask=1 and
y=175,height=175,mask=2. Native [pointer calculation 0x042adace](slices/function-042adace.c)
is `base + 320*y + (x >> 1)`. Never repurpose the backing padding or retain a
pointer after relinquishing its slice. For a one-slice update, keep all rectangle
coordinates within that slice and x=0..599, y=0..349. Draw through the returned
pointer; no full-screen allocation is needed.

For a valid owned mask, submission transfers responsibility for release into
the stock transfer pipeline. `present=true` adds the display SYNC. Earlier
slices of one frame use false, the final slice true. Cancel or invalid rectangle
paths release the mask. Do not unlock twice. A return of 1 means stock submission
processing completed; disabled-display paths can release without sending, so it
does not prove physical pixels appeared.

The timing hazards are concrete:

- [0x042ac4be](ownership/function-042ac4be.c) acquires slice semaphores using
  `0x0200ed78(handle,0xffffffff)`; no finite timeout.
- Submission can take a stock mutex via
  [0x0200ec3a](rtos/function-0200ec3a.c), whose 60,000-unit timeout asserts on failure.
- [0x042ac430](transfer/function-042ac430.c) retries indefinitely while the scanout
  queue has more than one entry or its send fails, sleeping one tick each time.
- [0x042ad52e](ownership/function-042ad52e.c) attaches release masks to transfer
  nodes; [0x042ac360](ownership/function-042ac360.c) returns the semaphores.

[slice-callers.txt](slice-callers.txt) includes plugin-host, display/rendering,
and `bt_data_report` routines (`0x042eeea6`, cleanup `0x042ec56c`). The latter are
real call references, but their complete thread provenance was not established;
they do not prove arbitrary BT-handler use is bounded or safe. No caller-only
search can eliminate the explicit waits above.

## Allocation and system UI coexistence

Generic allocation/free are [0x0434e6da](slices/function-0434e6da.c) and
[0x0434e6ee](slices/function-0434e6ee.c), wrapping stock heap allocation/free.
Host-table alloc/free instead use plugin lifetime tracking at `0x02011e64`.
That context is lazily created, so allocation may succeed outside a plugin, but
its ownership/cleanup is unsuitable for persistent appended-runtime state.
Use generic allocation with explicit ownership, or keep first commands entirely
inline/stateless. Do not claim any new static RAM reservation.

For a conservative first render, evaluate both
[base application 0x0425db22](ownership/function-0425db22.c) and
[top application 0x0425daf8](ownership/function-0425daf8.c) on the display task;
proceed only when both equal the stock launcher descriptor `0x0200fc7c`.
[0x042a8834](ownership/function-042a8834.c) independently uses the same base-app
comparison. Skip otherwise, including phone-call, notification/system overlay,
and other app states. The slice lock's active-display guard covers shutdown
transitions for that operation; it is not a comprehensive wearing/visibility API.

SDK `SYSTEM_EVENTS.md` specifies cooperative yielding during phone UI. The
native subscription [0x0429999a](deeper/function-0429999a.c) requires an active
plugin root and validates the callback, so it is not a general runtime listener.
The SDK also forbids any LVGL call while a framebuffer slice is held. A later
LVGL refresh can overwrite raw pixels in overlapping areas, including a refresh
later in the same display-worker iteration.

## Retained image rendering on the display worker

Use raw LVGL image objects and let the ordinary worker refresh drive scanout.
This avoids invoking the blocking raw slice API directly. These addresses are
native APIs established from stock callsites, not the lifecycle-dependent SDK
image wrapper.

| Entry | Minimal contract |
|---|---|
| `0x042d01b2` | `void *default_display(void)` |
| `0x042ccc62` | `void *active_screen(void *display_or_NULL)`; returns display+0x10, or NULL |
| `0x042bd7d0` | `void *image_create(void *parent)` |
| `0x042bd7fa` | `void image_set_source(void *image,const native_image *source)` |
| `0x042c963e` | `void obj_set_pos(void *obj,int32_t x,int32_t y)` |
| `0x042c96ec` | `void obj_set_size(void *obj,int32_t w,int32_t h)` |
| `0x042cf61c` | `void obj_delete(void *obj)`; only delete owned children |
| `0x042cf44e` | `void *obj_get_child(void *parent,int32_t index)`; checked, negative indexes supported |
| `0x042cf47a` | `uint32_t obj_get_child_count(void *parent)` |
| `0x042c7894` | `void *obj_add_event_cb(void *obj,void (*cb)(void *event),uint8_t filter,void *user_data)` |
| `0x042c7854` | `void *event_get_user_data(void *event)`; event+0x0c |
| `0x042c7834` | `uint32_t event_get_code(void *event)`; event+8 masked with~0x80 |
| `0x042b68c8` | Stock image-cache-invalidate entry; **no-op in this exact build** |

Evidence: [native-image](native-image/), [events](events/), [lookup](lookup/),
[event-api](event-api/). Stock system UI obtains the active screen through the
first two getters at `0x042826ca`/`0x042826ce` before creating a child.

The 12-byte, four-byte-aligned native descriptor is:

```c
struct native_image {
    uint32_t header;     // (height<<21)|(width<<10)|9, reserved bits zero
    uint32_t data_size;  // 64 + ((width+1)/2)*height
    const uint8_t *data; // four-byte aligned
};
```

The encoding is directly emitted by SDK converter
[0x042999ee](image/function-042999ee.c). Format 9 is native indexed 4-bit;
SDK enum 1 is not interchangeable with that header value. The 64-byte palette
is 16 BGRA8888 entries, then tight packed rows, even x in the high nibble. Palette
alpha can reveal stock content. For a static 128×64 proof, data is 4160 bytes,
header `0x08020009`; immutable appended descriptor/pixels avoid borrowed heap
lifetime problems. For dynamic geometry, rasterize into an owned allocation
before setting its source. Do not confuse this tight image stride with the
physical framebuffer's 320-byte stride.

[0x042bd7fa](native-image/function-042bd7fa.c) stores the descriptor pointer at
image+0x2c for variable-source type 0; it does **not** copy descriptor/pixels.
Both must outlive the image, including future refreshes. The SDK image wrapper
`0x0429a6e6` is unsuitable directly: its attachment helper
[0x0429a598](image/function-0429a598.c) requires plugin state `0x02011e24` and
links resources into that lifecycle.

### Owned deletion and replacement without global RAM

Attach a fixed compiled callback with filter **0x21 (DELETE)** and an owned
context as event user_data. Stock [delete core 0x042cf4de](lookup/function-042cf4de.c)
sends that event before recursive deletion/class destructors. The stock SDK
[callback 0x0429a1fe](events/function-0429a1fe.c) obtains user_data, invalidates
its context magic, and frees descriptor resources plus context using the generic
heap pair. Its descriptor invalidation call `0x042b68c8` is a 12-byte no-op in this
build ([assembly](completion/function-042b68c8.asm)); retaining that call preserves
the stock cleanup sequence without claiming there is an active image cache.
A single allocation containing context, descriptor, palette and pixels makes
ownership straightforward. Only the DELETE callback frees it after attachment;
pre-attachment failure paths retain caller ownership. Never free immutable flash.

To locate an existing owned child, enumerate the parent's children on this same
serialized display task. A pinned-layout, read-only tag search can compare each
child's registered callback to the **fixed compiled DELETE callback address**:

```
spec = *(void **)(child+8);              // NULL means no descriptors
count = (*(uint16_t *)(spec+0x22)) & 63;
descriptors = *(uint8_t **)(spec+0x0c);  // count records, each 12 bytes
record: callback u32@0, user_data u32@4, filter u8@8
```

Both event add `0x042c7894` and remove `0x042c7988` establish this layout. Only
a matching callback/filter identifies an owned context; do not dereference
arbitrary children's user_data looking for a magic value. No exported event
record getter was established in this pass. After deleting a match, rescan or
iterate children backwards because deletion compacts the array. Do not mutate
the descriptor table directly. An immutable-image proof can instead use a fixed
flash tag as user_data and a no-free callback.

Native object/event allocations are not uniformly graceful on OOM: event-add
reallocation failure asserts in an infinite loop. Keep object count and image
bounds small; a successful generic pixel allocation does not guarantee all
subsequent LVGL allocations. This interface avoids raw scanout waits but is not
a universal hard-real-time guarantee.

**Lifecycle limit:** active screen is a verified parent, but a launcher check
at creation alone does not remove its child on a later phone call/notification.
Persistent overlay coexistence needs explicit clear/yield/transition handling.
Do not claim launcher/base/top gating alone proves future UI coexistence. No
free static RAM slot, startup hook, plugin root fabrication, or framebuffer lock
is required for the minimal retained-image path described here.

## Acknowledge execution from the display task

The stock plugin worker `0x042a90ba` sends class0x16/event4 back to the display
queue via `0x042a8f66`. The display dispatcher calls
[0x0426223c](completion/function-0426223c.c); its command0xb0 branch builds TLVs,
then calls the following sender and immediately frees its own TLV list:

```c
uint32_t send_gm(uint8_t event, uint8_t service, uint8_t command,
                 void *tlv_list, uint32_t route); // 0x042e866e
// send_gm(original_event, 0x0f, private_command, response, 1);
// tlv_free(&response); // 0x042eff8e, even when sending fails
```

[0x042e866e](completion/function-042e866e.asm) fixes frame type0xfa and forwards
all five arguments to `0x042e61cc`. It returns0 if the connection flag through
`0x020120f8` is false. Route1 matches stock display completion: it queues BT
class0x0d/event0x3b. [Serializer 0x042f008a](completion/function-042f008a.c)
**copies** input TLV bytes into independent framed packets. The sender then
queues copies of those packets and frees its temporary packet list using
`0x042f0054`; it never owns/frees the caller's TLV list.

[0x04235a9c](completion/function-04235a9c.c) allocates the BT envelope and copies
the packet synchronously. [0x0423608e](completion/function-0423608e.c) tries to
enqueue at most five times from a non-BT task, sleeping five ticks between failed
attempts. On the third failure it calls `0x04235d94(400)`, which only raises a
shared work-budget value under a critical section and signals a semaphore; it
does **not** sleep 400 ticks. Thus the explicit retry sleeps total at most20
ticks per packet, apart from stock allocator/scheduler/logging costs. Failure
frees the unsent BT envelope. Keep replies below one packet (503 payload bytes)
for a small latency footprint. The raw route0 path has different reserve/flush
semantics and is outside this minimal interface.

Return1 means all serialized packet copies were queued; it does not prove the
phone received them or the panel physically updated. For a queued command, copy
the original request event into the bounded job, clean the original request TLVs,
and leave the immediate response NULL. Only after the display callback has
validated its guard and completed the object operation should it send its
correlated success/error. Queue drops or transport failures remain client
timeouts; enqueue return0 must never be promoted to completion. An execution
reply means the LVGL state changed, with physical presentation left to the
ordinary subsequent refresh.

## Timer lease and final input profile

The native LVGL timer APIs are [create 0x042b27ca](timer/function-042b27ca.c)
`void *timer_create(void (*callback)(void *timer),uint32_t period,void *user_data)`
and [delete 0x042b285a](timer/function-042b285a.c)
`void timer_delete(void *timer)`. The 24-byte timer stores period@0, last-run@4,
callback@8, user_data@12, signed repeat-count@16, paused-bit0@20. Create initializes
repeat-count=-1 (indefinite). `0x042b2b00(timer,count)` changes repeat count;
`0x042b2b0e(timer)` resets last-run; `0x042b2adc(timer)` marks ready. A separate
user-data getter was not established: a pinned-layout read at timer+12 is proven
by create and by stock refresh callback [0x042cc63c](timer/function-042cc63c.c).

[Timer handler 0x042b288c](timer/function-042b288c.c) invokes callbacks with the
timer pointer in a0 and checks the global deletion flag before accessing the
current timer again. Timer-delete unlinks/frees and sets that flag, so callback
self-deletion is explicitly accommodated. It also restarts enumeration when
timers are added/deleted. Do not retain a freed timer pointer or combine automatic
one-shot deletion with a context that still thinks it owns that timer.

A minimal coordinated ownership design, **not implemented here**, is:

1. Allocate one owner containing the image pointer, timer pointer, native image
   descriptor/pixels, starting tick, and lease. Create the image on the display
   worker, attach its fixed DELETE callback, and then create its repeating timer.
2. The timer callback reads owner from timer+12. Check current base/top launcher,
   active-screen identity versus the stored parent, and elapsed lease. On any
   invalidation, call `obj_delete(owner.image)` and immediately return. Do not
   touch owner or timer afterward.
3. The image DELETE callback obtains owner through `event_get_user_data`, clears
   owner.timer before deleting that timer, then invalidates/frees image resources
   and owner exactly once. Natural parent deletion therefore cancels the timer;
   timer expiry enters the same cleanup route. No writable-global RAM slot is
   needed. Never delete the active screen itself.

Timer create, like event-add, asserts on OOM. Keep creation serialized on the
display worker; callbacks must not wait for BT work or perform raw scanout locks.
This design supplies a short-lived overlay and eventual yield, **not atomic
call-overlay exclusion**: cleanup happens at the next timer callback. If the
worker/timer loop is suspended, expiration is delayed until it runs again. It
must not be described as a hard wall-clock guarantee or zero-frame overlap.

`uint32_t tick_now(void)` at [0x042d02c6](timer/function-042d02c6.c) delegates to
[0x0200f6e8](timer/function-0200f6e8.c), which reads scheduler tick
`0x020123d8`. `0x042d02d8(start)` computes unsigned modulo-32-bit elapsed ticks.
Use `(uint32_t)(now-start) >= lease` with bounded lease below2^31; do not compare
absolute unsigned deadlines across wrap. Stock timer creation uses periods such
as50/1000/3000 ([callsites](timer/create-callers.txt)); the follow-up below establishes the stock hardware rate at1000Hz (1ms per tick).
Timer scheduling can still be delayed by task execution or suspension.

The task has **8192 bytes of allocated stack**: init passes0x800 to
[0x0200f168](timer/function-0200f168.c), and underlying
[0x0200c4f2](timer/function-0200c4f2.c) multiplies that word count by4. Priority
argument5 can be overridden by a task-name table. The worker itself reserves
128 bytes; timer handler reserves80 bytes. These are fixed frame witnesses,
not complete worst-case stack usage: native callbacks/rendering/allocator/event
nesting and interrupts still consume stack. Put image buffers on heap/flash,
keep C frames small, and inspect compiled stack usage before any new pilot.

### Strict one-BYTES request extraction

The service hook ABI remains `(uint32_t command,void *request,uint8_t *event,
void **response)`. Copy `*event` while in the BT callback; both this pointer and
the request list are borrowed beyond the callback. A TLV node is `{next@0,
header_pointer@4}`, both32-bit. The pointed header is `{type:u8@0,
length:u24 little-endian@1..3,data_pointer:u32@4}`. This is the internal layout,
not the wire's big-endian length field. It is established independently by
[allocator 0x042efe44](../append-hook/tlv/function-042efe44.c) and
[parser 0x042f0306](completion/function-042f0306.c).

For raw **mode 36** geometry, 36 is the mode identifier, not a byte count.
Require exactly one node: request!=NULL, next==NULL, header!=NULL, type==1,
2<=decoded length<=5102, data!=NULL. Then require data[0]==36 and
length==2+20*data[1] (count is u8, at most255). The previous fixed36-byte example
was incorrect for this geometry format and is superseded here. Reject
missing/extra/type/length errors before copying or parsing. Read packed length
bytes explicitly. Copy the validated variable-length data and original event
into the bounded display job, then free the original list through
`0x042eff8e(&local_request)`. Do not queue pointers into original request storage.
Payload semantics/coordinate/overflow validation are an additional requirement
for the geometry implementation, beyond the native list contract.

No standalone raw image-source getter was established. The setter stores its
variable-source pointer at object+0x2c, and the native image destructor reads that
field. For an object already proven to be our image, a pinned-layout source read
is supported, but child discovery should use the fixed callback tag described
above and must not inspect image fields on arbitrary stock objects.

## Integration follow-up: timing, memory and geometry admission

### Stock scheduler tick is 1ms

The complete static chain now establishes **1000Hz**:

- Scheduler start calls `0x0200d7fe` ([callsite](memory/tick-1000hz-callers.txt)),
  which passes1000 to registered setup through `0x0200f0ec`.
- Early startup `0x041fb27e` registers setup `0x0434a616` using `0x0200f124`
  ([registration](memory/tick-config-register.txt)).
- [0x0434a616](memory/function-0434a616.c) reads the16000000Hz clock through
  [0x0432565c](memory/function-0432565c.c), then calls
  [0x0200af34](memory/function-0200af34.c). This writes hardware reload
  `(clock/rate)-1`, therefore15999. Callback `0x0434a498` reloads the same rate.
- Interrupt path `0x02008cf0` calls `0x0200d810`
  ([callsite](memory/systick-callers.txt)), which calls
  [0x0200bd44](memory/function-0200bd44.c) to increment the scheduler tick.

This is configured firmware timing, not a live oscillator measurement. Use the
existing tick API and wrap-safe elapsed arithmetic; do not read hardware timer
registers or change rate. The earlier sender bound of20 explicit retry sleep
units corresponds to20ms of requested delay, not a hard upper bound on wall time.

### Native allocation contracts and remaining LVGL risk

The following API does provide a **native ordinary-no-fit return without calling
the allocation-failure hook**:

```c
void *try_alloc(uint32_t size,uint32_t capability_mask); // 0x0433c294
void free_owned(void *ptr);                            // 0x020099a0
uint32_t free_bytes(uint32_t capability_mask);          // 0x0433c3c6
uint32_t total_free_bytes(void);                       // 0x0433c460
uint32_t sum_pool_minimum_free_bytes(void);             // 0x0433c4a4
```

For the appended runtime use capability_mask0, nonzero bounded size, and no
special alignment flags. Returned pointers are at least4-byte aligned. Guard
size arithmetic before calling; sizes below0x1ffffd avoid the TLSF `size+3`
round-up limit/overflow, and the proposed image is far smaller. A bound does not
guarantee pool capacity. This is the same lower entry called by generic
`0x02009904`; it is not a replacement allocator or modified failure policy.

[0x0433c294](memory/function-0433c294.c) enters the stock nested critical section
`0x0200a23a`, scans the five registered pool slots, matches capability flags,
and calls `0x0433c24c`. It releases `0x0200a264` on success **and** all-pools-failed.
[0x0433cb96](memory/function-0433cb96.c) returnsNULL on ordinary no-fit; its
assertions guard internal allocator corruption/invariants. Pool free accounting
and low-water accounting are updated by `0x0433c24c` exactly as for normal malloc.
[Free 0x020099a0](memory/function-020099a0.c) finds the registered pool, restores
its accounting, and calls TLSF free under the same critical section. Use only
pointers this allocator actually returned and free once.

`0x0200a23a` saves/disables MIE and increments a nesting counter;
`0x0200a264` decrements/restores it. The try-allocation operation itself is atomic
with respect to this core's interrupts/tasks. Do not surround LVGL operations,
rendering, logging or large memory copies with an extra interrupt-disabled span.
No cross-core allocator guarantees beyond this stock implementation were proved.

The generic convenience allocator **does call the OOM policy** after lower
allocation failure: `0x02009904` calls `0x0433c174`. Startup at `0x0424bd28`
passes3 to `0x0434d050`, registering callback `0x0434d020`
([startup](memory/perf-init-callers.txt), [registration](memory/oom-register.txt)).
That callback invokes assertion dispatcher `0x041fd1ae` with `perf_monitor.c`,
line28 and size/capability context. Do not assume that callback returns harmlessly.
The lower try-allocation avoids invoking that callback on ordinary failure
without changing/disabling it globally.

Free-total counters are backed by allocation decrement/free increment and read
under the native critical section. They are **snapshots**, summed across pools;
`sum_pool_minimum_free_bytes` is a sum of per-pool minima, not necessarily a
simultaneous global minimum. No public largest-contiguous-block accessor was
established in this bounded pass. Raw TLSF pool walking/introspection would need
a further API/locking contract; it is not required to attempt a bounded allocation
through the verified lower entry.

This does **not** make LVGL metadata construction fallible:

- `0x042cf7ee` allocates the image-class object and grows its parent's child array;
  some child-array allocations/reallocations are used without a NULL check.
- `0x042cdf0c` asserts if the36-byte object special-attributes allocation fails.
- `0x042c7894` reallocates a12-byte event record and asserts on failure.
- `0x042b27ca` allocates a24-byte timer plus list bookkeeping and asserts on failure.
- [0x042b3ad0](memory/function-042b3ad0.c) manages16 shared render scratch slots;
  it asserts on exhaustion or failed growth. Future rendering can allocate even
  after image/event/timer creation succeeds.

The shared allocator cannot consume a caller-owned reserve as LVGL metadata;
freeing a temporary reserve then constructing objects is not an atomic guarantee.
Creating metadata first and allocating pixels via `try_alloc` last reduces the
chance that the new large buffer starves construction and permits pixel-allocation
failure cleanup, but does not remove existing/native later-allocation risks.
No supported API for caller-supplied image/event/timer storage or an atomic LVGL
reservation was found. Do not fabricate internal objects, alter global allocator
hooks, or suppress assertions. Reusing already-created owned objects may reduce
allocation churn but still needs source-update/refresh and lifetime review.

### Service0xf/command0x7d and maximum request

[Stock handler 0x042e4680](../dispatch/function-042e4680.c) implements0x20..0x2f
except0x29. Command0x7d follows the unknown-command branch, frees request TLVs,
and builds STATUS2. Thus this exact stock service has no conflicting0x7d action;
this is not a claim about other services/firmware versions.

[Parser 0x042f0306](completion/function-042f0306.c) checks
`(declared_full_length-9) < 0x13ff8`: the maximum accepted declared full length is
81920, leaving81911 bytes of TLV stream. Each TLV independently must be<=81920
and fit the remaining stream. Therefore one BYTES TLV can contain at most81907
bytes after its4-byte TLV header. The geometry maximum5102 means declared full
length5115 and is structurally admitted. The special zero-copy8192-byte path is
limited to service0xf/command0x2e/type1, so **does not apply to0x7d**.

For command0x7d, parser allocates a data staging buffer of5102, then TLV allocator
`0x042efe44` allocates5118 bytes and copies it. These briefly coexist (10220 bytes
plus other framing/scheduler overhead); staging is released after insertion.
A copied display job later adds another~5110 bytes while the original TLV may
still exist. The graphics pixel allocation must be budgeted separately. Parser
and queue allocations still use the generic OOM-hook path; lower try_alloc for
pixels does not change that. Host-side5102 limits and sparse/in-flight-one
requests limit demand, but do not prove safe memory headroom on the device.

The exact geometry contract is one BYTES node, length2..5102,
mode byte36, count byte0..255, length==2+20*count, followed by the portable
validator's primitive/type/coordinate/overflow rules. Reject extra nodes and
trailing bytes. Copy original event and data before freeing borrowed request
storage. This supersedes the earlier mistaken length36 example.

Search boundary: native heap wrappers `0x0433c174..0x0433c5a8`, their TLSF allocate/
free paths, LVGL object/specattrs/event/timer construction and scratch allocation,
stock tick setup/ISR chain, and service0xf/parser branches above. No device
memory statistics, live allocation experiments, modified image or device actions
were performed in this pass.
