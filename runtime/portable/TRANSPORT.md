# Portable message-record transport

`transport.c/.h` is a derivative of G2 `patches/message_transport.c`,
`message_transport.h`, and the protocol checks in `transport_compression.c`,
pinned at commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. The unchanged license
is `LICENSE`; the bundled source and exact hashes are in
`tests/g2_compat/upstream` and `tests/g2_compat/UPSTREAM.json`. Original comments
in the extracted parser/ACK routines are retained. This is production portable
code, not an inclusion of the upstream firmware module or its hardware stubs.

The core takes a caller-owned `mm_transport` and platform callbacks. It has no
firmware addresses, global writable state, Bluetooth operations, native queues,
clock, display access, hardcoded heap or zlib ABI. It reconstructs ordered
records and invokes a synchronous handler. No MemoMind device adapter or native
inflater is supplied, and these host tests do not establish hardware parity.

## Boundary and ownership

Initialize an unused/zero context with `mm_transport_init(ctx, platform,
endpoint, max_record)`. Logical endpoint bits 1/2 and origin slots 1/2 preserve
the original destination/subset semantics; they are not a claim that MemoMind
has independent G2-style lens CPUs or links. A single endpoint implementation
can use endpoint/origin 1. A future adapter decides the actual routing and
forwards selected destinations; the core never forwards requests on its own.

`mm_transport_receive` accepts an origin, sequence byte, packet flags, borrowed
record bytes, and a verified reply capacity. The adapter must validate its outer
wire format and integrity, route identical ordered packets to selected logical
destinations, and guarantee capacity for at least the 9-byte ACK. Capacity
includes the 5-byte data-reply or 9-byte ACK envelope and is bounded to255 bytes.
A hint can raise known reply capacity; dispose/reinitialize when the link or
capacity contract changes. The test adapter translates the G2 outer format;
MemoMind GM framing must be handled by a separate implementation.

The caller serializes all operations on a context, including both origin slots,
hints and disposal. Callbacks must not reenter the context or dispose/reinitialize
it. The context and platform must remain alive throughout calls. Packet bytes
must stay stable, and must not alias context/parser-owned buffers. Allocation
and release callbacks own the parser's buffers; the handler receives borrowed
decoded bytes valid only until it returns. Reply and send callback buffers are
likewise borrowed synchronously; a queueing adapter must copy before return.

`mm_transport_dispose` releases partial record data and retained inflater state,
zeros the context and is idempotent. It sends no teardown messages. Do not call
init on a live context without disposal. `mm_transport_abort` invalidates an
active reconstruction and sends one NACK; repeated aborts of the now inactive
stream produce no more replies. An adapter receiving a corrupt outer packet
can use this API rather than passing unchecked bytes to the parser.

## Record, reset and reply semantics

Each record is `[flags:u8][wire_length:LE16][decoded_crc:LE16][body]`. The clear
five-byte header and body may split anywhere across packets. Body lengths are
0..65535, further bounded by the caller's nonzero `max_record`; decoded size is
bounded by the same value. CRC is CRC-16/CCITT-FALSE (poly1021, initialffff), over
the uncompressed body. The check vector `123456789` yields29b1.

Record flag bits are destination1/2, compressed4 and reset-context8. Packet flag
bits are destination1/2, RESET80 and END40. A record's nonempty destination set
must be a subset of the packet stream's set. A valid record for another endpoint
is consumed silently: ordinal advances, handler/ACK do not run, and that local
inflater/reset/history state is untouched. Thus a skipped reset cannot provide
another endpoint's compression context.

Packet RESET restarts reconstruction/ordinal/sequence but deliberately retains
completed-record compression context. It NACKs an unfinished prior record.
Record RESET_CONTEXT clears the inflater and ACK history and establishes a new
valid context, including for plain records. A fresh addressed record without
this flag NACKs for missing context. END requires a complete record boundary;
partial headers/bodies NACK, discard and return11. Sequences wrap at255; gaps or
changed stream options abort with10. A caller should impose its own inactivity
timeout and call abort/dispose; the core does not invent a clock or timeout.

Successful records produce ACK kind1 with stream ID, ordinal, endpoint, decoded
size and CRC; up to three prior explicit successful records follow when verified
capacity allows. Skipped records never appear as successes. History records
processing even if enqueueing its ACK fails, so a later ACK can repair lost
acknowledgement without reexecuting the handler. Failure replies are kind3;
record flags/context/inflate/CRC/handler failure reasons1..5 are retained in the
context diagnostics. Reason6 is the portable extension for configured length
limit rejection. Framing/abort failures follow upstream behavior and need not
increment the record-failure diagnostic counter.

A handler can write at most the provided reply capacity and set its reply length.
Kind5 data replies precede the corresponding ACK. Reply buffers are per origin
slot, never a shared global. Handler failure invalidates compression context;
handler side effects are not rolled back by the transport. A successful handler
followed by send failure remains processed; the API returns6, and callers must
not blindly execute the same command again assuming nothing happened.

API returns0 for completed processing, including a rejected record whose NACK
was sent;6 for resource/send failures;10 for sequence/metadata failures;11 for
truncated END. Inspect received reply kind/diagnostics rather than treating
return0 as an application ACK.

## Compression and resource limits

The optional `decode/end` pair is explicit. The decoder must implement a
persistent RFC1950 stream across records, consume all input, reject Z_FINISH,
and clear borrowed pointers before returning. Core additionally checks the
four-byte SYNC_FLUSH tail `00 00 ff ff`. It gives the decoder `max_record+1`
output bytes so expansion overflow is observable, then rejects output over the
limit. End must release all retained decoder state even after decode failure.
Missing decoder support yields an inflate NACK for compressed addressed records.

Wire reconstruction allocates at most `max_record` per active origin. Compressed
processing additionally allocates `max_record+1` output bytes, plus
platform-owned inflater memory. Two origin slots can retain separate partial
buffers and decoder states. A max-record limit is not a total heap budget;
allocator callbacks must enforce the actual budget and fail safely. No native
MemoMind zlib decoder, allocation headroom or scheduling deadline is asserted.

The portable parser is synchronous and does not yield. Its work scales with the
packet bytes, CRC bits and handler/decoder work. A device adapter must separately
bound total packet/command work, inflater expansion cost and handler execution.
Compiler per-function stack measurements exclude callbacks and native interrupt
context; they do not establish a whole-task stack bound.

## Deliberate differences from pinned upstream

* Explicit caller context, platform callbacks, logical identities and adapter-
  verified capacity replace global/native lookups and G2 outer routing.
* A caller-chosen wire/decoded length bound rejects oversized records before
  allocating their body; limit failure discards the active stream.
* Reported handler reply lengths exceeding its capacity become handler NACKs.
  The handler must still obey the supplied buffer bound while writing.
* Failed kind5 send is propagated as API error6 while the ACK still records
  successful handler processing. Upstream ignored the kind5 send result.
* The test-only G2 bridge adapter rejects two-byte returns before reading byte2,
  fixing an upstream out-of-bounds read. This is not a new native bridge hook.

## Verification and source preservation

Run from the workspace:

```
python3 runtime/portable/tests/run_transport_tests.py --output /tmp/mm-transport-check
```

The output directory must be new. The runner verifies the source pin/hashes,
reproducible test binding, **all original assert expressions**, literal message
fixtures and complete bodies of the five original scenarios:
`subset_records`, `outside_records`, `compressed_records`,
`skipped_reset_is_not_borrowed`, and `handler_failure`. Original split sizes,
context continuity and final allocation-leak assertion remain intact.

Only setup/context allocation, disposal and original outer-wire/hardware entry
points are rebound. `tests/transport/original_adapter.h` explicitly supplies a
host-only G2 two-lens routing/outer-header simulation; `host_zlib.h` supplies host
zlib. These are test scaffolding, excluded from production `transport.c`.
`prepare_original.py --check` verifies that the generated test source is current.

Additional public-API tests cover every truncation and split of a representative
record, sequence wrap/gap, abort-once, partial RESET, invalid inputs/capacity,
CRC mismatch and explicit recovery, handler failure, max-length65535, configured
limits, zero-length record, per-origin interleaving, reply-before-ACK, oversized
reply reporting, data-reply send failure, ACK history after send failure,
maximum reply/history bounds, absent decoder, bad flush/finished streams,
expansion overflow, failure at every observed inflater allocation, and disposal
with retained inflater plus partial input. Both host executables run with ASan
and UBSan. Freestanding RV32 builds verify no unresolved imports or writable
globals, record layout, code size and compiler stack frames.
