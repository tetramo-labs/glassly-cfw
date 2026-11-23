# Leased native microphone

Revision7 adds GM service15, command119 (`0f/77`), with one BYTES TLV.
The prefix is `MC 01 op`: configure1, status2, stop3, renew4. Status, stop and
renew are exactly four bytes. Configure is exactly thirteen bytes:

`4d 43 01 01 00 01 03 00 a0 00 a0 00 flags`

The supported native profile is source0, mono, codec3 (Opus), format0,
16,000 Hz and16,000 bps. Rate and bitrate use100-unit LE16 values. Flags2
starts capture; flags0 reserves a dry configuration without opening hardware.
Other profiles/flags are rejected. Codec3 is a MemoMind extension, not a claim
that G2's LC3, PCM, ADPCM, stereo or alternative sources are implemented.

Open the recording2024 channel before configuring. Configuration selects the
native49-byte framing directly; do not send legacy52 control packets. Native
52/11 start notifications and52/92 audio remain on the recording link. Each
49-byte record contains one40-byte Opus packet, representing320 samples at16kHz.
The app renews every30 seconds; the firmware lease is90 seconds.

A bounded JSON response carries the21-byte `MC` status in `stateHex`, plus
`serial`, `completed`, `pending`, `phase`, `error`, `nativeStatus` and
`nativeActive`. A queued response acknowledges admission, not audio startup or
shutdown. Poll status until the matching serial completes. Phases are idle0,
configured1, starting2, streaming3, stopping4 and fault5. Errors are none0,
busy1, no/unresolved link2, unsupported3, queue4, native5, expired6,
disconnected7, cancelled8, start timeout9, owner changed10 and schedule11.
Top-level `result` reports malformed, unsupported, busy or unavailable admission.

The native app task0x13 owns start/stop/configuration. Native recording startup
and cooldown are retained; its registered callback points at the CFW wrapper.
A generation-tagged task timer checks ownership every second. Task submission
and delayed-task APIs copy their small payloads. No audio driver, scheduler,
allocator or clock call runs under the custom critical section.

SPP and iAP2 send veneers gate only the2024 stream, matching the current peer
and channel. Other services, including local recording2026 and control/OTA,
continue through the original prologues. Lease expiry, stop, disconnect and
mode11 cut further enqueueing immediately. Previously queued native audio may
still arrive. The watchdog then requests native shutdown; an unsuccessful stop
remains stopping with `nativeActive=1`, rather than falsely reporting success.
A failed timer reschedule cuts transmission and attempts shutdown synchronously.
If shutdown also fails, another explicit stop is needed; this is not a proven
hardware power-off guarantee. Foreign recording ownership is never stopped.

Mode11 and launcher destruction cancel queued configuration and release the
microphone. Display frame release alone does not. Glassly's display clear uses
frame release so captions can continue listening while the screen is empty.

The owner uses48 bytes at offset160 of the existing boot-zeroed256-byte private
registry. No additional heap owner or task is allocated. The RX extension stays
within96KiB; this profile compiles geometry/vector with `-Os` and microphone code
with `-Oz`. Rendering throughput and actual device power behavior need hardware
acceptance. Host sanitizer tests, linked RV32 control tests, prologue/registration
checks and actual stock task/start/stop/reset/format ABI tests are distinct from
that hardware evidence.
