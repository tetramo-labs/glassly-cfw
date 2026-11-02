# Native ALS / raw IMU adapter boundary

Read-only stock H001Y 1.0.3.127 analysis, segment 3 SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, base `0x041eb020`. Exports in this directory were obtained from the existing app project with `-readOnly -noanalysis`; selected missing function definitions were created only in the discarded read-only session. No image, device, runtime or shared project changes. Existing SDK pin is `171098bff25934a534a49f95b88df58fbed404c7`.

## Result

Actual light-sensor acquisition exists. The selected sensor is a runtime probe result, not something that should be guessed from the firmware's three driver names. Raw accelerometer/gyro/temperature acquisition exists, but neither that sample nor calibrated pitch proves compass heading. No magnetometer/heading producer was established in this bounded pass. Compass remains required and unresolved; gesture exclusion does not remove raw IMU or ALS requirements.

The smallest safe first integration is an owned, passive sample snapshot/capture with explicit available/unavailable and freshness metadata. It must neither claim new sensor power ownership nor call I2C/mutex APIs from the display observer. Controlled start/stop needs arbitration of the existing shared state or deliberate replacement of all recognized owners; a saved Boolean followed by restore is unsafe. Stock compatibility is not required, but that does not make competing native accesses disappear.

## ALS: real code and ABI

`light-manager/function-0422b390.{c,asm}` initializes I2C bus 1 at 400000, registers setting callbacks for `0x5004` (automatic brightness) and `0x5904` (force activity), and tries driver factories in this order:

| Driver | Factory | Runtime table | Flash initializer | read(uint16_t*) |
|---|---|---|---|---|
| W1160 | `04348432` | `02010ce8` | `0439b3f8` | `043483b2` |
| MN12215D | `04347d74` | `02010cb0` | `0439b3c0` | `04347d02` |
| STK31860 | `043480a8` | `02010ccc` | `0439b3dc` | `04347efa` |

Each table is seven 32-bit fields: init, read, suspend, resume, identify, teardown, name. Successful init (return0) followed by successful identify (nonzero) sets availability bit1 in `02011628` and saves the selected table at `02011ac0`. Initializer's own return0 does **not** prove hardware detection. Identity should be reported by matching the pointer against these three fixed tables; no arbitrary pointer/string dereference is needed. Cached selected table is not sufficient by itself after teardown: `0422b522` unregisters settings, calls driver teardown and closes I2C without clearing that pointer in the exported code.

`int 0422b67a(uint16_t *out)` is the common sample API. `out` must be valid/aligned and owned by the caller; it is only written on success. Return1 means success, return0 unavailable/read failure. The entry has a48-byte frame. It checks shared flags before acquiring I2C1 lock (`043421d2(1)`), may call resume and sleep110 native ticks, invokes the selected read, optionally suspends, releases the lock (`04342200(1)`), and converts a successful raw16 value:

```
normalized = raw == 0 ? 0 : ((raw * 1000u) >> 16) + 1;
```

This gives0..1000 normalized native counts; **no lux calibration/unit proof**. Witnesses: `0422b6d6/da` lock call; `0422b6f0` resume; `0422b6f2` loads110 for delay; `0422b706` indirect read; `0422b71c` optional suspend; `0422b720/24` unlock; `0422b732..73e` multiply/shift/store; `0422b742` returns1. Locks route to the existing potentially waiting/asserting `0200ec3a` mutex API. No whole-chain time or stack bound established.

Flags in `02011628`: bit0 auto brightness setting; bit1 detected; bit2 resumed/running; bit3 force activity from5904. Bit4 is also tested for eligibility; its ownership is not closed in this pass. Read requires activity eligibility, detection/table/read pointer and bits2 or3. Ordinary readers include `0425e9ee` and `0425eef4` in display brightness processing, `042316f4`, and factory/test routine `0421fbe0`. The latter **changes persisted5904 and5004 settings** and is not a read-only diagnostic to reuse. `0422b746(out_id)` also performs live identify I/O under the bus lock; it is not a cached getter.

STK read `04347efa` reads registers13/14 and combines high/low bytes; null output asserts. STK probe `04347e10` expects ID82 from register3e, up to3 retries. MN probe `04347afc` uses I2C1/address49, register03 expected88; read `04347d02` reads4 bytes from39 and copies the final two bytes. This establishes concrete I/O, not the sensor physically fitted to the current glasses. W1160 init is exported in `ownership/function-0434830e.c`; full W1160 conversion calibration was not pursued.

`0422b5aa`/`0422b5e6` set/clear the one shared running bit and call resume/suspend. `0422b620` drives them from settings changes. They are not reference-counted acquisition tokens. Some resume/suspend calls occur outside the read function's I2C lock; taking that bus lock around a new caller alone does not prove complete power-state serialization.

## Brightness is not an ALS sample

`04261400` returns current queued brightness. `04261152(level)` clamps to1..10, queues display class5/event9 with one byte, and updates cached current level only if enqueue returns0. Prior queue evidence says zero does not universally prove display completion. `04261410(level)` validates1..10 then persists setting5003. GM service1/command0e checks type8, length1 and delegates to it; zero is rejected by lower setter despite outer `value<11` check. Service1/command0f accepts type8/length1 Boolean and delegates to `0426147c`, persisting5004. Disabling auto restores fixed brightness through queue and emits the existing phone notification. Query1/6 supplies the aggregate state; validate actual response echo, not merely command ACK.

`042612ec` registers the5003/5004 listeners and stores fixed/current/auto state at02011655/54/56. No light units follow from these levels. SDK `display_control.auto_brightness_block` is `04299e26`: it requires loaded-plugin singleton02011e24, tracks bit8 at plugin+19 and calls `0425f6c0(8,blocked)`. That lower API takes a shared bitmask, not a new CFW owner lease. Do not reuse the plugin bit or its singleton for unrelated appended code.

## Raw IMU and compass boundary

Existing `../input-adapter/report.md`, `../input-settings/report.md` and their exact native exports remain the ownership evidence. Host table0436609c+50→04299d1a (enable); +54→04299caa (read). SDK sample16 is accel signed16[3], gyro signed16[3], unconverted temperature signed16, calibrated whole-degree pitch signed16. The wrapper requires the active plugin's raw-mode flag; it is not a generally callable appended API.

Lower `bool 04228900(void *out14)` checks initialized/shutdown/valid state, increments active-reader count0200f9aa under critical section, waits on mutex0200f96c, copies14 bytes from0200f970, unlocks, decrements the reader count. It does not retain the output. Native frame/lock path contradicts the SDK's nonblocking claim. Read success does not give a hardware capture timestamp or new-sample guarantee. Calibrated pitch from04227cee is a separate read and is not proven atomic with those14 bytes.

Worker04227eca obtains a14-byte sample through0422a18c→04347344, executes the stock algorithm, then, when shared raw bit is set, copies the sample into0200f970 under the same mutex and marks valid. Its local sample is borrowed only during that iteration. A future additive capture directly after successful acquisition could copy14 bytes plus capture-tick and sequence into a bounded CFW record without sensor I/O or Bluetooth in that hook. That would establish actual sample freshness even if the stock raw-cache flag is off, but only while stock acquisition runs. It would not make START power-on ownership complete. Observer entry/register/FP preservation and private-context lifetime still require compiled tests before installation.

The driver factory04347ad0 selects the ICM42670 table02010c94. `04347922` reads WHOAMI75, expects69 and reports nameICM42670. Manager04229d9e supports its hardware-version branch, configures GPIO interrupt70 and calibration state. This evidence supports accel/gyro/temperature data, not a magnetometer. Conversion to g, degrees/sec, Celsius and sensor-to-display axes requires tracing the actual range/configuration and sample decoder; those units are intentionally left raw here.

No heading/magnetic vector producer, magnetic accuracy or G2-equivalent fusion source was established. Negative search boundary: ASCII strings in this pinned app body, public SDK sensor interfaces, the recovered IMU manager/driver and light-manager paths, and a bounded Android JADX keyword search (Google Maps compass UI hits are not glass sensor evidence). No ROM/B-core exhaustive sensor inventory, physical board identification or live register acquisition was done. It is therefore premature to claim absent hardware, or to synthesize compass heading from gyro/pitch.

## Smallest next implementation and required proof

1. Fixed diagnostic QUERY may return only allowlisted cached ALS selection/flags plus cached IMU validity/state, firmware/source ID and **no sample claim**. Snapshot related metadata in the existing reviewed critical primitive; do not expose RAM addresses or dereference arbitrary pointers. Active selected-driver identification remains unmeasured until live probe.
2. Passive capture QUERY/START/STOP can own only a CFW snapshot/ring, generation, lease and forwarding. START subscribes to actual native sampling without setting stock power bits; STOP/mode11 disables forwarding and invalidates the CFW generation, never invokes stock sensor shutdown. Report `sampling_unavailable` when stock is idle and explicit dropped count/sequence/tick; this is a useful scoped step, not full G2 passive-ALS/compass parity.
3. For an active sampler, use a dedicated normal worker with persistent owned context, not LVGL owner memory or display/BT blocking calls. Establish a single sensor arbitration point covering stock settings callbacks, power transitions, init/teardown and CFW requests. Since stock compatibility is excluded, replacing recognized owner entry paths is allowed, but must include the manager and lifecycle paths above. Do not patch flags directly or borrow plugin lifecycle state. Outstanding reads must complete before sensor/context shutdown; lease expiry marks cancellation, worker acknowledges, only then may context be freed.
4. Before implementation: model actual read functions with callback mocks for unavailable/drivererror/running and temporaryresume paths, sentinel outputs on failure, exact normalization endpoints0/1/65535, lock/unlock balance, shutdown interleavings, stream sequence/overflow/generation, STOP/cleanup idempotence and no delayed event after release. Validate hardware units/driver identity separately. Do not label G2's OPT3001 tenths-lux/peak/gear/scale fields as present on MemoMind: report unavailable metadata or define an explicitly native extension.

Current CFW graphics/diagnostic owners depend on the stock active launcher screen as their parent. Dashboard removal must replace this admission/parent/bootstrap relationship; deleting assets alone does not establish safe sensor or screen lifetime. Flash bytes and live screen heap are separate reclaimable resources.
