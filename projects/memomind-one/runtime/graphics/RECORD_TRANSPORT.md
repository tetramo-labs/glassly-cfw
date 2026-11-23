# Native compressed records

The optional `--record-transport` build uses the existing GM service 15,
command 0x7d display queue. Each request body is a kind-1 TLV containing
`[126, 1, sequence, flags, record bytes...]`. At most 128 record bytes fit a
packet. Packet and record flags, CRC16, persistent RFC1950 streams and ACK
history follow `../portable/TRANSPORT.md`. This is a native GM carrier, not the
G2 outer BLE framing. The single physical endpoint and origin are both 1.

The reply is a kind-5 JSON TLV with `glassly: record-transport`, `abi: 1`,
`frames` (hex native ACK/NACK/data frames), parser `status`, `nackReason`,
`ownedBytes` and `closing`. A zero status can contain a NACK; callers must check
frames. Each binary reply is limited to 64 bytes including its envelope.
Command data replies precede ACKs. Ordinary settled notifications remain
unsolicited. Nested record/raw carriers (126/127) are rejected.

The record session belongs to the display owner but survives until an active
command returns if that command deletes the owner. Its parser, partial input,
output and persistent decoder allocations share a 180 KiB budget and preserve
48 KiB free native heap. Revision6 allocates the 6 KiB JSON reply scratch only
during process/finish and frees it after the native reply has copied it. Context expires after 30 seconds independently of the
frame lease. Incomplete raw-message assembly excludes record processing.
Maximum encoded and decoded records are each 65,535 bytes; capacity does not
guarantee enough free heap for every combination of scene/cache/record state.

`inflater.c` embeds the byte-pinned zlib 1.3.1 sources under their original
license (`../vendor/zlib`). It accepts persistent SYNC_FLUSH streams, rejects
finished/overflowing streams, clears borrowed pointers and frees poisoned
contexts. The record parser retains its upstream attribution. No stock inflater
ABI or writable global decoder state is used.

The Swift `GraphicsRecordSession` probes capabilities, compresses using a
persistent platform zlib stream, checks correlated ACK length/CRC, and stops
on NACK, loss or malformed replies without replaying a command. It resets its
context before a message after 25 seconds idle. Native APIs and interrupts
are mocked in offline RISC-V tests; timing, heap coexistence and boot require
separate hardware evidence.

Required offline checks are registered in `tests/run_tests.py`: unchanged G2
transport scenarios with the production inflater, sanitizer carrier tests,
RISC-V decoder tests and the full native display-queue integration tests.
