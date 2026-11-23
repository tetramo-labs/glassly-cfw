# Head-up settings: wire contract and native ownership

Scope: static stock 1.0.3.127 segment-3 analysis, existing Android 1.3.81 APK and captured general-session frames. No device commands, setting changes or runtime-source changes. Stock body SHA-256 is `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`. Functions are exported alongside this report; the raw settings descriptor rows are in [config-descriptors.json](config-descriptors.json).

## Concrete standard-command path

Initializer `0x042e8114` installs `0x042e88ea` at table offset 0x38. Dispatcher indexing `0x34 + service*4` establishes **service 1**. This handler already supports angle, head-up screen-on, timing and sensitivity. A phone compatibility adapter can use these existing commands; enabling a plugin or adding a new firmware setter is not required to express these settings.

| Service 1 command | Value / setting key | Query-6 JSON field | Valid range; descriptor default | Write response |
| --- | --- | --- | --- | --- |
| `0x0c` | Head-up angle, `0x5002` | `angle` | 0–70; 30 | STATUS0 after structurally valid request, **ignores setter failure** |
| `0x33` | Head-up screen-on control, `0x500a` | `hd_screenon` | 0/1; 1 | STATUS0 on setter result 0, otherwise STATUS1 |
| `0x16` | Raised-head screen-on duration, `0x5005` | `light_ut` | 5–255; 15 | Same unchecked-success path as angle |
| `0x17` | Lowered-head delay, `0x5006` | `light_dt` | 1–5; 1 | Same unchecked-success path as angle |
| `0x6b` | Motion sensitivity, `0x520c` | `head_sens` | 0–4; 2 | Checks setter result |
| `0x15` | Nod/shake setting, `0x5202` | `nod_shark` | 0/1; 0 | Same unchecked-success path as angle |

These requests carry a type-8, length-1 value: wire payload `08 00 00 01 VV`, where VV is the unsigned byte. Use the transport's existing sequence/checksum implementation. The handler checks the first TLV's type and length; do not interpret its permissiveness toward extra TLVs as part of a stricter portable API. A query is service 1/command 6 with empty payload. The handler formats the aggregate JSON using string `0x0439221c`, returns it via `0x042ef978`, and releases its temporary formatting buffer; the ordinary dispatcher sends the response correlated to the request event. Query 6 may span physical frames and must be reassembled before decoding.

`hd_screenon` is **head-up screen-on**, despite its ambiguous abbreviation: native UI handler `0x0426da76` binds key `0x500a` to `icon_head_up_screen_on` at `0x04362914`. The same handler binds `0x5002` to `icon_headup_angle`, `0x5006` to `icon_head_down_delay`, and sensitivity to `icon_head_motion_sens`. Duration 255 has a special UI branch rather than ordinary numeric formatting; its timing behavior must not be extrapolated from the ordinary seconds values.

The descriptor table is 101 rows of 16 bytes beginning at `0x0435a4f0`. For these byte settings, key is u16 at 0, default byte at 2, max u32 at 8, minimum byte at 12 and type bits at 13. `0x0422a8ee` checks those limits. The getter's explicit fallback argument is overridden by a matching descriptor before persisted value lookup: **angle default is 30, not the call-site fallback 15**; raised duration default is 15, not the fallback 10. This refines the earlier input-adapter report's fallback descriptions.

## Persistence, callbacks and echo

The callable byte setter is `int 0x0422aefc(uint32_t key, uint8_t value)`. Ghidra renders its return type void, but assembly shows it leaves the `0x0422ac90` result in a0 through its epilogue. Its 32-byte frame holds a single-byte local and calls `0x0422ac90(key,&local,1)`.

The lower setter returns 0 on success and 11 on validation/state/store failure. It validates the descriptor, serializes through mutexes, calls store function `0x0433f14c(key,data,len,1)` and flush routine `0x0433fc3e`, then synchronously invokes registered callbacks as `void(key,data,len)`. Input data remains borrowed through the call. There is no later scheduled apply operation in this setter. Failure handling and durable storage behavior below the flush routine were not fully audited, so success is not a proof of power-loss durability.

Callbacks are snapshot/refcounted from a linked registry: records are 40 bytes, matched by key. With up to eight matches the setter uses its stack; above that it allocates a pointer array. If allocation fails, it invokes callbacks under the registry lock instead. Outer write serialization remains held during callbacks. This is a distinct registry from the two-slot app bus; do not confuse its callback record refcounts with sensor ownership refcounts.

`uint32_t 0x0422b05a(uint32_t key,uint32_t fallback)` reads a descriptor default and persisted byte under the settings mutex. Both getter and setter can use the native `0x0200ec3a` mutex path (60000-tick wait/assert behavior documented in input-adapter). They are not bounded operations suitable for the passive event observer or a latency-critical display callback. Setting through a display queue would move the blocking persistence and synchronous callbacks onto that worker, not make them asynchronous or nonblocking.

The normal GM service handler already performs these writes in its existing command context. Prefer that path for an initial host adapter. If an internal setter is later necessary, its execution context, ordering, callback reentrancy and completion contract need separate review; this pass does not establish a safe new display-worker setter interface.

**ACK is not echo.** Commands 0x0c/0x16/0x17/0x15 explicitly discard setter status and build STATUS0. After each desired write, query 6 and compare the target field exactly; report a mismatch or unavailable query as failure. Commands that do check status still do not return the newly stored value. No dedicated asynchronous head-up setting echo was established in this pass.

## Sensor application and shared ownership

Angle key `0x5002` has at least two proven subscribers:

* Application callback `0x042282fc` updates `0x0200f9a0`, used by stop/power behavior at `0x04227e4c`.
* IMU manager initializer `0x04229d9e` registers `0x04229c8e`; that callback updates `0x0200f9b5`, which detector `0x0422a20e` actually reads. This closes the path from persisted GM angle to the detection algorithm. The algorithm also uses calibrated pitch, history, motion rejection and hysteresis; numeric angle equality across products does not prove identical physical triggering.

For `0x500a`, callback `0x042282fc`/shared tail `0x042283b2` sets byte `0x0200f9ac` to `value==1` under a critical section. An off-to-on transition also sets `0x0200f9ad`; disabling clears that pending flag. The worker reads the pending flag and can reemit a currently raised gesture. Thus a setting transition may affect event suppression; it is not necessarily a fresh physical motion. The complete stock UI/power gating effect of disabling this setting still needs live correlation. It is not equivalent to powering down all IMU activity.

`0x042286a2(bool)` sets or clears **one shared bit** (bit 1 of byte `0x0200f9af`), then starts/stops sensor processing. `0x04227cfc` checks initialized state and an already-running bit, starts lower acquisition and signals its queue. `0x04227e4c` only shuts processing down when several activity bits permit; these encode multiple stock uses, not caller-specific ownership tokens. The raw-sample enable `0x042289a2` similarly changes a shared bit.

The SDK `imu_enable` wrapper `0x04299d1a` remembers modes only in the loaded plugin state and uses this same lower boolean API. [imu-enable-callers.txt](imu-enable-callers.txt) proves several other stock applications call it directly on activation/deactivation. There is no acquire/release counter, caller token, or independent appended-client slot in the reviewed path. Two extra users could overwrite the same bit; restoring a prior snapshot could overwrite a concurrent stock transition. **Do not use this function as a leased sensor ownership API.**

Other shared uses include calibration (`0x0422840e` starts task `0x04228528`), temporary activity (`0x0422877c`), shutdown (`0x04227b82`), and key `0x5904` force-active behavior. None is a substitute for the user's head-up screen-on setting. This pass does not expose these as portable controls. Passive class-3 observation remains preferable because it does not alter any enable state.

## APK and capture boundary

The APK is Flutter. Searching captured JADX Java sources found no relevant app settings implementation; Java results named heads-up concern navigation notifications. `analysis/extracted/libapp.so` contains `setHeadUpControl`, `headUpControl`, `setDeviceHeadAngle`, `headAngle`, `queryHeadAngle`, timing methods, the head-up settings route, and UI limits 0/70. [flutter-strings.txt](flutter-strings.txt) preserves offsets. Those strings corroborate naming and range, but are not a decoded Dart command binding; the wire command assignments above come from native dispatch and config/UI references.

[captured-settings-frames.json](captured-settings-frames.json) selects relevant records from `analysis/protocol/general-session/normal-frames.json`: three query-6 requests and their six physical response frames. Frame 401's first response fragment contains `angle:61`, `light_ut:15`, `light_dt:1`, `head_sens:2`, `hd_screenon:1`. This is a historical observation, not current state. No writes to the five head-up/timing/sensitivity commands were present in that selected trace. No write-ACK-readback or physical head-movement test was performed here.

## G2 comparison and next acceptance boundary

`/Users/fosse/dev/g2flash/demos/head-up-test.ts` sends separate `headUpSwitch:1` and `headUpAngle` writes, checks acknowledgement, waits 500 ms and queries settings. It **logs** the returned switch/angle; it does not assert that the echo equals the request. It then exercises a page and display lease (or no-page mode) and requires a configured number of event-12 reports. A MemoMind test should strengthen the readback comparison because its angle ACK can mask failure.

G2 README/settings extension additionally promise separate head-up wake, head-up/down foreground events, idle inputs and wake-session takeover. Those involve display ownership and deferred CLAIM/READY/fallback semantics. Mapping MemoMind screen-on control and angle fields, or observing IMU IDs 2/3, does not implement those policies. Preserve stock forwarding in the current passive observer.

`patches/host/upstream_host_test.c::settings()` validates revision/capability additions, field presence, packet bounds, ring report separation and send failure behavior. It does not test physical head-up behavior or a native angle setter. Passing those upstream host assertions is not evidence that MemoMind settings or sensor semantics match G2.

For a true settings adapter, the remaining acceptance work is: validate requested ranges before sending; retain the original user values; perform existing GM write plus exact query comparison; observe enabled/disabled behavior and angle changes with physical actions in both stock/base and custom-scene contexts; verify stock UI/power handling; and report unsupported wake takeover/raw sensor ownership separately. No feature is marked complete from API availability alone.
