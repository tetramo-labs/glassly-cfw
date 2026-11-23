# Microphone control boundary

Stock application body SHA256:
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
This is read-only analysis; no microphone lease adapter is installed by this work.

The recording service registers link/data callbacks through `0424613a`.
Its three slots are at `02013c70` (link) and `02013c98` (data). Registration
requires both entries in a slot to be empty; unregister `042461c0` clears a
matching pair. Data forwarding at `04245d3c` supplies transport, peer, bytes and
length. The recording callback at `0420aaa8` drops the transport argument and
tail-calls `0420a7da(peer, bytes, length)`.

The actual parser, including that callback, passes 38 Unicorn cases in
`parser-verification-final.json`. Native task posting, transport send, recorder helpers,
settings and logging are explicit mocks; this is not an audio/device test.
The test checks callee-saved registers, stack alignment, untouched input and
peer buffers, exact event payloads and negotiation replies.

- `52 12 flag` requests negotiation. Only flag1 selects the alternate boolean;
  the response is `52 13 selected 31 28 00`. SPP, iAP2 and BLE route selection
  is exercised, without claiming live transport support from these mocks.
- `52 01 kind` posts task `0x13`, event1, with six peer bytes followed by the
  selected recording kind. An override is accepted only when the native default
  at `020115ff` is5 and kind is1–7 excluding2. Other values preserve the default.
- `52 00` calls the stock stop-preparation helper. Unless the native state at
  `02011968` is2, it restores recording kind5 and posts task `0x13`, event2, with the
  six-byte peer. State2 suppresses that post; its lifecycle meaning is not yet
  verified and must not be bypassed by a new adapter.
- Short and unknown packets are ignored without posting a recording command.

Read-only task-handler follow-up identifies `0420a316` as task `0x13`.
Stop event2 cancels pending event1, then calls `0420a232` only when the active
flag `0201196c` is nonzero. Start event1 honors a deadline at `02011960`,
rescheduling itself when needed. Stop preparation sets that deadline to native
clock plus1,500; negotiation stores its boolean at `02011964`. These task paths
are decompilation findings, not part of the 38 parser execution cases. The stop
handler does not visibly compare the requesting peer before stopping, so a new
lease must establish ownership independently. Recording-kind reset is distinct
from a stop-reason field.

A leased adapter still needs the native task-handler lifetime, active peer and
recording-state ownership, codec/configuration support, disconnect behavior,
lease expiry and mode11 cleanup. A queued start/stop request is not completion.
Calling the task or modifying shared flags without those checks would not
establish G2 microphone parity. The existing verified Opus capture remains the
working streaming path.

Reproduce with `.tools/rv32-tests-venv/bin/python
analysis/microphone-lease-20261103/verify-parser.py --report /tmp/microphone-parser.json`
with a new report path. Native exports and raw
firmware stay local; the test pins the original body before execution.
