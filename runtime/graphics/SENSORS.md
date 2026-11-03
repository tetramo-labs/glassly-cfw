# Passive sensor capture (GLASSLYCFW/8)

Service15 command118 (`0x76`) observes the stock sensor reads without changing
sensor power, polling rate or calibration. This is a latest-sample diagnostic
interface, not a lossless stream or a calibrated G2 sensor adapter. No compass
source is established. A successful start can have no samples until native
firmware reads a sensor.

Commands use a single binary TLV1. All lengths are exact:

| Operation | Bytes |
| --- | --- |
| Status | `53 43 01 00` |
| Start | `53 43 01 01 mask` (1 IMU, 2 ALS, 3 both) |
| Stop | `53 43 01 02` |
| Renew | `53 43 01 03` |

Start replaces the capture generation, clears validity and resets sequences.
The lease is90,000 RTOS ticks. Renew only extends a live capture; cleanup, stop
or expiry invalidates samples. Whole-session cleanup, mode11 and launcher
destruction stop capture. Releasing a display frame does not. The48-byte owner
occupies the final reserved registry slot at `0x0205e1f8`; no persistent heap,
worker or timer is added. Expiry is checked on commands and native read hooks.

A native read takes a generation token before I/O. Only successful completion
with the same live generation publishes a snapshot under the existing critical
section. The completion tick is sampled outside that section. Late reads from
an earlier generation, stopped captures and older completion ticks are ignored.
Sequence exhaustion disables that sensor; generation exhaustion refuses start.

Responses are JSON TLV5 bounded to208 bytes:

`{"glassly":"sensors","abi":1,"result":"ok","stateHex":"..."}`

Results are `ok`, `invalid`, `unavailable`, `exhausted` or `inactive`.
`stateHex` encodes52 bytes in lowercase hex. Multi-byte counters are little-endian.

| Offset | Bytes | Meaning |
| --- | --- | --- |
| 0 | 3 | `53 43 01` |
| 3 | 1 | Active sensor mask |
| 4 | 1 | Valid sample mask, subset of active |
| 5 | 1 | Fresh sample mask, subset of valid |
| 6 | 2 | Reserved zero |
| 8 | 4 | Capture generation |
| 12 | 4 | Reply RTOS tick |
| 16 | 4 | Lease deadline; zero when inactive |
| 20 | 4 | IMU sequence |
| 24 | 4 | IMU completion tick |
| 28 | 4 | ALS sequence |
| 32 | 4 | ALS completion tick |
| 36 | 14 | Seven signed big-endian register words: temperature, accel XYZ, gyro XYZ |
| 50 | 2 | Native normalized ALS, little-endian0..1000 |

Invalid samples have zero sequence, tick and data. Freshness means age at most
1,000 ticks for IMU or5,000 ticks for ALS, using unsigned tick subtraction.
These are RTOS completion timestamps, not hardware acquisition timestamps.
The IMU hook observes register0x09's14-byte read before the stock decoder's
right shifts and gyro-X sign change. Values have no advertised physical units.
ALS is the vendor's normalized value, not lux. Native power ownership and
sampling cadence remain vendor-controlled; client polling can skip sequences.

The Swift `memomind sensors` command validates capabilities, refuses to replace
an existing capture, logs snapshots, renews every30 seconds and stops on exit.
Swift and Android native clients validate the same wire layout. Glassly's
calibrated light/compass engine capabilities remain unadvertised until a native
power/units contract is implemented and verified on hardware.

Offline coverage includes sanitizer lifecycle/fault tests, linked RV32 service
and cleanup paths, constructed-image native acquisition/decoder hooks and
Swift/Kotlin rollover, malformed-state and lifecycle tests. Hardware sensor
response, cadence, orientation, power behavior and wake/sleep interaction remain
unverified for revision8.
