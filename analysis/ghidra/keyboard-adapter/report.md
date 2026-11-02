# Native keyboard / HOGP adapter boundary

Static evidence for stock MemoMind H001Y 1.0.3.127, segment-3 body SHA-256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, XIP base `0x041eb020`. Official SDK checkout commit `171098bff25934a534a49f95b88df58fbed404c7`. This pass used direct Ghidra exports from the existing RV32 project with `-readOnly -noanalysis`; it did not create REA evidence IDs. The current local REA raw-import CLI does not expose RV32, so no other architecture was substituted. No device action or runtime modification was performed. [provenance.json](provenance.json) hashes the evidence.

## Finding

Stock firmware already owns a BLE Central/HID Host for **one managed accessory**, concurrently with the controller-facing glasses connection. Service `0x10` exposes scanning, connection, automatic security/discovery, HID reports and bounded private GATT requests. This is a useful native boundary, but it is not the G2 Cordio interface assumed by the portable keyboard compatibility core. A complete drop-in native backend is not established.

Prefer testing the existing read-only status/capability interface before adding hooks. Keep the stock accessory manager as the only owner of scan, bond, discovery and ATT state. The existing cooked-input observer cannot establish which physical device produced a key. The raw HOGP path retains report ID, usage page and application context; its plugin subscription **claims** input, rather than passively observing it.

## Read-only capture request

Send service `0x10`, command `0x01`, with exactly one JSON TLV type `0x05`, UTF-8 `{"op":"query_status"}`. The response is a JSON TLV with current `state`, `connected`, `bonded`, `hid_ready`, `gatt_ready`, and address/identity/name fields when available. Current flags are numeric 0/1. Match the GM event ID and parse any STATUS/error response normally. `{"op":"query_cap"}` at the same endpoint returns capability JSON.

These two queries do not enqueue scan/connect/disconnect/unbond operations. The command dispatcher is [04256ef4](../app/function-ram:04256ef4.c), with `query_status` routed to `0x04255830`, and the underlying snapshot at [042523b8](api/function-042523b8.c). Querying does allocate response storage and send a reply; “read-only” here means no accessory ownership or configuration mutation. Do not substitute `query_gatt_list`/`query_gatt_db`: those schedule discovery work and update controller transaction state.

Official contract: [HOGP_QUICKSTART.md](../../../.tools/memomind-open-platform/GlassSDK/docs/HOGP_QUICKSTART.md) and [BLE_ACCESSORY_PROTOCOL.md](../../../.tools/memomind-open-platform/GlassSDK/docs/BLE_ACCESSORY_PROTOCOL.md), especially control, GATT, and lifecycle sections. This source documentation is separate evidence from the target binary and is not a hardware test.

## Live read-only confirmation supplied by the parent task

At `2026-10-31T20:07:24.846039+00:00`, the parent captured both queries over the stock Classic SPP control service, with the input004 runtime installed. [stock-readonly-01.json](../../../captures/input-runtime-20261031/stock-readonly-01.json) and its [wire log](../../../captures/input-runtime-20261031/stock-readonly-01.jsonl) report no mutations. `query_cap` returned all documented gateway flags, including `scan`, `connect`, `hid`, `gatt_relay`, `gatt_list`, `gatt_db`, `hid_event`, `hid_desc` and `inputmap`; the map limit was8192. `query_status` returned state0, reason0, err0, connected0, bonded0, hid_ready0, gatt_ready0, and empty address/identity strings.

This confirms the existing endpoint and inactive accessory state on that installed image, using **SPP**, not controller-facing BLE. It does not validate scanning, pairing/security, accessory ATT requests, raw HID delivery or keyboard interoperability. The parent's180-second cooked-input logging interval returned zero records; absence of a supplied physical stimulus does not prove missing native input support.

## Native API surface and ownership

The following addresses are proven call sites/implementations, not a public stable ABI. Inferred decompiler `void` return types are not authoritative: callers inspect `a0` for enqueue status in several thin wrappers.

| Address | Interface observed | Ownership / constraints |
| --- | --- | --- |
| `0424ecfa` | Host initialization | Initializes shared state; registers topic `0x34` handler `042528dc`; sets existing relay and GATT callbacks. Runs from app init table. |
| `0424ffe0(duration,report)` | Scan enqueue | Copies 8 bytes: duration u32 at 0, report u8 at 4; topic52/event11. |
| `04250018()` | Stop scan enqueue | Topic52/event12. |
| `0425005c(addr6,type,name)` | Connect enqueue | Copies37 bytes: address0..5, type6, name7..36, bounded30. Topic52/event13. Type is later checked0..3. |
| `042500d2()` / `042500f4()` | Disconnect / unbond | Topic52/events14 /6; distinct operations. |
| `04250116()` / `0425015a()` | GATT-list / HID descriptor work | Topic52/events15 /28. Not passive snapshots. |
| `04250320(op,handle,seq,data,len)` | Private ATT enqueue | op0..2, handle nonzero, len<=64; data required for nonzero len and op!=0. Copies72 bytes. |
| `042503be()` | Connected predicate | Native handle at `02014152` differs from `0xffff`, and internal state>3. Native handle0 is not excluded. |
| `042523b8(out53)` | Snapshot | Copies current state and bounded names/addresses. No radio command. |

Private ATT request72: op u8@0, padding@1, handle u16@2, sequence u16@4, length u16@6, inline data64@8. [Topic worker](host/function-042528dc.c) copies into four72-byte slots at `0201465c`; count `02011c46`, read index `02011c47`, write index `02011c49`. Busy/rejected submissions report local error `0xfe` through the relay. This is separate from the controller's own four pending correlation slots.

[Runner042503ea](final/function-042503ea.c) allows one active request (`02011c45`) only when discovery state `02014256==12`. It moves a pending record to `02014614`, sets state17, and dispatches op0 read to `0431a128`, op1 write-with-response to `0431a1b0`, op2 write-without-response to `0431a24c`. Read and acknowledged write arm topic52/event18 for5000 ticks. Write-without-response completes from local submission, not accessory execution. Disconnected queued requests are drained with error. Never inject directly into these globals or consume completion state belonging to another controller.

The public JSON interface additionally validates current `list_id` generation, handle/property eligibility, authentication/readiness, duplicate sequence and payload bounds. Subscription is a CCCD write selected through that validated interface. The internal HID report-map reader can accumulate up to512 bytes; this does not prove that the public private-GATT interface supports generic long reads, prepare/execute writes or arbitrary discovery operations.

## Scan, connection, security and coexistence

[Scan worker0424fc48](lower/function-0424fc48.c) manages existing state, report-mode flag and deferred connect cancellation. Report duration is clamped/defaulted to30000 ticks. [0424dd92](final/function-0424dd92.c) registers the host GATT callback, configures scanning through `04319e80(1,0xa0,window,0)` with window0x30 or0x60, installs a filter via `04319ed0`, starts through `04319e50(1)`, then arms its native lifecycle helper. These are the stock policy's choices, not general permission to run competing scans.

[Scan consumer0424f030](host/function-0424f030.c) uses a2460-byte cache (30 records of82 bytes), merges advertisement/scan-response information and reports selected HID candidates. The official SDK explicitly requires a nonempty name plus recognized HID service0x1812 or appearance for report-mode results. This is not an unfiltered advertising feed.

[Connect worker042519cc](host/function-042519cc.c) rejects a conflicting existing target/bond, records one target address/type and enters internal state2. It submits `04317ec0(addr,type,1)` normally or `04317f94(addr,type,1,0x18,0x28,0,500)` for the identified mouse path, then starts a10000-tick timeout. These low wrappers copy command payloads and dispatch commands0x174/0x182 through `043199d2`; disconnect04318052 dispatches0x175. Full lower command queue/task scheduling is not reconstructed by the thin wrapper alone.

[Connection event04251dd2](host/function-04251dd2.c) scopes events to target address/type or resolved identity, saves the native u16 handle, enters state3, requests MTU247 (`04319c52`) and starts security. Unbonded and bonded paths use `04317dde` (command0x181) and `04317e2c` (command0x2fd) respectively. The latter copies address/type plus optional identity. [0424f6e4](lower/function-0424f6e4.c) records successful bond identity and advances discovery; [0424f7f4](lower/function-0424f7f4.c) accepts encryption success only when status@6==0 and enabled@7!=0. Failure branches handle missing key/MIC retry through stock helpers and can disconnect. No explicit numeric-comparison/passkey reply API has been established here.

The shared BT router [04217546](../notification-adapter/function-04217546.c) invokes the accessory connection handler and then continues stock connection handling. Native parameter-request event0x194 preserves parameters for a matching accessory and applies separate policy for other links. Security ownership is checked by [0424ef4a](lower/function-0424ef4a.c) using handle/address/type/identity, not by assuming every BLE event belongs to HOGP.

Controller-link loss reaches topic52/event20: it stops report-mode scanning, clears pending controller ATT operations, and abandons an in-flight controller operation. It does not unconditionally disconnect an already established accessory. Local HID input can continue; controller forwarding is a separate opt-in flow. Replacing the relay pointer `02011c3c` would steal that flow: initializer04256b96 sets it to `04255b70` through0424fbc0.

## Event layouts and borrowed storage

Offsets below are little endian, RV32 pointers are32-bit. Preserve native event namespaces separately from the G2 compatibility enum.

| Native event / consumer | Established layout |
| --- | --- |
| `0x190`, scan0424f030 | addr6@0, type u8@6, RSSI@7, format byte@8, byte count@9, advertisement pointer@12. Stock router frees nested pointer after consumption. |
| `0x191`, connection04251dd2 | state u32@0; addr6@4; type u8@10; native handle u16@12; reason u8@14. State3 is established;0/1 take disconnect paths. |
| `0x15`, security0424f7f4 | address at0; status u8@6; encryption-enabled u8@7. |
| `0x1e0`, bond0424f6e4 | current address/type at0..6; identity block at7 is type then address6; native handle u16@14. Do not reverse the identity byte order. |
| `0x135`, GATT callback |16-byte descriptor: addr6@0, value handle u16@6, data pointer@8, length u16@12. |
| `0x136`, GATT callback |20-byte descriptor: addr6@0, handle u16@6, data pointer@8, offset u16@12, length u16@14, ATT status u8@16. |
| `0x137`, GATT callback |addr6@0, write status u8@6. |
| `0x138`, GATT callback |addr6@0, MTU u16@6. |

Host callback entry is `04250818`; the decompiler-defined body begins `0425081e`. It gates by target address through0424eef2, owns the discovery state machine and routes HID report handles to0425878c. Native event0x139 is separately copied/freed by the infrastructure, but this HOGP body does not handle it; no manual indication-confirmation obligation is inferred.

[04319058](../notification-adapter/function-04319058.c) deep-copies notification/read descriptors plus their nested bytes before app enqueue. [043196e0](../notification-adapter/function-043196e0.c) frees the temporary descriptor after successful shallow envelope copy; it also frees nested data on enqueue failure. The app-side stock router frees nested data on consumption. Any added observer must copy bytes while borrowed data is valid; it must not retain/free native pointers or transfer them into the portable ring. The portable ring itself owns96-byte fragments and32 slots, which is a different buffering contract.

## Task and callback boundaries

App init042127a4 registers BT router04217546 on generic topic0 and installs ingress04212cea. Ingress performs the special deep-copy above, then posts through042361b8/042361da. The app worker0423590c dispatches the envelope synchronously through04235770 and frees it afterward. Topic52 host control042528dc and topic0 connection/security/scan routing therefore share this app-worker path. Native timers use042363f4(topic,event,payload,len,delay), cancellation04236404(topic,event); they schedule stock event work rather than implementing the portable core's timer contract automatically.

GATT callback registration is a **different four-slot registry**:0421bcf0 deduplicates pointers in020129d8..020129e4, takes the first empty slot, logs/returns on full, and has no useful registration-success result. Dispatcher0421bc32 calls all nonnull entries synchronously with `(event,payload)`. Initialization0421bc98 installs this fanout through04319f14, which stores pointer02012224. Do not confuse it with the generic event bus's two slots per topic, which can evict the oldest callback when registering a third distinct callback. The task chain is now closed in assembly: `04217568: auipc ra,0x102; 0421756c: jalr ra,ra,0x22a` calls `04319792` before stock event-specific handling. That function routes ATT events through `04319f28`, which tail-calls pointer02012224 with the original event/payload arguments. Thus the host GATT callback executes on the same app worker as topic52 control, before the router frees nested data. **The decompiler C for04217546 omitted this computed call; the assembly is the decisive evidence.** Exports are [event-dispatch](event-dispatch/function-04319792.c), [tail dispatcher](dispatch/function-04319f28.asm), and [BT router assembly](../notification-adapter/function-04217546.asm). This proves the inspected stock route, not safety of arbitrary direct calls from other tasks.

The raw HOGP-to-display path is already analyzed in [input-adapter/report.md](../input-adapter/report.md):36-byte native raw records, class23 display queue, and40-byte plugin callback conversion. Plugin subscriptions require a loaded foreground plugin and claim classes; they can suppress cooked routing. They are not a passive arbitrary-runtime registration API.

## Portable keyboard backend feasibility

| `mm_keyboard_platform` responsibility | Present evidence / remaining work |
| --- | --- |
| `scan_available`, `scan_start`, `can_connect`, `open`, `close` | Existing stock broker provides most policy, but uses one address-scoped accessory and u16 handle, not Cordio IDs1..3. Adapter must allocate its own compatibility token/epoch and preserve stock ownership. |
| `request` read/write/watch | Bounded private ATT path is a candidate, with64-byte writes and shared transaction ownership. FIND/long operations need explicit semantics, not direct opcode casts. |
| `pair`, `auth`, `compare`, `master_security` | Stock auto-security exists. Explicit passkey/comparison prompts, responses and ownership are unresolved; do not pretend G2 DM events are native. |
| `ind_confirm` | Not established. Native indication event and confirmation ownership need proof; duplicate manual confirmation could be wrong. |
| `master_dm` and event normalization | Need address/handle filtering and native-to-compatibility translation. Forward stock handling unchanged. No physical-source inference from cooked keys. |
| `now_ms`, `timer_start`, `post_poll`, `send` | Generic native facilities exist, but integration must establish one serialized producer plus timer-consumer ordering, owned queued records, failure/drop accounting, and teardown. Display-worker input serialization does not automatically cover BT callbacks. |

Recommended scope is a broker-backed adapter with explicit capability gaps, beginning with passive status and raw/normalized report observation after separately authorized accessory selection. A full keyboard compatibility endpoint remains blocked on security-prompt mapping, indication confirmation, transaction arbitration and lifecycle tests. The stock app-worker serialization is established, but an added portable producer/timer integration must preserve it. Required validation includes actual native-call emulation, request/timeout/drop/teardown tests, then hardware pairing/interoperability and coexistence. Static exports and SDK examples are not those tests.
