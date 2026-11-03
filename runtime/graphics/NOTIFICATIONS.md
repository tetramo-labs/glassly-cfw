# Native ANCS candidate

`--notification-relay --cfw-revision 2` adds a poll-driven native adapter to the
minimal-owner profile. It is an offline candidate, not installed firmware.
Mobile integration and real notification/action acceptance remain pending.

GM service 15, command `0x78`, accepts one BYTES TLV:

| Bytes | Operation |
| --- | --- |
| `41 4e 01 00` | Drain up to two queued records |
| `41 4e 01 01` | Enable/renew a 90-second lease and return status |
| `41 4e 01 02` | Disable, invalidate UID associations and cancel pending action |
| `41 4e 01 03` | Query status and drain records |
| `41 4e 01 04 UID_LE32 ACTION` | Request positive (0) or negative (1) action |
| `41 4e 01 05` | Renew a live lease |

Replies are JSON with `glassly:"notifications"`, `abi:1`, `result`, and `records`.
Each record is a hex-encoded original `AN` v1 payload, without the G2 field-125
protobuf envelope. Other fields report observed connection state, source
generation, session, rejected events, queue drops, active lease, action serial and result.
The session counter changes on peer/reset boundaries and queued records are
discarded; hosts must reset partial reassembly when it changes. Action availability
uses ANCS flag bit 3 for positive actions and bit 4 for negative actions.
Action results: 0 none, 1 pending app dispatch, 2 native transaction accepted,
3 busy, 4 stale/unknown/unavailable action, 5 native enqueue/request rejected.
Result 2 does not establish that the phone performed an action. A failed initial
app enqueue is visible on the following poll, not the already-built reply.

The pre-stock call at `04217568` copies source/attribute/app-name data before
stock cleanup. The wrapper restores original arguments, stack and return address,
then forwards to `04319792`. It does not register another app-bus subscriber.
Ordinary source callbacks allocate nothing and send nothing. Body spans are
checked against app SRAM and limited to 4096 bytes; each attribute is limited to
1024 bytes. Complete attribute records are validated before queue mutation.

State is allocated once per boot on explicit ENABLE, with 96 KiB heap headroom.
The reserved registry occupies bytes 128–139 of the existing 256-byte carve;
canary and flash-broker slots remain separate. The original 4096-byte relay ring,
1024-byte app-name scratch and 32 UID associations stay owned until reboot.
No pointer to a display owner or borrowed event survives the observer. Core
access is serialized by the native short critical pair. Allocation, JSON
construction, app posting and native action RPC run outside that critical section.
The adapter's allocator callback only returns preallocated ring/scratch storage.

Timers are logical: host polls perform the original bounded two-record drain.
Lease checks stop ingestion without polling; mode 11 and launcher teardown
explicitly disable the relay. Queue drops retain the original counter semantics.
This is not G2's unsolicited transport or exact timer pacing.

Actions are marshalled through private app event `0x280` and revalidated there.
A source-generation change, removal, disconnect, lease expiry or cleanup rejects
stale requests. The stock peer busy byte prevents overlap with its attribute
transactions; busy requests are rejected rather than added to a second queue.
The native action wrapper is synchronous and may assert on its existing RPC/OOM
paths. Its later completion event contains no UID; no remote-completion claim is
made. Android notification IDs are never accepted as ANCS identities.

The same candidate suppresses the stock vendor-app launch function at `0421d17c`
with an eight-byte return-zero stub. Static tracing connects its MemoMind app-ID
argument to `0433da30`; physical suppression remains unverified.

## Verification

- Original nine notification scenarios, all 76 CHECK sites / 266 evaluations.
- Production native adapter under ASan/UBSan with explicit native boundaries.
- Compiled RV32 service dispatch for all 256 commands and both request shapes.
- Actual pre-stock call wrapper with both native stack alignments and deliberately
  clobbered caller registers.
- Reconstructed OTA, unchanged unrelated components, exact metadata length update,
  hook destination, launch stub execution and revision mismatch rejection.

Pending: actual native callback/concurrency and complete task-stack validation,
mobile polling/reassembly/configuration, native notification/action tests and
post-flash boot verification. Display position/depth/settings are a separate
unfinished slice. Increment `--cfw-revision` for every flash.
