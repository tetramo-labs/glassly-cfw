# Revision 10: drainable sensor capture

GLASSLYCFW/10 (`sensor-drain-001`) closes the normal-completion tail loss in
revision 9. FINISH validates the capture generation and saved ACK, stops further
publication atomically, and preserves the remaining FIFO records for 30,000
RTOS ticks. Repeating FINISH does not extend this deadline. Late reads cannot
append to the frozen generation. The existing watchdog reclaims the buffer
when the deadline expires; explicit cleanup and restart still discard it.

Batch ABI 2 reports inactive, capturing or draining at header byte 27. A separate
RELEASE command validates generation and ACK before freeing the buffer. It is
idempotent for the same generation and cursor and cannot release a newer capture.
RELEASE may deliberately abort unread data; successful release alone does not
prove that samples were saved. The older unscoped STOP remains an abort operation.

The Mac recorder freezes at the requested end time, saves each returned batch
before advancing ACK, confirms an empty tail with ACK equal to the final produced
sequence, then releases its generation. Drain requests are bounded to nine:
eight four-record batches plus an empty confirmation. Swift and Kotlin clients
reject changes to the frozen terminal sequence or overwrite count. Save failures
cannot advance the ACK. The recorder uses generation-checked release on errors,
which can discard unread records, and reports completion only after normal drain.

This uses the existing 784-byte arena and 48-byte registry slot. Internal validity
bit 7 records the frozen phase without exposing it as sample validity. Runtime
size is 96,448 bytes, leaving 1,856 bytes in the 96 KiB RX allocation. The final
candidate is build/image 10-02; build 10-01 preceded generation-checked release
and was never transmitted. Image/runtime/header pins and source recipe are here.

Host ASan/UBSan tests and eight linked RV32 groups cover freeze/replay, overflow,
ACK validation, stale generation, late publication, response allocation failure,
release idempotence, queue failure, cleanup and deadline rollover. Sixteen
constructed-image native hook cases still execute the stock sample decoder with
mocked bus/RTOS boundaries. App validation is 120 Mac, 12 iOS simulator, 26 Android
and two engine tests. Initial app runs exposed an old expected command sequence
and an outdated Android firmware byte count; final runs include those corrections.
The full regression and source-binding results are recorded separately.

The read-only probe stalled for 45 seconds with only connection-intent records
and zero transmit submissions. Its sealed capture retains the initial
`sensor-read-20261103-probe-01` name. No OTA or Bluetooth settings changes occurred.
V6 remains the last boot-verified image. V10 drain timing, sensor response and
watchdog scheduling have no new physical acceptance.

Sampling is still passive: it observes native reads without owning sensor power.
Normalized ALS is not lux, and IMU register values are not calibrated physical
units. Active power arbitration, compass, remaining G2 integration suites and
other hardware acceptance remain incomplete. This release does not claim full
sensor or G2 parity. The existing Swift OTA transport is unchanged.
