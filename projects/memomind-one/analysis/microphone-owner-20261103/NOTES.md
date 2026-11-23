# Revision7 microphone ownership

Candidate `microphone-owner-001`, `GLASSLYCFW/7`, is constructed from the pinned
stock1.0.3.127 image with the existing minimal launcher, flash scenes and record
carrier. Exact image, runtime, container header and installed app header hashes
are in `pins.json`. No new physical flash region or RAM carve is introduced.

Build `build-07-03` uses the existing full profile plus `--microphone-control
--cfw-revision 7 --rx-profile app-rx-96k-v1`. Geometry/vector use `-Os`, microphone
uses `-Oz`; the runtime occupies98,304 bytes. The first build exceeded the96KiB
limit and was rejected; it was not packaged or flashed. The second candidate was
superseded before packaging by the native-start failure cleanup fix.

The constructor validates each stock witness before replacing the task0x13
callback address at0420980c/04209814, SPP transmit entry0431ca9e, iAP2 transmit
entry0431b88c and2024 link notifier04245cf4. Original recording task code stays
unchanged. Veneers align incoming stacks, preserve arguments/callee registers,
replay the exact overwritten prologues and rejoin the original functions.

Native task0420a316 performs start/cooldown and emits52/11. Stop0420a232 may fail
without clearing active0201196c. A failed start can leave state02011968=1 while
active is zero; native cleanup04209998 clears that state for the owned peer.
Format04209de8 selects legacy49-byte records. Local/stored recording uses2026,
which must not be gated as live2024. Audio driver, task and radio behavior remain
explicit mocks in offline evidence; do not mistake ABI validation for capture.

Host sanitizer tests cover cancellation before/during start, expiry, late starts,
stop retries, scheduling/queue failures, foreign ownership, dry configuration,
ambiguous links and clock wrap. Linked RV32 tests execute the service and owner,
check all memory accesses, verify veneers at both incoming stack alignments and
execute the constructor's patched callback address formation. Thirteen additional
cases execute the actual stock task/start/stop/reset/format routines with explicit
hardware mocks. Compressed records and existing image reconstruction checks also
pass on the exact candidate. Full regression and current hardware status are in
`checkpoint.json`.

Glassly uses the canonical Swift controller, an equivalent Android adapter,
30-second renewal and explicit shutdown polling. Clearing the display releases
only its frame, leaving microphone/notifications active. Both native clients and
the engine require revision7. Historical raw52 capture evidence remains valid for
its earlier image; it does not establish revision7 microphone acceptance.

The new profile is fixed16kHz mono Opus, codec3. Other G2 codec/source/channel
configurations are still missing. See `runtime/graphics/MICROPHONE.md` for failure
semantics, including the case where both watchdog rescheduling and native stop
fail. Actual lease expiry, disconnect, cleanup and renewed capture need hardware
checks. No physical audio or display acceptance is claimed by this checkpoint.
