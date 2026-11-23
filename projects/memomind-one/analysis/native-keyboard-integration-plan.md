# Native keyboard integration plan

The smallest complete adapter should keep the stock HOGP accessory manager as the sole radio/security/discovery owner, run the unchanged portable keyboard core on the stock app worker, and observe original ATT values before HID normalization. It needs an owned transaction arbiter and a separately scheduled sender. The current GM HOGP gateway and cooked-input observer are useful diagnostics, but neither supplies the full G2 keyboard contract.

This is a read-only design based on existing source and native exports. No production/test/firmware source or device state was changed. Addresses refer only to H001Y1.0.3.127, stock app-body SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`. See `ghidra/keyboard-adapter/report.md`, `profile.json` and hashed export provenance; SDK commit is `171098bff25934a534a49f95b88df58fbed404c7`. Existing direct-Ghidra RV32 evidence is identified honestly; no new REA/Ghidra export was required here.

## Preserve the actual G2 semantics

The production core is `runtime/portable/keyboard.{c,h}`. The original six host scenarios and86 assert expressions,966 evaluations and20,000 malformed trials remain the baseline. Eight ARM/native adapter scenarios remain pending; compiling the portable core on RV32 does not pass those scenarios. The upstream TypeScript client/parser in `tests/g2_compat/upstream/demos/keyboard-{client,hid,protocol}.ts` is part of the required behavioral reference.

Important details for the adapter:

- One core owns **one keyboard connection**, represented by a logical token1..3. This is not a requirement for three simultaneous keyboard peripherals. Stock MemoMind's one accessory slot can represent this one link, but cannot simultaneously replace another person's ring/accessory. Busy/conflicting ownership must be rejected; never silently adopt or unbond an existing target.
- `KB_FIND(start,end)` means **ATT Find Information**, with original raw response bytes: format1 or2 and handle/UUID entries. It is not a normalized HID field list or a list of characteristic value handles. The client traverses declarations, services and descriptors, including128-bit UUIDs.
- `KB_READ(handle,arg)` uses `arg` as a **Read Blob offset**,0..512, not a requested length. The client explicitly paginates until empty/short/error completion and handles ATT Invalid Offset/Attribute Not Long. Mapping every call to offset0 would loop/repeat data and break Report Map discovery.
- Core WRITE accepts0..18 payload bytes; the original high-level client uses1..18. Stock private writes allow64bytes, so this size bound is sufficient. Preserve acknowledged versus no-response completion meaning, rather than claiming local submission proves peer execution.
- `KB_WATCH` replaces a local filter of up to16 value handles. It does **not** subscribe CCCDs. The client discovers Report References, selects Report Protocol and explicitly writes CCCDs. WATCH cannot be translated into stock `subscribe`/`unsubscribe` operations.
- Preserve raw values by characteristic handle. The client derives report ID/service/report format from discovery, then unions held keys across independent report characteristics. A normalized key code, report ID alone, or boot-keyboard8-byte assumption loses behavior. Do not prepend HID Report ID to a GATT report value.
- Preserve24-byte KB record headers,96-byte fragments,32 slots,512-byte event maximum, sequence gaps/drop heartbeat, epoch/request correlation, one pending ATT operation and original deadlines. Failed sends consume records and must never replay stale typing. Keys are released client-side on gaps, lost phone link, disconnect/security failure and Service Changed.
- QUERY/ENABLE bypass epoch matching; other commands obey it. Disable/timeout retains connection ownership until the close event, isolating late callbacks. Enabled keyboard mode has no built-in30-second renewable lease. The display input owner's lease must not silently change this lifecycle.

## Proven native boundaries and proposed use

| Native boundary | Evidence and proposed role |
| --- | --- |
| `04217546` stock BT router | On the app worker, invokes ATT dispatch and stock connection/security routing, then frees nested event data. Observe owned events and continue original stock handling exactly once. Native event codes are not portable/G2 codes. |
| `04217568/0421756c → 04319792 → 04319f28 → *02012224 → 0421bc32` | Assembly closes the ATT path into the existing callback fanout on the same app worker. The decompiler omitted the computed call in04217546; use the assembly proof. |
| `04250818` entry, decompiled body `host/function-0425081e.c` | Stock HOGP ATT consumer; target-address filtering, discovery and private transaction state. Event0x135 reports are routed by native handle before `0425878c` HID decoding. Preserve this route. |
| `042528dc`, topic52 | Stock HOGP control worker shares the app-worker dispatch path. Proposed CFW control/poll work must enter this serialized task, not call BLE operations on the display worker or timer thread. |
| `0424ffe0(duration,report)` | Copies8-byte scan request to topic52/event11. Explicit7000-tick report scan fits the core deadline; worker0424fc48 accepts nonzero durations≤30000 and clamps/defaults larger/zero. Must acquire scan ownership first. |
| `04250018`, `0425005c(addr6,type,name)`, `042500d2` | Scan stop,37-byte connect request, disconnect enqueue. Return/enqueue failure and cancellation paths need adapter treatment. Do not use `042500f4` unbond as normal cleanup. |
| `042523b8(out53)`, `042503be()` | Read-only snapshot and connected predicate. Native handle at02014152 may be0;0xffff is invalid. Do not cast it to the portable token. |
| `04250320(op,handle,seq,data,len)` | Copies72-byte private request, op0 read/op1 write/op2 no-response write,≤64data bytes. Four queued requests, one active. Candidate for supported operations after arbitration; not complete FIND/READ-BLOB support. |
| `042503ea` | Runs requests only at discovery state12, moves to state17 and arms5000-tick read/write timeout. CFW must not write these globals or steal the current completion. |
| `0431a128(addr,handle,p3,p4)` | Command0x1fc copies addr6 and three u16 fields. Stock private read supplies both extra fields0. Nonzero field meanings are **not yet proved**; do not label them a blob offset without downstream command decoding. |
| `0431a0c8`, `04319ff8` | Native command0x1fb and UUID-specific0x1f9/0x1fa builders. These are search leads, not established raw Find Information APIs. |
| `0431a1b0`, `0431a24c` | Stock acknowledged/no-response write builders. Need exact ownership of lower request buffers and asynchronous/local completion mapped to portable events9/10. |
| `04319058`, `043196e0`, `04212cea` | Incoming descriptor and nested bytes deep-copied before app enqueue; temporary descriptor freed after successful envelope copy, nested bytes freed on failure or eventual stock consumption. Added code borrows and copies; never frees/retains native pointers. |

The GATT callback registry (`0421bcf0`, four pointers at020129d8..020129e4) is not a guaranteed available slot: full registration only logs/returns, and no useful result or removal/lifetime API is established. Generic app registration04235ffa is worse: a third callback silently evicts an existing slot. Do not register speculatively or overwrite either callback table. The proposed implementation should use explicitly pinned wrapper/callsite hooks once exact displaced instructions, return/argument preservation and lifecycle are reviewed. Existing evidence establishes function boundaries and task paths, not a ready patch manifest.

The plugin raw subscription04299932 validates a callback inside the loaded foreground plugin and claims input classes. Its class23 queue receives filtered, deduplicated/throttled normalized36-byte records only for claimed classes. The installed cooked observer sees class2/3 identifiers without physical-source provenance. Neither is an appropriate KB_INPUT source. Keep stock claim mask02011ca8, plugin handling and cooked navigation unchanged.

## Owned event normalization

Use a session-owned mapping `{logical_token, generation, target_addr/type, identity_addr/type, native_handle, closing}`. A handle match alone is insufficient across reconnect/address rotation; match the established address/identity lifecycle. Record generation at request admission and retain it through close/timeout so late events cannot satisfy a newer request. One physical broker connection does not justify resetting the core while callbacks are outstanding.

| Native input | Proven bytes | Compatibility event / gap |
| --- | --- | --- |
| scan0x190 | addr6@0,type@6,RSSI@7,format@8,len@9,pointer@12 | Owned scan result→0x26 with original≤31 advertising bytes and separate scan-start/end→0x24/0x25. Observe before native filtered/merged cache if preserving original advertisement bytes. Report-mode JSON requires named HID candidates; that filtered list is not an unfiltered core advertising feed. |
| connection0x191 | stateu32@0,addr6@4,type@10,handleu16@12,reason@14 | Established state3→0x27 status0; close state0/1 must map only after distinguishing connect failure versus real close and translating native reason/status. No direct enum cast. |
| encryption0x15 | address0..5,status@6,enabled@7 | Emit success0x2c only for owned status0 and enabled!=0. A bond event is not encryption success. Failure/disconnect sequencing must preserve one close and late-event isolation. |
| bond0x1e0 | current addr/type0..6,identitytype@7+addr6,handleu16@14 | Update private identity ownership; do not export native bond/key payloads. No demonstrated mapping to every original DM event yet. |
| notification0x135 | addr6,handleu16@6,data pointer@8,lenu16@12 | Owned raw notification→event13, value handle preserved, bytes copied synchronously into the core ring. Stock HID decoder still runs exactly once. WATCH decides which handles are relayed. |
| read0x136 | addr6,handleu16@6,pointer@8,offsetu16@12,lenu16@14,status@16 | Only the adapter's correlated pending transaction may become event5(read) or6(blob). Request kind/generation/offset and native ownership must be tracked; discovery reads cannot complete a CFW request. |
| write0x137 | addr6,status@6 | Correlate through owned in-flight transaction; no handle in this event means shared-broker arbitration is mandatory. |
| MTU0x138 | addr6,MTUu16@6 | Adapter metadata only; do not fabricate a portable notification. Stock requests247; higher payload capability remains a hardware/controller negotiation question. |
| native0x139 | infrastructure handles a nested buffer, HOGP consumer does not process it | Indication meaning and confirmation owner unresolved. Do not map automatically to event14 or issue duplicate confirmations. |
| passkey/comparison | no proven native request/reply ABI in this evidence | Required0x2e(two-byte prompt),0x35(normalizedu32<1000000), AUTH3bytes, COMPARE0/1 remain unresolved. Never infer a key structure from a coincidental byte layout. |

Core `mm_keyboard_handle_event` returning1 means G2 keyboard ownership; it must **not** cause the MemoMind observer wrapper to skip stock dispatch. `master_dm`/`master_security` cannot invoke stock processing a second time. They need an explicit adapter contract where the native original handler runs once and these callbacks perform only ownership/policy validation, with original security side effects preserved. Decide pre/post ordering from exact exports; do not call a close/enqueue callback recursively while the native handler has partially mutated its state.

A short-lived stack normalization record may borrow the ATT bytes while running on the producer task; `mm_keyboard_handle_event` copies complete admitted events into its owned ring. No extra512-byte per-event heap copy is needed at that point. Data lost before this hook is a separate issue: an allocation/enqueue failure hook must attribute owned loss to `mm_keyboard_lost` on the producer, and a lost close must still release ownership safely. Never turn a lower-stack allocation failure into a silent stuck-key success.

## Smallest complete ownership and scheduling design

Use an explicit runtime session independent of the foreground screen. Its owner contains the4168-byte portable core, one pending request descriptor, connection/identity/generation, broker-claim state and timer/send lifecycle state. A hidden LVGL child is unsuitable as the sole owner: current-screen deletion must not free a context still referenced by app-worker callbacks or a timer. It can be a UI projection only, with a separate lifetime protocol.

The controller command handler should validate the original≤80-byte KB control, copy it to a bounded owned work item, release the native request, and post to the app worker. Admission is not operation success. Core status/ATT records provide asynchronous results. Use an explicitly allocated, collision-audited compatibility endpoint; do not overwrite service0x10's stock operations or choose a command number without dispatch proof.

On the app worker, `scan_available/can_connect` check current stock target, in-flight scan/connect, bond and controller ownership. Acquire an explicit broker claim for the chosen target; preserve stock local HID consumption. Race checks must cover other stock/controller commands on the same task, not only a snapshot taken on the RFCOMM task. No automatic adoption/replacement/unbonding. Allocation or scan-start admission failure must schedule the appropriate asynchronous failure event, because `scan_start` itself has no return value.

The core has one pending ATT request. Keep a bounded adapter-owned record until native discovery and other stock work permit submission, respecting the original30-second deadline. Returning accepted from the core's boolean request callback means **the adapter owns the queued operation**, not that ATT has completed. It must not return false merely to disguise broker BUSY as the core's NO_MEMORY status, nor fabricate successful FIND/BLOB data from a reduced capability list.

Full FIND/READ-BLOB need a proven low-level request/response route plus arbitration with stock discovery/private requests. Extend the broker or add an interlocked adapter transaction path; do not launch a competing BLE stack. Exact native ATT opcode/parameter decoding, state transitions for non-broker completions, error payload construction and cancellation must be established before implementation. A vendor JSON snapshot cannot synthesize all attribute declarations/descriptors or the original on-wire pagination semantics.

Use exactly one producer for control/event/poll/lost. The20ms consumer drains at most four records and posts a poll back to that producer. It must not perform BLE mutations. Core `send` receives the original protobuf field131 compatibility envelope, up to127bytes. Carry those bytes through a documented MemoMind transport wrapper and let a host adapter feed them to the unchanged G2 parser. Do not claim the existing GM service directly understands SID9/field131.

The current native GM sender042e866e is a proven application response boundary elsewhere, but its asynchronous buffer-copy ownership, allocation behavior and blocking/task dependencies need keyboard-specific review. If it can wait for the app/BT task, it cannot execute inside that same producer. A normal non-app-worker timer/egress task should own the consumer. Native topic timer042363f4 posts back to the app worker; using it as both core timer and producer is not evidence of an independent safe sender. The API callbacks must preserve non-reentrancy and failed-start/post retry semantics from the original tests.

Teardown order: stop new controls, issue explicit core disable/disconnect for the session-owned target, process close, cancel pending native/adapter work, invalidate generations, quiesce producer posts and timer callbacks, stop/delete consumer timer, then free. Do not reinitialize the context while queued work can still reference it. Phone-link loss releases host held keys immediately; preserve the actual core/native policy for accessory retention rather than assuming the stock broker's "leave accessory connected" behavior is identical to core DISABLE.

## Remaining proof gates for full completion

1. Exact FIND Information and Read Blob builders, response namespace, offset/status semantics and buffer ownership. The stock0x1fc wrapper's extra fields are only a lead.
2. Pair/authentication/comparison prompts and replies, actual I/O capability policy, genuine bond capacity and identity replacement rules. Stock public connect auto-pairs; there is no explicit public `pair` op. AUTH/COMPARE cannot be no-op callbacks.
3. Indication notification/confirmation ownership and Service Changed delivery. Prove whether stock auto-confirms; no-op confirm is valid only with that proof and correctly timed ownership.
4. Non-stealing broker transaction arbitration and unchanged stock local navigation/controller flows. Handle discovery, generic descriptor handles, writes without response and lost/late completions.
5. Exact app-worker hook bytes and normal-task sender/timer lifetime. Native deep-copy allocation/queue failure and lost-close recovery need coverage beyond the portable ring.
6. Native radio interoperability and coexistence. Current live evidence only confirms query_cap/query_status over SPP at2026-10-31T20:07:24Z with an inactive accessory snapshot; it proves none of pairing, encrypted ATT, raw reports or physical key behavior. It is a historical observation, not a fresh state claim.

## Existing tools and deterministic hardware plan

`scripts/memomind_hogp.py` is the diagnostic controller for stock service0x10: command1 JSON control, command3 JSON+optional BYTES GATT, asynchronous commands2/4/5/6/7/8/9/10/12. It matches GM event IDs separately from GATT sequence IDs, enforces current list generation and explicit≤64-byte writes, and never auto-scans/connects/retries/unbonds. Native ACK means admission only. Its current command set does not fill FIND/BLOB/security gaps; use it to capture native behavior and ownership before designing hooks.

`android_hid_fixture/` is an offline-built, separately packaged Android GATT server with explicit start/stop/report/release, bounded foreground service, token-authenticated loopback controller, encrypted/open diagnostic modes, valid69-byte HID report map, report/boot interfaces, CCCDs and read offsets. It is not installed/tested in the cited evidence. Pairing UI does not trigger Activity teardown; there is no auto-confirmation, key injection or release. A future test must correlate fixture GATT/MTU/bond logs, glasses GM/HCI captures and compatibility KB records. Its simple six-key report model deliberately excludes rollover arrays and full multi-report coverage, so additional deterministic host/native-emulation vectors remain necessary.

The same phone also carries the primary Classic link. Shared BR/EDR/LE identity/bond/CTKD and controller concurrency are explicit unresolved interoperability concerns; the fixture cannot turn them off. Prefer a separately reviewed peripheral arrangement if this prevents isolation. Never clear bonds or replace an existing accessory as implicit cleanup.

A complete validation sequence, after separate native review/authorization, must cover:

- All original host predicates and TypeScript HID/parser/client fixtures unchanged, plus exact callback argument mapping tests.
- Actual RV32 gates and compiled core/adapter with mocked **proven native ABIs**, including every command, other-link isolation, accepted enqueue versus completion, stale generations, timeout/disable, allocation/post/timer failure, lost close and exact stock forwarding.
- FIND pagination with16/128-bit UUIDs; offset0 and Read Blob reads through512bytes; report-map/reference/CCCD/Service Changed; write/no-response; notification/indication fragments, all-or-drop overflow and failed-send no replay.
- Passkey input/display, numeric comparison accept/reject, OOB refusal, security/bond allocation failure, encrypted-state proof and late callbacks. Keep key material out of logs.
- Multiple report characteristics/report IDs, keyboard+consumer usages, modifiers held across reports, press/release, rollover/malformed input, sequence gaps and reconnect configuration invalidation. Stock navigation must still execute exactly once.
- Fixture pairing/discovery/CCCD traces, explicit single press then release, stock controller SPP/BLE coexistence, disconnect/reconnect without bond deletion and primary-link-loss behavior. Record full raw report bytes and real handles; do not infer physical source from cooked events.

Passive observation or basic boot-keyboard success can be useful milestones, but neither completes the full keyboard adapter. The unresolved gates above must remain visible until each has native evidence and tests.
