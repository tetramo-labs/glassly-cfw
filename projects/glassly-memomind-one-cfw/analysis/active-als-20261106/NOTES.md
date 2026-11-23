# Active light sampling (GLASSLYCFW/14, 2026-11-06)

Revision 14 adds the firmware half of the G2's mode 16 to the sensor capture
command (service 15, command 118): a start carrying a 16-bit interval
(`53 43 01 01 mask interval`) makes the CFW read the light sensor itself at
that cadence. The Glassly App serves `session.lightSensor` on MemoMind over the
revision 10 passive capture since glassly `eff290eaa0`; on revision 14 it sends
the interval when the capability reply advertises `activeAls`.

## Design

- The sampling job is a generation-tagged delayed task on the app task 0x13
  (event 0x293, the same `0x042363f4` API as the 1 s watchdog, delay = interval).
  It calls the stock sample read `0x0422b67a`; the read's patched prologue
  (`glassly_sensor_als_entry`) publishes a success into the FIFO as for any
  stock read. The job re-arms itself while the generation is live with light
  active; a stale, stopped, sealed or expired generation ends it without a read.
- The stock reader only samples while auto-brightness keeps the sensor
  running (`0x02011628` bit 2). If bits 2 and 3 are both clear the start calls
  the stock settings listener `0x0422b620(0x5904, &1)`, which sets the force
  bit in RAM (the read then resumes, sleeps 110 ticks, reads and suspends under
  the I2C lock). The arena records `forced`; `dispose()` clears it with
  `0x0422b620(0x5904, &0)` outside the critical section on every release path
  (stop, restart, release, expiry via the watchdog, mode 11 cleanup, failed
  schedule). A sensor already running or forced is left alone.
- The arena grows from 784 to 788 bytes (`interval`, `forced`). The 48-byte
  owner slot and the wire replies are unchanged; passive 5-byte starts behave
  as before. Interval with an IMU-only mask, interval 0 or a 6-byte start are
  `invalid`; intervals clamp to 100..5000.
- Capability reply: `"activeAls":1,"activeAlsMinMs":100,"activeAlsMaxMs":5000`
  inside `sensors`. Revision 10 clients ignore the extra keys.

## Evidence

- `runtime/graphics/tests/test_sensor_capture.c` `active_sampling()`: force,
  restart, stop, cleanup, release, expiry, failed schedule and draining paths
  with mocked flags, listener and read (ASan/UBSan).
- `tests/rv32/sensor_capture_runtime_test.py` `test_active_light_sampling`:
  the linked RV32 runtime with `0x0422b67a`/`0x0422b620` as native stubs and
  the flags byte in mapped RAM; 9 groups pass (`sensor-capture-runtime.json`).
- `boot-selector-14.json`: first-run boot selection unchanged.
- Swift kit: `SensorCaptureCommand.activeStart`, `GMSession.sensorCaptureActiveStart`,
  catalog `active-als-001`; `swift test` SensorCapture/FirmwareImage 41 pass.
- Full regression: `regression-14-01` (see `checkpoint.json`).

## Not established

Not flashed: the Mac has not reached the glasses since the V12 attempt. The
native sampling cadence, the 110-tick forced-read sleep's cost on the app task,
the force's interaction with a user toggling auto-brightness, and whether the
stock reader's own tick coexists with ours are unverified on hardware. Prefer
intervals of 250 ms or more while the sensor is forced.
