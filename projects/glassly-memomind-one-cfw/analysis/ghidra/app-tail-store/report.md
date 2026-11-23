# App-tail mutable cache: validation, ownership and acquisition proof

Read-only stock-1.0.3.127 analysis. No flash reads/writes, device commands,
manifest changes or runtime additions. Shared Ghidra exports used
`-readOnly -noanalysis`; no functions were created to fill disassembly gaps.

## Decision

A sector-aligned 256 KiB candidate exists at **device 0 offsets
`[0x003ab000,0x003eb000)`**, XIP **`[0x043ab000,0x043eb000)`**.
It is outside the input-observer-001 app's declared body and observed component
CRC coverage, but remains inside the stock app partition's allocation.

**Actual reset-time CRC coverage and ownership are not yet proven sufficiently
for a write.** The acquired OTA does not contain the bootloader/ROM that activates
compressed updates or validates the app before entry. No observed app-side
routine establishes that reset ignores the entire tail. This is an evidence gap,
not a finding that mutable tail storage is incompatible.

Cache survival across OTA is not required: the cache may be invalidated and
reinitialized after an update. Erasure by an updater therefore does not by itself
rule out this design. The required proofs are that runtime writes cannot alter
boot-validated bytes or another owner's state, and that an ordinary reset after
writing remains valid. Those requirements remain open.

## Exact ranges and declared length

Source OTA SHA256 `08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`;
app body SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
Current candidate arithmetic uses offline
`captures/firmware/input-observer-001/verification.json` final bounds, output
SHA256 `bbc777895ef3c56af8ff3b5cbac85c8e7acb429eadfdc194cd407f5255c12f85`;
it is not a flash read or confirmation of current on-device bytes.

| Property | Value |
|---|---|
| Stock metadata partition | index2, type`0x20` |
| App allocation | `[0x001eb000,0x003eb000)`, 2 MiB |
| App header / body start | 32 bytes / `0x001eb020` |
| Stock declared body | 1,773,176 bytes |
| Candidate image declared body | 1,822,432 bytes |
| Candidate image body end | `0x003a7f00`, exclusive |
| Proposed cache | `[0x003ab000,0x003eb000)`, 64 sectors, 262,144 bytes |
| Current body-to-cache gap | 12,544 bytes |
| Maximum future body before cache collision | 1,834,976 bytes |
| Next stock partition | type`0x90`, starts exactly`0x003eb000` |

`candidate.json` records these calculations. Reserving this range in future
constructors would reduce the app growth limit; the existing 2 MiB check alone
would no longer protect the cache. The remaining 12,544-byte gap is code-growth
space, not a guaranteed journal/metadata reserve. A 256 KiB *logical* mutable
store additionally needs erase-block replacement/metadata capacity or an explicitly
weaker persistence contract; 64 sectors cannot be assumed to hold both arbitrary
256 KiB contents and atomic replacement overhead simultaneously.

The captured component header is eight LE32 words: magic`0xa4e49a17`, body length
at+4, load/entry-related word at+12, body CRC32 at+16. `scripts/memomind_ota.py`
verifies that declared length is precisely decompressed component bytes minus32,
and CRC matches exactly those body bytes, for all six components. The type0x20
metadata record independently stores body length at+12 and allocation at+16.
This proves the format's body CRC range; it is **not executable boot validation
proof**. No bytes for the remainder of the allocation appear in that stream.

## Executable evidence: what the app actually checks

`0x0431684e` validates the two bootmap copies at XIP`0x047fc000/0x047fd000`:
count byte+4 must be below205; it CRCs exactly `8 + count*20` bytes and compares
the following word. It chooses a valid copy using the header generation ordering.
This CRC covers bootmap metadata, not the app allocation or app tail.
`0x04316962(out,type)` locates a matching20-byte record from the selected map.

Cross-core loader `0x041fb3d2` checks component magic, reads header entry at+12,
and, where copying is needed, copies **metadata body_length** bytes from
`physical_start+0x04000020` to the record's load address. It does not copy the
whole allocation and does not call CRC in the exported function. This is an
application-controlled secondary-core loader, not proof of how this application's
own reset-time loader behaves. `0x041fb5c8` also uses header+24 for boot handoff.

The app reads its own header in `0x042a43c8` using
`0x04329ad8(0,0x001eb000,stack_buffer,32)`, checks magic and
`1 <= body_length <= 0x1fffe0`, then copies body_length and header CRC into a
native store configuration. This establishes that native app code distinguishes
body length from its2MiB allocation. It does not itself recompute the app CRC.

The initial CRC caller searches are retained (`crc32-callers.txt`,
`crc32-rolling-callers.txt`). They are direct-reference searches in the analyzed
app, not an exhaustive indirect-call/ROM proof. No claim is made that all boot
checks have been enumerated.

## OTA erase/program: stage versus activation

Normal compressed OTA reception uses the type4 staging partition, not the app
partition. `0x04341560` obtains its physical start through bootmap lookup and
adds`0x04000000`; `0x043415b4` obtains its allocation. On this pinned metadata,
staging is `[0x00481000,0x006df000)`, capacity`0x25e000`.

`0x04341602` rounds requested staging bytes up to4096 and erases that range via
`0x04329a14(0,staging_start,rounded_length)`. `0x04341926` checks offset and length
against staging capacity and programs received bytes with`0x04329b1e`.
`0x04341c08` checks inner magic`0xabcd6543`, component table CRC and CRC of the
packed streams. It does not validate the decompressed app body or decide how much
of the app partition to erase.

`0x04341fdc` calls`0x043169ce(1)` to mark pending state in alternating bootmap
sectors, then schedules reset through`0x0434c42c(6,0)`. `0x043169ce` changes header
state/generation and preserves the existing20-byte records under a new metadata
CRC. Actual staged decompression, app partition erase/program and activation
occur beyond this acquired path. **Neither full-allocation nor declared-length
activation erasure is established for normal compressed OTA.**

A separate single-component transfer path is established:
`0x042400b6(type)` gets allocation through`0x04240060`, erases that *whole
allocation*, programs only its incoming stream length in4096-byte chunks, and
checks CRC of the bytes programmed. Its caller is the normal OTA parser
`0x0423a90e` at`0x0423ca68`, using selector`0x0201163d`; the selector is populated
from packet byte+0x15 (an all-zero four-byte selector becomes0xff). No inspected
whitelist in this branch limits it to type0x20, and this is not a recommended
app-update mechanism. This full-allocation erasure illustrates why ephemeral
cache data must not be assumed to survive every update mode. It does not
invalidate the disposable-cache design.

`0x04329a14` explicitly rejects unaligned address/length (`(address|length)&4095`),
uses64KiB block erases where aligned and large enough, otherwise4KiB sectors,
then busy wait, callback and cache invalidation under native serialization.
Candidate cache sectors do not overlap the current body's last sector.

## Stock runtime owners: established and unresolved

The whole candidate belongs to type0x20's allocation. There is no separate
cache partition or reservation in the supplied map. No currently recognized
Ghidra references point into physical`0x003ab000..0x003eafff` or its XIP alias
(`tail-physical-refs.txt`, `tail-xip-refs.txt`, both empty). This bounded negative
search does not cover arithmetic addressing, indirect operations, unrecognized
instructions, other processors or missing boot code. It cannot prove exclusivity.

A concrete suspected owner was traced and excluded: the native store initialized
by`0x042a43c8` uses an app body-length/CRC identity but stores its bytes on
**device1**, not in the app tail. Config`0x04382ff0` read callback`0x042a3e20`
bounds offset/length by`0x300000`, then calls read with device1 and offset
`0x00500000+offset`; write`0x042a40c4` and erase`0x042a411e` use the same range.
Their cache-maintenance alias is`0x05500000+offset`. This corresponds to the
separate unified-map type0xc8 allocation`0x01500000..0x01800000`.
Callback raw disassembly is retained because three callbacks were not defined
Ghidra functions. `0x042a4178` also bounds its verification view to that3MiB range.
This is an owned native store, not free flash for this project.

The app startup code copies declared code/data and clears BSS as established in
`../memory-capacity/report.md`; it does not itself initialize the candidate tail.
Still missing: reset-time boot validators, activation erasers, factory-recovery
paths covering the app allocation, and any other-core indirect owner. No test
has written candidate bytes or rebooted with a modified tail.

## Concrete read-only acquisition ABI for missing evidence

The statically established interface is:

```c
/* Pinned 1.0.3.127 only; normal native ABI/gp veneer required. */
int flash_read(unsigned device, uint32_t physical_offset,
               void *owned_destination, uint32_t byte_count); // 0x04329ad8
```

Zero means success; nonzero is failure. The exact four-register ABI is preserved
in its assembly. It acquires`0x04329912(device)`, calls`0x0432957e`, then releases
`0x0432994a(device)`. That lock uses an RTOS mutex or native critical mode,
according to existing initialization. Use an initialized normal task context;
do not call from interrupt context or while holding incompatible flash locks.

`0x0432957e` splits unaligned starts and subsequent data at256-byte boundaries.
`0x04329460` builds a read descriptor with command03, or initialized-mode EB/BB,
and calls SRAM`0x020081da(device,descriptor,destination,count)`.
The lower read engine issues a read transaction and copies the result from
controller FIFO windows`0x01104000` (device0) or`0x01108000` (device1). No erase,
program or write-enable operation is in this read chain. The similarly located
`0x0432a6e6/0x0432a13c` are **status/protection mutation routines**, not the read
entrypoint; they were inspected and must not be used for acquisition.

The native read wrapper does **not** validate total device capacity, pointer
ownership or address overflow. Hardware busy loops in`0x020081da` do not expose
a software timeout; a host timeout cannot make an in-flight native call cancellable.
Future dump command design should therefore expose only fixed allowlisted reads,
owned256-byte output, one request at a time, offset/count overflow checks,
correlated response and stop on nonzero status/disconnect. No automatic retry or
readiness manipulation through flash init/protection APIs is required or proposed.

| Future fixed acquisition range, device0 | Evidence / purpose |
|---|---|
| `[0x00000000,0x00010000)` | First64KiB is below the first supplied partition; candidate resident boot flash. Its contents and presence of the required bootloader are **not yet verified**. |
| `[0x007fc000,0x007fe000)` | Two bootmap sectors, directly read/CRC-checked by native`0x0431684e`; validated concrete metadata addresses. |
| `[0x001eb000,0x001eb020)` |32-byte current app header; exact existing native read call corroborates ABI/address. |

These ranges all fit the known internal8MiB flash map; enforcing
`offset < 0x00800000 && count <= 0x00800000-offset` is a necessary outer bound,
not sufficient permission for arbitrary reads. Prefer only the table's allowlist.
The device0 flash map and read command path are established, but no claim is made
that every address in the first64KiB is readable on this hardware until a bounded
read succeeds. Boot ROM outside flash would remain missing even after that dump.
Acquire repeated bounded chunks only after each prior response succeeds; record
exact length and SHA256, compare bootmap/header semantics, then import a separate
analysis project without changing the current one. This report adds no command
or implementation and performs no hardware acquisition.

## Conditions for the eventual dynamic store

1. Resolve reset validation by analyzing acquired boot code or equivalent exact
   executable evidence. Show CRC source and length, not merely a matching format.
2. Verify current app header/body length and map on the target build; enforce the
   new upper app bound before reserving64 sectors. Prove no stock runtime owner
   addresses them, including computed routes beyond this static pass.
3. Define ephemeral cache initialization/versioning and reset behavior. A random,
   erased or partially written cache must be treated as invalid cache data;
   boot itself must not depend on successful cache recovery.
4. Implement erase-aware transactional storage and needed spare sectors, then
   preserve the original dynamic cache API semantics through an explicit backend.
   No fixed-buffer or immutable-only substitution is declared full parity.

This investigation supplies the next acquisition ABI and separates OTA
persistence from boot validity. It does not authorize or establish safe cache
writes yet; the outstanding boot-validation evidence is concrete and testable.
