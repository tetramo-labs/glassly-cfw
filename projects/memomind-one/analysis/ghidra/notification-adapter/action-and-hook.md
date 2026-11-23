# Outgoing ANCS action and pre-stock hook proof

This follow-up closes the native action-copy and execution-task questions. It does not implement or flash an adapter. Source targets are the stock app segment SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8` and Bluetooth segment SHA256 `f45213d4f98f48fb45af137689989a7c29e785d79a2bd94b2519e8bcc7dacf1f`.

The Bluetooth segment was imported into a separate `analysis/ghidra/projects-bcore` database, never the shared app project. [B-core provenance](bcore/provenance.json) records the real raw binary, RV32 little-endian loader, `0x14010020` metadata-derived base and startup-derived RAM mappings/gp. Initial disassembly proves the copies and register setup; no synthetic ELF or firmware bytes were introduced. Ghidra initially mistook a function-pointer tail dispatch for a switch and merged handlers into one decompilation. `bcore/scripts/RepairCommandTail.java` corrects only the isolated database's flow annotation/function boundaries using raw instructions `1406337a..1406338c`. Use `bcore/action/function-1406334e.c`, not the earlier merged export, for the corrected dispatcher.

## Exact action contract

App-side callable: `uint32_t action(const uint8_t peer[6], const uint8_t uid_le[4], uint8_t action)` at `0x04318ee6`. It builds an 11-byte stack payload `[peer6][UID4][action1]` and calls `0x043199d2(0x2c0, bytes, 11)`. Its assembly preserves the returned a0. Native does **not** check action <=1 or validate UID existence; the portable adapter must enforce its existing action-0/1 contract and validate an observed UID/peer association.

`0x043199d2` rejects disabled/global-busy Bluetooth states and maps **every nonzero lower result to 11**. Thus this public wrapper returns 0 (queued) or 11 (rejected/unavailable), not the detailed B-core codes below. `0x04316d00` tail-jumps to `0x0434b3a4`.

`0x0434b3a4` forms four words `[result=0, command, payload_pointer, length]` on the caller's stack and calls `0x0434b160(core=1, service=0, argc_including_result=4, words_pointer)`. This is synchronous RPC, not an inline deep copy of every input. The RPC layer holds a per-core mutex, sends a 12-byte descriptor containing the argument pointer, waits on its semaphore for `0x4b0` scheduler ticks, and returns after acknowledgment. Missing service can trigger connection lookup/retry; normal timeout or IPC send failure asserts. Do not call it from a display observer, ISR, queue lock, or teardown callback that must not wait. The exact API cannot honestly be advertised as a nonblocking try-action.

On B-core, `0x10226dda` copies the 12-byte RPC descriptor into its local queue and wakes `rpc_task`. Initializer `0x140dfb08` creates worker `0x140df7ce`, priority argument 9, stack-depth argument `0x200`. The worker reads the shared words, invokes the selected handler, stores its result to word 0, and only then sends ACK. RPC service-0 table entry `0x10230ec4` is `0x140e3610`; registration `0x14064b80 -> 0x140e36be` installs user command dispatcher `0x1406334e` at `0x10231d58`.

The sorted command table at `0x140e6790` has 12-byte records `[command, handler, auxiliary]`. [Raw table witnesses](bcore/action-table-witnesses.json) prove command `0x2c0` maps to `0x14061760`.

`0x14061760(payload, length)`:

1. Asserts unless payload is nonnull and length is exactly 11.
2. Requires native ANCS active byte `0x10233b3c == 1`, peer6 equality with `0x10233b40`, and `0x1407e90e(0x0d) == 3`.
3. Allocates a 44-byte message payload through `0x1407e190(0x0d07, 0x0d, 0, 44)` (plus its 16-byte message header and allocator overhead).
4. Writes kind byte 2 at +0, **copies** UID4 to +1..4, and copies action byte to +5.
5. Enqueues the owned message through `0x1407e27e(message, 0)`, then returns 0. Failed readiness returns 1; the apparent allocation-failure branch returns 4, but the allocator itself asserts on failure before its caller can reliably recover.

Therefore the original stack peer/UID/action storage is no longer retained when a successful RPC returns. Only the copied UID/action live in the owned queued message. This is the requested copy-before-stack-return proof, not an assumption based on the wrapper's local array.

`0x1407e27e` links the message into the native ready queue under its critical section and wakes the service task through `0x1407df8a`. There is no bounded queue-admission failure returned by that void enqueue helper. Native allocation assertions remain a real limitation; no global OOM hook is disabled or bypassed.

## Execution, validation and completion

`0x1404689e` creates `bt_service` task at `0x14049fc0`, priority argument 6, stack-depth argument `0x200`. That task initializes the native message engine and loops in `0x1407ded6 -> 0x1407e076`; event 0 invokes `0x1407e6ba`, which drains ready messages through `0x1407e576`. This task is distinct from the RPC worker and the app/display workers.

ANCS module 13 is registered by `0x140589fa`: dispatcher `0x1407f12e`, state descriptor `0x1022ea80`, state-3 handler `0x1405869c` (table entry `0x140e6254`). The generic state dispatcher rearranges `(message,payload,destination,source)` into the state handler's `(message,destination,source,payload)`. For message `0x0d07`, readiness flag bit 0 must still be set. Kind 2 invokes `0x14075998(connection_record, payload+1)`.

`0x14075998` rejects a busy control transaction (`0x1023168e != 0`). Otherwise it sets busy and builds the six-byte ANCS control-point value `[2][UID4][action1]`, then calls `0x1407c6d0(connection, handle_at_102343f0, six_bytes, 6, 1, 2)`. The latter resolves a connection and routes an ATT write (opcode 0x12 on its ATT API branch); its alternate branch copies pending write data to owned storage. This proves action-to-control-point construction, not that a remote phone accepted or performed it. The lower ROM ATT implementation is outside these extracted-image exports.

A later failure/busy/readiness rejection can occur **after** the app received return 0. Consumer `0x1405869c` reports through `0x14066b60`: event `0x259` with `[peer6][status_byte]`, length 7. Stock app `0x04211abe` uses that event to drain its pending requests. It contains no UID or action discriminator, so it cannot uniquely acknowledge an arbitrary concurrent custom action. A native adapter must preserve stock ordering and allow at most its explicitly tracked outstanding operation; neither immediate return 0 nor event259 alone is proof the requested UI action happened.

Stock app pending list at `0x02011604` supports request types 0/1/2 in `0x04211494`, and clears peer requests on disconnect. The examined references show constructors for types 0/1 but no existing type-2 producer API. The native type-2 queue format is next pointer+0, previous+4, type byte2 at+8, peer6 at+12, UID4 at+18 and action byte+22, within a36-byte node. Its consumer removes/frees the node, and disconnect cleanup also removes/frees it. Reproducing that submission is possible only on the same serialized app worker with allocator compatibility and linked-list/busy invariants tested; this pass does not install such a producer. `0x042113ce` is not a pure lookup: it may create/reassign a peer slot, so it must not be called casually from a passive observer. An integration should use its own bounded action queue and dispatch only from an admitted app-side task, with peer/connection generation and busy/ordering policy. It must also avoid retrying an action merely because an ambiguous completion timed out.

The same RPC copy proof closes attribute-request borrowed pointers: command2be→`0x14063e6e` copies UID and at most14 attribute-spec bytes into an owned message; command2bf→`0x14061646` copies an identifier of at most39 bytes and at most1 attribute byte. Exact outer payload sizes are20/24. These lower limits are not the portable relay's1024-byte incoming attribute bound. Invalid outer sizes assert. No new attribute requests were sent in this investigation.

## Concrete pre-stock incoming hook

The existing display-worker gate `0x0425c00a` cannot observe raw ANCS before cleanup: source/attribute events execute on the separate topic-0 app worker. The display gate can receive **new copied jobs** or observe companion GM messages, but it does not contain the original ANCS source/attribute buffers.

A concrete additional callsite is `0x04217568`, inside stock Bluetooth callback `0x04217546`:

```
04217568  auipc ra,0x102
0421756c  jalr  ra,ra,0x22a    # original target04319792
04217570  ...                # continuation
```

Original eight bytes: `97 20 10 00 e7 80 a0 22`; body offset `0x2c548`. Registers a0/a1/a2 still carry event/payload/length. [Reference export](prestock-hook-refs.txt) shows a conditional branch landing at04217568; no references enter the second instruction or continuation in the examined project. [Hook profile](prestock-hook.json) records the exact target hash and witnesses. No bytes have been patched.

An appended callsite wrapper can recognize events258..25b, synchronously validate/copy bounded data, restore its original argument/return state, and tail-forward to04319792. Ordinary events can directly tail-forward. The original helper returns without ANCS-specific processing for these IDs; afterward the unchanged router invokes the stock ANCS handlers and frees nested data. This avoids app-bus callback registration and its eviction/post-free risks. No subscriber, pointer table, or native payload needs replacing.

The hook must preserve stack alignment, gp/tp, callee-saved registers, original return04217570, and the original helper's argument contract; audit the actual compiled gate and reference set before use. Its callback must not send Bluetooth, call synchronous actions, block on the display task, or retain the event/descriptor/body pointer.

A viable ownership split is a **stateless producer of copied jobs** plus a display-owned relay: put only peer/UID/command/length/bytes and an explicit version into a bounded owned job, forward stock, then let the existing display gate find the current relay owner and consume or discard it. Late jobs must not carry a freed owner pointer. Destruction removes the owner on the display thread; it does not free a context still referenced by an app hook. Retained ANCS source generations/UID-to-peer associations must invalidate on state change/disconnect.

Existing `0x0425abe8` copies class63 payload inline before returning, and the display worker owns/frees that envelope. However its allocator can assert, it can drop priority2 jobs, and it can return0 after a drop. A future bridge must make drops explicit, bound notification bursts/bytes, include queue-copy headroom, and never treat enqueue as delivery. Posting one raw descriptor with a borrowed nested pointer is forbidden. The present evidence does not establish an atomic allocation reservation or a no-OOM guarantee for such a bridge. A relay shared across the app and display tasks needs additional serialization/lifetime proof; the single-display-owner design avoids retaining a cross-task context but still needs bounded job admission.

## Admission status

Resolved: real action callable and result mapping; copy-before-return; active-peer validation; RPC versus service execution task; message/control-point ownership; busy and completion semantics; exact pre-stock callsite without subscriber eviction; display gate's limited role.

Still required in an implementation review: compiled gate/forwarding tests; bounded cross-task copy/drop accounting; peer+UID generation/action validation; action/control serialization with stock transactions; lease/timer teardown; actual MemoMind relay envelope; allocator headroom policy (including native B-core assertions); and real notification/action tests. No iPhone/ANCS or Android notification was sent, no action was performed, and no hardware parity was claimed.
