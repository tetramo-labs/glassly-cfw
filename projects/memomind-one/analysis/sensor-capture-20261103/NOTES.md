# Revision8: passive sensor snapshots

The `sensor-capture-001` candidate is GLASSLYCFW/8. It includes revision7's
microphone owner and adds passive timestamped IMU/ALS snapshots. Exact image,
header and runtime hashes are in pins.json; recipe.json records source hashes
and compilation profile. Sensor support uses48 reserved registry bytes and no
persistent heap. Applying `-Os` to graphics C sources makes the runtime94,608
bytes, leaving3,696 bytes in the existing96KiB region. This is code-space saving,
not a measured heap saving. No new flash region is carved.

The implementation builds on the604-case native ABI investigation in
../sensor-abi-20261103. The IMU hook sits at the original14-byte bus read call
before stock decoding; ALS wraps its native normalized read. Each hook records
a generation before I/O and publishes only a successful current-generation
completion. It preserves stock return values and decoder output. Active power
control is deferred because ALS shares unsynchronized native power state; raw
values are deliberately not presented as calibrated G2 sensor readings.

The required regression runner now includes the sensor host and linked runtime
stages. The latter runs the actual constructed-image hooks with stock IMU and
ALS code while mocking bus/RTOS functions. Counter wrap, freshness, stale
completion, stop/restart, expiry, whole-session cleanup, malformed commands,
allocation failure, bounded memory and preserved native output are covered.
The source pin in sensor_native_abi_test.py is named STOCK_SHA so the rebuilt
runtime adapter cannot rebind the stock firmware pin.

The first runtime link failed because size optimization emitted memset. A
freestanding byte-wise memset resolved the undefined symbol before build02.
No image from that failed build was flashed. Build02 and image02 are the
candidate verified by image-verification.json, rv32-03.json and catalog-inspect.

Swift and Android clients expose the native sensor command, and the Mac CLI
records latest snapshots with lease renewal and cleanup. Glassly's installed
firmware catalog and engine admission now target revision8. The existing OTA
implementation is retained. App results are in app-verification.json; the
vendored source provenance is pinned in Glassly's UPSTREAM.json.

No revision8 OTA was started. The host Bluetooth power query stalled for10s;
the read-only probe was terminated after45s with only capture/attempt/connect
intent records, no transmit submission. Raw captures remain local and sealed;
connection-attempt.json pins the trace. No global Bluetooth settings were
changed. A connect intent is not a connection or a boot check. Revision6 remains
the last installed and boot-verified version. Revision7 was never flashed.

Still required: live sensor sampling and timing, physical orientation/scaling,
native power ownership, compass source, sleep/wake behavior, revision7 microphone
lifecycle/audio acceptance, and the remaining original G2 integration suites.
Out-of-scope hardware features remain excluded. Offline passes do not establish
full parity or hardware acceptance.
