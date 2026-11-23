# Native sensor acquisition and ownership checks

604 offline cases execute pinned stock RV32 instructions for ALS reads,
resume/suspend/settings, IMU cached/direct acquisition, start/stop/raw-enable,
and the ICM42670 sample decoder. They pass. The test is a required aggregate
stage; an injected failure makes the aggregate fail. No sensor command or new
firmware image is installed by this change.

Run:

```
.tools/rv32-tests-venv/bin/python tests/rv32/sensor_native_abi_test.py --report NEW_REPORT.json
```

The stock body SHA256 is
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
`verification.json` pins the source and local full report. Exports were obtained
from the existing Ghidra project using read-only/no-analysis sessions. Raw code
exports and full generated results remain local.

## Sample format correction

The driver table initializer at `0x0439b3a4` points to read function
`0x043475cc`. The native manager `0x0422a18c` calls `0x04347344(out,0,0)`,
which dispatches through that table. Tests execute this whole path, mocking only
the bus transfer at `0x0434742e` and disabled logging on errors.

The read requests 14 bytes starting at register `0x09`. On success it converts
seven big-endian signed words in order temperature, accel XYZ, gyro XYZ.
With the normal manager's third argument zero:

* All six motion axes are arithmetically shifted right by four bits.
* Gyro X is negated after that shift.
* The output is six little-endian signed motion words followed by the original
  temperature word, without a temperature conversion.

For example, register words `[-32768,-32768,-17,-16,-1,0,32767]` become
`[-2048,-2,-1,1,0,2047,-32768]`. The nonzero-third-argument driver path preserves
the six full-resolution axes and their signs but leaves output bytes12–13
untouched. Tests use a sentinel to detect this. Neither path supplies a capture
timestamp, compass heading, magnetic accuracy or proven physical units. The
SDK's separately read pitch does not change these properties.

Consequently, the existing 14-byte cache is native reduced-resolution data,
not a lossless raw-register stream. A full-resolution observer must capture
before this transformation; selecting the alternate path alone also requires
handling its absent temperature field. No conversion to g, degrees/sec or
Celsius is advertised here.

## ALS and ownership results

Actual `0x0422b67a` reads normalize successful raw values as
`raw == 0 ? 0 : (raw * 1000 >> 16) + 1`. Output ranges0–1000 and is not proven
lux. Tests cover all low-five-bit eligibility combinations, absent tables/read
callbacks, normalization boundaries, driver errors, optional resume/suspend,
the110-tick resume delay and injected state changes during the driver call.
The output sentinel survives failure, and the bus lock/unlock sequence balances.

The native resume/suspend routines and settings callback execute separately in
the suite. They do not acquire that bus lock. Their running bit may change even
when a table or callback is absent; it is not proof of hardware completion.
Turning automatic brightness off can suspend the sensor independently of a new
reader. Setting5904's force bit does not turn this into a per-client lease.
The tests expose these semantics; they do not make them safe for a new owner.

IMU enable sequence `[1,1,0]` starts once and then clears the shared owner bit
and stops processing. Two callers do not receive independent references.
Raw-cache enable also writes one bit and never starts acquisition by itself.
Busy-stop returns success while the running flag can remain set. A future
controller must distinguish command return from completed sensor shutdown.

Cached reads increment a16-bit active-reader count before taking the mutex.
An injected shutdown after admission does not cancel the in-flight copy; it
finishes and releases its reader count. Admission while shutdown is already set
fails without copying. The counter is not saturating: an initial65535 wraps to
zero. This is a native boundary test, not evidence of that many physical readers.

## Verification limits and next implementation

The suite checks callee-saved integer registers, return/stack restoration,
16-byte stack alignment, permitted writes and output canaries. Mock returns
clobber caller-saved registers. Bus/driver functions, mutexes, critical sections,
RTOS signaling, logging and lower power operations are explicit mocks. Injected
state changes model selected interleavings; they do not establish scheduler
coverage, electrical behavior, whole-chain stack use or physical sensor identity.

The next native adapter needs a bounded snapshot with capture tick, sequence,
generation and lease; stale/in-flight samples must not cross STOP/restart.
Passive capture can avoid changing sensor power, but must report stock sampling
unavailability. Active start/stop additionally needs arbitration across settings,
power, teardown and outstanding reads. Compass remains unresolved and in scope.

## Device attempt

Revision7 preflight22 produced an empty traffic trace and stalled for over
three minutes. Independent read-only connection-list and power queries also
stalled. Only those task-owned processes were terminated. No OTA was invoked;
there was no boot or sensor hardware verification. This is a Mac Bluetooth API
stall, not proof that the glasses were asleep. The prior sealed21-attempt search
is unchanged. See `connection-attempt.json` for image/runtime pins and evidence.
Revision6 remains the last verified installed image; revision7 remains the
candidate already bundled and pushed in Glassly.
