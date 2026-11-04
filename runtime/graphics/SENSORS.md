# Buffered passive sensor capture (GLASSLYCFW/10)

Service 15 command 118 (`0x76`) observes stock sensor reads without changing
sensor power, polling rate or calibration. Revision 10 adds a frozen tail and generation-checked release to the
32-record FIFO. It is bounded capture, not a
lossless stream or calibrated G2 sensor adapter. No compass source is established.
A successful start can have no samples until native firmware reads a sensor.

Commands use a single binary TLV 1. All lengths are exact. Integers in commands
are little-endian.

| Operation | Bytes |
| --- | --- |
| Status | `53 43 01 00` |
| Start | `53 43 01 01 mask` (1 IMU, 2 ALS, 3 both) |
| Stop | `53 43 01 02` |
| Renew | `53 43 01 03` |
| Batch | `53 43 01 04 generation:u32 acknowledged:u32` |
| Finish | `53 43 01 05 generation:u32 acknowledged:u32` |
| Release | `53 43 01 06 generation:u32 acknowledged:u32` |

Start replaces the capture generation, clears validity and resets sequences,
ACK and drop counts. The lease is 90,000 RTOS ticks. Renew only extends a live
capture; stop, expiry, whole-session cleanup, mode 11 and launcher destruction
invalidate samples and release the buffer. Releasing a display frame preserves
capture. Start allocates 784 bytes with a 32 KiB heap reserve. Allocation failure
leaves a prior capture intact. Restart can briefly hold two arenas (1,568 bytes)
before freeing the old one; reply scratch is at most 384 bytes, excluding native
JSON/allocator overhead. Scheduling failure cancels only the generation
whose watchdog could not be queued. The 48-byte owner remains at `0x0205e1f8`. Its internal validity byte uses
bit 7 for the frozen phase; that bit is never exposed as sample validity. No
additional heap or registry storage is required by finish/release.

The existing app worker receives a generation-tagged watchdog every 1,000 ticks
while capture is active. It reclaims expired buffers without requiring host
polling, subject to native worker scheduling. Native acquisition hooks never
allocate, free or schedule work. All owner/buffer accesses are protected by the
existing short critical section. Detachment happens under that lock; freeing
happens after it. No new task or LVGL object is created.

A native read takes a generation token before I/O. Successful completion with
the same live generation publishes a sample and FIFO record. Old-generation,
stopped and out-of-order per-sensor completions are ignored. The RTOS completion
tick is sampled outside the critical section. FIFO ordering reflects publication
order, not a guarantee of timestamp order across different sensors. Sequence
exhaustion disables capture instead of wrapping. Each successful publication
increments its per-sensor latest-sample sequence and the combined FIFO sequence.

## Finishing and releasing a capture

Finish validates generation and ACK before changing state. It atomically disables
publication, applies the ACK and returns the first retained batch. In-flight reads
cannot append after that boundary. The final sequence and overwrite count remain
fixed. The retained buffer has a 30,000-tick deadline; repeated finish, status,
batch and renew requests do not extend it. Renew reports inactive while draining.
The watchdog also reclaims frozen buffers. Display clear preserves them; full
cleanup, restart and the old unscoped stop operation discard them.

Drain with batch requests until pending is zero and the firmware acknowledges
the final sequence. Release then frees the matching generation and returns
`released` with phase inactive. Release can also abort an active or partly drained
capture; it discards unread records, so it is not evidence that they were saved.
Repeated release with the same generation/ACK succeeds. A stale generation or
invalid ACK cannot stop a newer capture. Allocation failure while constructing
a reply may follow a successful state change; retrying finish/release is safe
only with the same generation and a previously saved ACK.

## Latest-sample reply

Control/status replies remain JSON TLV5 bounded to 208 bytes:

`{"glassly":"sensors","abi":1,"result":"ok","stateHex":"..."}`

Results are `ok`, `invalid`, `unavailable`, `exhausted`, `inactive`,
`allocation-failed` or `schedule-failed`. The 52-byte lowercase hex state is:

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
| 36 | 14 | Seven signed big-endian words: temperature, accel XYZ, gyro XYZ |
| 50 | 2 | Native normalized ALS, little-endian 0..1000 |

Counters are little-endian. Invalid samples have zero sequence, tick and data.
Freshness means age at most 1,000 ticks for IMU or 5,000 ticks for ALS, using unsigned
tick subtraction. These are RTOS completion timestamps, not hardware trigger
samples. IMU capture precedes the stock decoder's right shifts and gyro-X sign
change. Values have no advertised physical units. ALS is normalized, not lux.

## Buffered reply and ACK

Batch replies are JSON TLV5 bounded to 384 bytes:

`{"glassly":"sensor-batch","abi":2,"result":"ok","stateHex":"..."}`

`stateHex` contains a 28-byte header followed by zero to four 24-byte records:

| Offset | Bytes | Meaning |
| --- | --- | --- |
| 0 | 3 | `53 42 02` |
| 3 | 1 | Active sensor mask |
| 4 | 4 | Capture generation |
| 8 | 4 | Reply RTOS tick |
| 12 | 4 | Acknowledged combined sequence |
| 16 | 4 | Last produced combined sequence |
| 20 | 4 | FIFO overwrites, saturating |
| 24 | 1 | Pending records before this reply, including returned records |
| 25 | 1 | Capacity 32 |
| 26 | 1 | Returned records, at most 4 |
| 27 | 1 | Phase: 0 inactive, 1 capturing, 2 draining |

Each record has a little-endian sequence at 0, completion tick at 4, kind at 8
(1 IMU, 2 ALS), zero at 9, and 14 sample bytes at 10. IMU uses the same seven
big-endian register words; ALS uses two little-endian normalized bytes and 12
zero bytes. Buffered sequences are global across both kinds. They differ from
the per-sensor sequence fields in the latest-sample response.

A batch requires the current nonzero generation and an ACK between the previous
ACK and last produced sequence, inclusive. It removes only acknowledged records
and returns the oldest retained records. Repeating an ACK does not consume them;
concurrent production may still overwrite the oldest records when full. Each
such overwrite increments `drops`. A generation mismatch returns `stale`; a
backward or future ACK returns `invalid`; an expired/stopped capture returns
`inactive`. Capturing has a nonzero active mask; draining/inactive have mask zero.
Successful batch/finish replies may be capturing or draining. Release replies
have no records and phase inactive. Rejected requests do not acknowledge records. Error replies return
zero records. FIFO data is copied under the lock before response construction.

ACK only records durably saved by the client. Sequence gaps and the overwrite
counter expose FIFO loss; they do not count failed native reads or reads made
outside a capture lease. Stop/restart/cleanup deliberately discard unread
records. Buffered capture therefore makes no lossless-recording guarantee.

## Clients and verification

Swift and Android native clients validate lengths, reserved bytes, units,
sequence continuity, ACKs, generation and tick rollover. The Mac tool drains
backlogs, logs each batch durably before advancing its ACK, renews every 30 seconds
and reports observed gaps/overwrites. On normal completion it freezes, drains at
most eight batches plus an empty ACK confirmation, then releases the generation.
On error it attempts a generation-checked abort; unread records may be lost.
Swift and Android native adapters expose the same bounded drain operation and
reject changing terminal counters. A failed save callback cannot advance ACK.
Capabilities require revision 10, batchVersion 2, finish 5, release 6 and
drainTicks 30000. Batch ABI 1 is no longer accepted. Generic engine light and
compass capabilities remain unadvertised until power/units contracts exist.

Sanitizer tests and linked RV32 tests cover replay, overflow, malformed ACKs,
allocation/queue failures, stale watchdogs, expiry and cleanup. Constructed-image
hooks run with stock acquisition/decoder code and mocked bus/RTOS boundaries.
Physical sensor response, timing, orientation, power behavior, scheduler latency
and sleep/wake interaction remain unverified for revision 10.
