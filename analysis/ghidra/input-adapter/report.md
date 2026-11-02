# Input and head-movement adapter evidence

Static review of stock MemoMind H001Y firmware 1.0.3.127, segment 3 body SHA-256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, mapped at `0x041eb020`. SDK commit: `171098bff25934a534a49f95b88df58fbed404c7`. No input capture, device action, firmware edit, or observer installation was performed in this pass. Addresses and byte witnesses are in [profile.json](profile.json); adjacent function `.c` and `.asm` files are native exports. Decompiler prototypes are inferred; assembly and SDK definitions settle the interfaces described below.

## Result and recommended boundary

The existing display-worker dispatch gate is a concrete candidate for an **additive cooked-event observer**. Classes 2 and 3 carry button/navigation and IMU gesture identifiers respectively, before stock app routing. A future observer can copy their small scalar records and then invoke the unchanged stock dispatcher. This would preserve stock handling, including power-management effects. It is not yet an implemented or validated input adapter.

Neither convenient subscription API is appropriate for registering an arbitrary appended observer:

* The official raw HOGP subscription claims input classes, suppresses their normal cooked route, and validates callbacks against the currently loaded plugin image.
* The generic app event bus has two slots per topic and silently evicts an existing callback when a third distinct callback registers. The IMU topic already has two static registrations.

This evidence supports a bounded cooked-event probe next. It does not establish raw ring provenance, G2 wake-session takeover, head-up setting round trips, or physical gesture parity.

## Official SDK contracts and native enforcement

Source definitions are in `.tools/memomind-open-platform/GlassSDK/include/gm_plugin.h`, `gm_plugin_extensions.h`, and `gm_plugin_input.h`. The SDK ABI offsets were compiled in [offsets.c](offsets.c). Host table `0x0436609c` is 112 bytes; its `imu_enable`, `imu_read`, and `extension_get` entries are at offsets `0x50`, `0x54`, and `0x6c`.

| Interface | Native address / signature | Contract and restriction |
| --- | --- | --- |
| Extension lookup | `0x0429a3a2`, `int(uint32_t id, const void **out)` | ID 4 returns input table `0x02011404`; ID 5 returns system table `0x02011410`. Null output returns -1; unknown ID returns -2 and null output. |
| Raw subscribe | `0x04299932`, `int(uint32_t classes, void (*cb)(void *, const input_event40 *), void *ctx)` | Only mask bits 1/2/4/8; requires foreground plugin state and valid callback. Replaces that plugin's stored callback/context/mask. |
| Raw unsubscribe | `0x042998e2`, no arguments | Removes the plugin claim. Lifecycle changes also update effective claim. |
| System subscribe | `0x0429999a`, `int(void (*cb)(void *, const system_event12 *), void *ctx)` | Same plugin callback validation; immediately invokes a snapshot callback. Current event is CALL_UI, not an input stream. |
| System unsubscribe | `0x042997f8`, no arguments | Clears that plugin's listener. |
| IMU modes | `0x04299d1a`, `int(uint32_t modes)` | Bits 1 gesture and 2 raw, using plugin state and shared lower sensor enable flags. Not an independent sensor owner. |
| IMU sample | `0x04299caa`, `int(imu_sample16 *out)` | Requires plugin raw mode. Native path can wait on a mutex; see below. |

`0x0429bd66` validates the callback through `0x0429b822`: the pointer must be aligned and inside the loaded plugin's image range, with the required loaded-state flag. A normal appended runtime callback is outside this lifecycle/range. This review does not propose bypassing that guard.

`0x04299896` installs the effective claim through `0x0425a14c`; global claim mask is `0x02011ca8`. `0x0425a59a` returns early after a claimed raw event is handled, skipping cooked routing. SDK comments explicitly describe this claim behavior. A subscription is therefore not a passive observer, even when its callback does nothing.

The plugin descriptor's `on_event` at offset 24 is `bool (*)(void *context, const gm_plugin_event_t *event)`. It runs synchronously on the display task and can consume an event. Core event size is 20 bytes: size/type at offsets 0/2, timestamp at 4, union at 8. Button fields are two `uint16_t` values at 8/10; IMU gesture is `uint16_t` at 8 with active byte at 10. `0x0429ac6a` builds these records on its stack, and `0x0429b966` calls the descriptor callback using the loaded plugin context. Retaining event pointers beyond the callback is invalid. System/raw callbacks are void and likewise receive borrowed records. SDK serialization does not make plugin lifecycle-dependent callbacks generally callable by unrelated appended code.

## Native display path and ownership

The previously verified hook site is `0x0425c00a`, original bytes `03 25 04 f9 ef f0 cf b7`: `lw a0,-0x70(s0)` followed by the call to `0x0425b38a`. Its continuation is `0x0425c012`. The worker owns and frees the envelope after dispatch. The existing custom gate already uses this call site; any expansion must preserve the displaced load, original argument, stock call/return semantics, and normal envelope cleanup. This report does not replace the compiled gate review.

Envelope fields:

| Offset | Meaning |
| --- | --- |
| 1 | Class, low six bits |
| 4 | Event identifier, `uint16_t` little endian |
| 6 | Inline payload length, `uint16_t` little endian |
| 8 | Inline payload begins |

Class 2 originates at `0x04225696(key)`, which calls `0x0425add2(2,key,NULL,0)`. The latter supplies priority 1 to queue routine `0x0425abe8`. Class 3 similarly carries the IMU gesture ID without payload. Only these known class/length combinations should be admitted by an initial observer. Copy scalar values during dispatch; do not retain envelopes or stack-converted app records. Avoid allocation, sensor reads, Bluetooth send/retry, or waits in the observer. A later bounded owned buffer would need explicit overflow behavior, lifetime, synchronization, and host-drain design.

`0x0425b38a` processes class 2 through `0x042631b6` before app routing. A pre-dispatch observer consequently sees some keys that stock routing may consume before the foreground app sees them. Class 3 constructs `{uint16_t gesture, uint16_t active=1}` and routes app event kind 2. No inactive edge is established in this path. A separate class `0x11`, event 6 branch synthesizes gesture 2/active 1; it must not be labelled a measured head movement.

App routing at `0x0425dbfc` invokes `bool callback(app, kind, payload)` through app offset `0x28`, overlays from priority 4 down to 0, then the base app, stopping on true. Assembly forwards payload in `a2`; the decompiler's abbreviated prototype omits it. Plugin app descriptor `0x020102b8 + 0x28` points to `0x0429ac6a`. App payloads are borrowed synchronously. A passive observer should leave this consumption order intact.

## Event identifiers and physical-source limits

| Native cooked key | SDK interpretation | Closest G2 semantic candidate |
| --- | --- | --- |
| `0x1f7b` | Primary single | tap 0 |
| `0x1f7c` | Primary double | double 3 |
| `0x1f7d` | Primary long | long press 9 |
| `0x1f7e` | Primary very long | No proven equivalent |
| `0x1f7f` | Primary release | release 10 |
| `0x1fb0`…`0x1fb3` | Up/down/left/right | Navigation; not automatically ring swipe |
| `0x1fb4`…`0x1fb7` | Page up/down, scroll up/down | Preserve separate semantics |
| `0x1fb8`, `0x1fb9` | Back, home | No proven G2 system-exit equivalence |

The native plugin conversion uses button 1 and actions 1…5 for the first five rows; navigation uses buttons 2…11 and action 6. Handler `0x0421e0f6` emits the first five cooked IDs for its event-1 record with byte 0 equal to 1 and action byte 9 equal to 0/1/7/9/15. Its full hardware source fields are not decoded here. HOGP routes also produce cooked keys, so those IDs alone do not prove temple-versus-ring provenance.

Native IMU IDs are 1 nod, 2 head raise, 3 head lower, 4 shake, 5 raise timeout, 6 lower timeout, 7 left, 8 right. `0x04227eca` emits both display class 3 and generic app topic 10/event 8 containing a four-byte gesture ID. `0x04227576` similarly emits timeout IDs 5/6. Head lower is a distinct gesture, not a head-raise callback with active=false.

Initializer `0x04227892` creates worker `0x04227eca` named `app_gmimu`, priority argument 5, stack-depth argument 350. Native worker entry frame is 80 bytes; this alone is not whole-chain stack usage. The detector `0x0422a20e` uses history, calibration and hysteresis. `0x0422a140` returns calibrated pitch using scale/offset state. Timeout settings 5005/5006 default to 10/1 and are multiplied by 1000 in power handler `0x0424222a`; threshold setting 5002 defaults to 15. Exact externally visible head-up switch/angle query/write/echo semantics remain unproven.

Power handler `0x0424222a` consumes topic 10/event 8: raise/lower change activity/state, nod generates activity, and shake takes another stock path. These effects are concrete reasons to preserve stock dispatch.

## Raw HOGP and sensor caveats

Class `0x17` requires exactly 36 payload bytes at dispatcher `0x0425b768`. Producer `0x042256d0` queues priority 0; MOVE records are dropped when its outstanding count is at least two. Other source logic rate-limits movement per axis to approximately 15 ticks and deduplicates edges. Native normalized layout:

```
0 key:u8, 1 phase:u8, 2 source:u8, 3 axis:u8
4 value:i32, 8 normalized:i32, 12 x:i32, 16 y:i32
20 modifiers:u16, 22 usage_page:u16, 24 usage_id:u16
26 report_id:u8, 27 reserved:u8, 28 application:u32, 32 timestamp:u32
```

The SDK wrapper converts this to a 40-byte record, prepending size and relocating report ID. Phases are down/up/repeat/move/cancel = 0…4. Sources are generic/keyboard/mouse/consumer/digitizer/gamepad/vendor = 0…6; they identify HID categories, not a specific ring model. Class claims are key=1, relative=2, absolute=4, touch=8. SDK key IDs include touch down/up/move/tap/double/long/swipes at 42…51, but their presence in the enum does not prove the connected accessory emits them.

Lower router `0x0425a3b8` only forwards the claimed classes to this raw queue. A passive class-0x17 observer therefore will not receive a complete raw stream when no plugin claims input. Enabling claims to obtain it changes stock behavior. `0x0425a062` can also emit a synthetic unknown/cancel record during reset. Normalized events cannot be advertised as raw reports or complete hardware edges.

The SDK describes `imu_read` as nonblocking, but native `0x04299caa` calls `0x04228900`, which locks mutex `0x0200f96c` through `0x0200ec3a`; that calls a 60000-tick wait and asserts on failure. It then copies 14 raw bytes and adds calibrated pitch. The 16-byte output has accelerometer `int16_t[3]`, gyro `int16_t[3]`, temperature `int16_t`, and pitch `int16_t`. Do not invoke this path from a bounded display observer on the strength of the SDK comment. Mode setters share lower sensor state and are not proven reference-counted for arbitrary extra owners.

## Generic app bus is not an additive fallback

`0x04235ffa(topic, callback)` supports topics 0…52 with two callback slots each at `0x02012c20 + topic*8`. Duplicate registration is ignored. When both slots are occupied, it shifts the second callback into the first slot and inserts the new callback into the second, evicting the original first callback. Topic 10 has static registrations of `0x0424222a` from `0x04241f64` and `0x042311d0` from `0x04230c12` (see [app-register-callers.txt](app-register-callers.txt)). The second callback body is outside this pass's decoded scope; its existing registration alone rules out assuming a free slot.

Dispatcher `0x04235770` calls both non-null callbacks as `void(event_u16, inline_payload, length_u16)` and subsequently releases the envelope; callbacks cannot retain its payload. Queue wrapper `0x042361b8` forwards to `0x0423608e`, which allocates/copies and can retry/delay. This is neither an unbounded multicast registry nor a bounded lock-free observer channel.

## G2 parity comparison and acceptance gaps

Read-only upstream references: `/Users/fosse/dev/g2flash/patches/gesture_fwd.c`, `patches/settings_ext.c`, `demos/head-up-test.ts`, and `docs/ring-touch-test.md`.

* G2 gesture IDs are a separate namespace: head up=12/head down=15 versus MemoMind IMU 2/3. Map semantics explicitly, never pass through raw enum numbers. A physical correlation test must establish suppression, timing, duplicate behavior and available source identity before claiming equivalence.
* G2 raw R1 format is 11 bytes, `00 09 61 00 type aux speed tickLE32`. Field 100 forwards an RI-v1 record with raw type, auxiliary byte, speed and ring-origin tick. Touchdown type 10 maps to event 14. MemoMind normalized HID category/timestamp has no established equivalence to these fields. No R1 source identity or ring clock reconstruction was demonstrated.
* The G2 head-up test sets switch and angle, reads them back, creates/leases the scene, then expects at least three event-12 reports within 120 seconds; it also supports a no-page case. An SDK head-raise enum does not satisfy settings round trips, page/no-page routing, lease interaction, or this physical count. Native MemoMind head-up configuration endpoints still require tracing.
* The ring-touch test requires three event-14 reports; when RI packets are available it checks raw type 10 and unique ring ticks. The upstream historical negative result is not a MemoMind result. An enum containing touch-down does not pass this test.
* G2 settings extensions include wake leases, deferred head-up/double-tap handling, CLAIM/READY and timeout fallback. Observing events while forwarding stock behavior provides none of this takeover policy. Implementing it would be a distinct, separately reviewed change.
* PhoneSDK subscription documentation describes the permissioned phone/plugin bridge. It does not establish that an arbitrary appended runtime can register these native callbacks or that hardware emits every documented event.

A next probe can be limited to copying known class-2/class-3 scalar events at the existing display gate and forwarding stock unchanged. It still needs compiled hook/ABI review, bounded storage and overflow tests, opt-in session ownership, live event-to-action correlation, and confirmation that stock calls/UI/power behavior remains intact. Raw ring parity, settings parity, and wake takeover remain separate unresolved requirements.
