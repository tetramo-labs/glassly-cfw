# Revision9: acknowledged sensor buffering

GLASSLYCFW/9 (`sensor-buffer-001`) retains32 native IMU/ALS observations and
returns up to four records per poll. Generation-checked ACKs release only
acknowledged records. Full buffers overwrite their oldest record and increment
a saturating loss counter. A repeated ACK returns the retained records again,
subject to concurrent overwrites. Global sequence gaps remain visible to clients.

Start allocates a bounded784-byte arena; stop, whole-session cleanup, expiry and
watchdog scheduling failure detach and free it. The existing app worker handles
a generation-tagged1,000-tick watchdog, so a disconnected client does not need
to poll for lease cleanup. Acquisition hooks only copy bounded data under the
critical section. Allocation/free/scheduling occur outside it. Old watchdogs and
late reads cannot invalidate or publish into a later capture generation.

The runtime is96,208 bytes with2,096 bytes remaining in the96KiB RX region.
The owner still uses the existing48-byte registry slot. This adds784 bytes of
heap while a capture buffer is retained; restart can briefly hold1,568 bytes
of arena storage. Reply/native allocator overhead is additional. This is not
a RAM-saving claim.
Native sensor power and cadence remain untouched. Native normalized ALS is not
lux, and IMU register words have no new physical-unit claims. Sensor activation,
calibration, compass and scheduler/hardware acceptance remain open parity work.

The first build failed compiler indentation warnings and produced no image.
Build02 is the pinned candidate. Host sanitizer tests cover retained replay,
ACK bounds, overwrite counts, stale reads/watchdogs, expiry and failure cleanup.
Five linked RV32 groups cover the same control/ownership boundaries, plus16
constructed-image acquisition-hook cases with native stock decoding and mocked
bus/RTOS calls. Exact pins and the reproduction recipe are retained here.

Swift and Kotlin decode the same bounded batch protocol. Glassly includes V9,
requires revision9 and exposes the native batch methods. The Mac tool logs a
batch durably before advancing its ACK, drains backlogs, renews the lease and
reports sequence gaps and overwrite counts. Stop intentionally discards unread
records. There is no lossless-recording promise. Generic engine light/compass
capabilities remain unadvertised. The proven OTA implementation is unchanged.

The read-only connection probe timed out after45 seconds with only capture,
attempt and connect-intent records. There were no transmit submissions and no
OTA invocation. No Bluetooth settings were changed. V6 remains the last
boot-verified installed image; V7/V8/V9 have no new hardware acceptance.
connection-attempt.json pins the sealed local trace. A separate verifier check
uses historical V6 evidence and is explicitly not a V9 transfer proof.

App results are in app-verification.json. The full required regression result
and source bindings are recorded separately in regression-verification.json.
Hardware timing, native power arbitration, physical readings, full sensor/G2
semantics and the remaining original integration suites remain incomplete.
