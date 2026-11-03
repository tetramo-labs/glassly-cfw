# Revision 4: native compressed records

Candidate `record-transport-001` is GLASSLYCFW/4. Runtime 96,032 bytes fits the
existing 98,304-byte RX allocation. No additional stock flash/RAM carve is used.
The other five packed firmware components remain byte-exact.

Build recipe: use the revision3 command in `../ota-pacing-20261103/NOTES.md`,
add `--record-transport`, set `--cfw-revision 4`, and write a new build directory.
This candidate uses `build-02` and `image-01`. Build01 failed a compiler warning
before image construction; no firmware was transferred from it.

The original G2 transport scenario assertions run unchanged against the pinned
production inflater as well as the prior host shim. Native RV32 tests cover
compressed drawing, persistent dictionaries, maximum record size, CRC rejection,
lease expiry and mode11 destruction from inside dispatch. The decoder tests
exercise dynamic/fixed/Huffman blocks, allocation failures, two contexts,
borrowed-pointer cleanup and overflow/finished-stream rejection. Sanitizer
carrier tests cover every observed allocation failure and deferred destruction.

The older base graphics gate harness assumes the non-observer stack boundary
and fails on this full profile. The notification/wake-aware gate harness passes
512 service cases and 14 pre-stock cases on the actual candidate. No production
code was changed to accommodate that obsolete harness. Observed linked stack
use is 912 bytes with native APIs mocked, not a hardware interrupt/task bound.

`hardware.swift` checks exact installed headers/topology, notification control,
position/depth change and restoration, compressed drawing/dictionary reuse,
65,535 decoded bytes, binary diagnostic replies and cleanup from a record.
It does not generate real iOS notifications or confirm physical display output.
`verify-ota.py` independently reconstructs the full OTA from callback traffic;
this is not an independent HCI capture. Reboot ACK and verified boot are separate.
