# Graphics fragmentation failure: exact inbound RFCOMM size mismatch

**Root cause: inbound RFCOMM requires642-byte fragment bodies (651-byte full
frames), whereas the host emitted503-byte bodies (512-byte frames).** The503
constant came from the native outbound serializer, which is not the inbound
RFCOMM stream-framing contract. This is not fixed by pacing/ACK wait alone.

## Capture evidence

A local read-only snapshot of the live capture is `hci-snapshot.btsnoop`;
[evidence.json](evidence.json) records its SHA256 and checks. TShark extraction
is [rfcomm.tsv](rfcomm.tsv). Phone HCI timestamps are offset from host JSONL
clock; correlate payloads/frame numbers, not equal timestamps.

- HCI25476: outbound512-byte FA fragment, declared overall5115.
- HCI25478: outbound512-byte continuation01, same declared/event/service/command.
- HCI25480: outbound512-byte continuation02.
- HCI25482: incoming44-byte STATUS8 `pkg parse error wait retry`.
- HCI25483: outboundcontinuation03; error preceded this frame on HCI, although
  host trace delivery interleaved it after that write was initiated.
- No incoming9-byte fragment ACK is observed between those first fragments and
  the error. Every individual host fragment checksum is valid. HCI preserves
  these512-byte RFCOMM payloads, so this is not an observed coalescing/truncation
  error in Android's writes.

## Exact native proof

Transport callback `0x042dfc8c`, registered for app dispatcher class0x0d, has a
separate RFCOMM stream reassembler before `0x042e8350`/`0x042f0306`:

- It initially collects7-byte header, reads logical length, initializes remaining
  to logical_length-9 for headFA, and saves event/service/command.
- At `0x042e16b2..0x042e16c4` it computes
  `expected_frame_bytes = min(remaining_body,0x282)+9`. Constants and branch are
  explicit in [assembly](../review/function-042dfc8c.asm).
- For continuations, `0x042e16ca..0x042e16f2` checks expected head, same overall
  logical length and identical three event/service/command bytes.
- It collects exactly that many stream bytes, then invokes parser. RFCOMM SDU
  boundaries do not override the expected frame size.
- After a valid frame it subtracts the frame's body bytes and advances head
  FA→01→02… (wrap to01 after heads>=f0). After a parse error it resets framing.

In this capture its first651-byte candidate consists of all512 bytes of hostFA
plus139 bytes of host01. That candidate's computed checksum is **0x24af**, but its
last two bytes are **0x001f**. This deterministically fails the native checksum
check, returning parser error3 and producingSTATUS8. It never accepts the first
fragment, explaining the absence of its ACK.

## Correct framing and ACK semantics

The5102-byte geometry data occupies5106-byte TLV stream (type1+u24length+data),
overall logical length5115. Divide that stream into642-byte bodies: **seven651B
frames and one621B final frame**, headsFA,01..07. All carry declared5115 and the
same event37/service15/command125; each checksum covers that individual frame's
header and body. Preserve every original TLV byte; do not insert a TLV header at
each continuation. [evidence.json](evidence.json) contains an offline corrected
plan, not packets sent to hardware.

Service dispatcher `0x042e70a4` sees parser return2 while incomplete. For0x7d,
it takes the normal ACK path calling `0x042e61cc(fragment_head,0,event,service,
command,NULL,0)`, generating an empty9-byte frame. ACK suppression applies to
specific stock plugin commands, not0x7d. ACK-paced sending is a useful confirmation
of accepted fragments, but no requirement to wait is enforced by the inspected
reassembly state machine. Keep bounded timeouts and stop onSTATUS8; do not keep
sending remaining fragments into reset state.

No device actions, transport sends, capture collector changes, or implementation
edits were performed in this investigation.
