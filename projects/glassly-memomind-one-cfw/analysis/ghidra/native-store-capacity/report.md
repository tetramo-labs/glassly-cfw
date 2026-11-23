# Native CUS8 store: dynamic-capacity and reservation boundaries

Read-only native analysis; no device access, cache allocation, reservation, KV
changes, erase/program operations or runtime modifications. Ghidra exports used
`-readOnly -noanalysis`. Source firmware/SDK pins are those in
`../app-tail-store/report.md` and `../memory-capacity/report.md`.

## Finding

The external3MiB CUS8 partition is a **managed plugin package cache**, with a
working allocator, directory journal, eviction and relocation machinery. It is
not unused flash and does not expose a proven general-purpose mutable allocation
API. A CFW-owned256KiB region here could avoid modifying the internal app body or
its boot CRC, but **no safe reservation is currently established**.

A legitimate separate region is architecturally possible only after proving a
free/migratable extent and enforcing explicit exclusion across all native owners,
including the whole-store recovery erase path. Neither a fake plugin package,
a protected flag, a fake bad-sector entry, a changed capacity argument nor a raw
write into a currently empty hole supplies that contract. Current entry names,
occupancy and pending relocation are unknown because the directory was not read
from the device in this task.

## Mapping, owner and callbacks

Stock bootmap type`0xc8` owns unified physical`[0x01500000,0x01800000)`.
The actual SPI calls use **device1 offsets`[0x00500000,0x00800000)`** and XIP
alias`[0x05500000,0x05800000)`. Do not pass unified physical addresses to the
low24-bit device1 read/program APIs.

Config table`0x04382ff0` has ten32-bit words. `0x042a43c8` copies it into a
context and installs the current app-header body length/CRC in its final two
words. The table and raw callback disassembly are preserved in the sibling
app-tail report (`native-store-config.json`, `native-store-callbacks.asm`).

| Config offset | Entry | Contract |
|---|---|---|
|0x00|zero|Callback context argument|
|0x04|`0x042a3e20`|Read relative offset/length, bounded by3MiB; calls`04329ad8(1,0x500000+offset,dst,len)`|
|0x08|`0x042a40c4`|Program same bounded relative range via`04329b1e`; invalidates XIP cache and verification cache|
|0x0c|`0x042a411e`|Erase same bounded relative range via`04329a14`; invalidates XIP cache and verification cache|
|0x10|`0x042a4178`|Validate candidate package identity/content before reuse or completion|
|0x14|`0x042a9d0a`|Load96-byte bad-sector map from KV`0x6009`|
|0x18|`0x042a9dd4`|Persist bad-sector map to KV`0x6009`|
|0x1c|zero|Unestablished/reserved here|
|0x20 /0x24|runtime app length / CRC|Current-firmware identity copied from app header|

Read/program/erase callbacks have real native addresses but are internal store
operations, not a public allocator/ownership API. Their raw callbacks only bound
to the3MiB store; they do not enforce a future CFW subrange reservation.
The exact read ABI/lock/poll constraints are in`../app-tail-store/report.md`.

The public SDK at commit`171098bff25934a534a49f95b88df58fbed404c7` independently
documents CUS8 as3MiB with28 entries and64KiB directory, eligible LRU eviction,
protected factory entries, durable resume and package identity. It expressly
states that plugins must not use it as user-data storage or directly access its
addresses (`GlassSDK/docs/PROTOCOL.md`, “Flash cache and execution”). This report
investigates a future explicit CFW platform reservation, not an unsupported
plugin-side borrowing of cache bytes.

## Directory and namespace, with exact native validation

The store context allocated by`0x042a43c8` is`0x1210` bytes. Core state ends at
`0x11a0`, followed by a108-byte package descriptor used by the wrapper. It is a
singleton at`0x02011e48`; teardown`0x042a439e` releases associated state, clears
verification cache and frees it. This is not a reentrant generic file handle.

Directory storage is store-relative`[0,0x10000)`. Payload starts at`0x10000`.
There are eight journal/snapshot slots,8192 bytes each. Snapshot payload is4088
bytes; version/magic/generation and28 entries are included. Full-snapshot CRC32
at relative`0xff0` covers the preceding`0xff0` bytes, using reflected polynomial
`0xedb88320` (`0x042a0544`). Snapshot commit marker`0x434f4d54` is written at
slot+`0x1ffc`. A following journal uses24-byte records beginning atslot+`0xff8`.

`0x042a0754(snapshot,capacity)` requires:

- magic`0x47534331`, version4, **stored capacity exactly equal to supplied capacity**;
- nonzero64-bit generation and an aligned next-allocation cursor in range;
- valid CRC,28 bounded records, valid names/lengths/ABI and states0/1/2;
- page-aligned extents wholly above64KiB and inside capacity, no overlap;
- complete records have completed length equal to declared length; no duplicate
  complete names; at most one incomplete record;
- bounded pending relocation state, destination below source, no overlap with
  other allocated extents.

Each entry is144 bytes, at context+`0x58+i*0x90` (snapshot+`0x30+i*0x90`):

| Entry offset | Meaning established in native consumers |
|---|---|
|0x00..0x3f|NUL-terminated name, max63 bytes|
|0x40..0x5f|32-byte content SHA256 identity|
|0x60|Version identity|
|0x64|Declared package byte length|
|0x68|ABI identity|
|0x6c|Store-relative payload offset|
|0x70|Completed byte length|
|0x74|Flags: bit0 protected, bit1 used in reclamation/use policy; other bits invalid|
|0x78|State:0 empty,1 candidate,2 complete|
|0x80 /0x84|64-bit successful-use ordering|
|0x88 /0x8c|App length/CRC identity under which validated|

`0x042a188a` searches complete entries by name;`0x042a18f0` then compares name,
version, length, ABI and SHA256. Names alone are not a safe ownership key.
`0x042a4178` checks parsed package length/ABI, other runtime compatibility and
content SHA256 before acceptance. `0x042a2322` requires all expected bytes,
allowed extents, matching current app identity and validation callback success
before converting candidate to complete. It preserves an old complete version
until validation succeeds, then replaces same-name entries. Arbitrary mutable
data does not satisfy this package protocol. Rewriting a cached package in place
would invalidate the checked content identity.

App-body CRC is used here as a **cache validation identity**; external cache
bytes do not feed that app-header value in these paths. That is distinct from
proving the missing bootloader's entire policy. The native store is already
routinely mutable without changing app image bytes, unlike the app-tail proposal.

## Mount, recovery and lifecycle

`0x042a17f2` tailcalls common mount`0x042a0e46` with recovery mode1;
`0x042a1802` supplies mode0. Assembly pins the fourth argument (decompiler wrapper
prototypes omit it). Mount loads the bad-sector map, reads all eight snapshots,
validates generation/CRC/commit state, replays journal records, validates extents
against excluded sectors and checks pending relocation. Mode0 refuses dirty or
pending-move state (`-6`); it must not be confused with the wrapper's write-capable
initialization. Mount's repair mode can commit repaired metadata and resume moves.
A directory inventory parser must preserve these rules; selecting merely the
last apparently committed header can hide a newer damaged or in-progress state.

`0x042a0b86` rotates to the next slot, increments64-bit generation, erases both
4KiB halves, writes snapshot, then commit marker. `0x042a0c66` appends CRC-protected
24-byte progress/use records, committing their final word last; when full it
rotates the snapshot. These are actual recovery mechanisms, not evidence that
arbitrary new mutable-store transactions are already implemented.

Top-level installer`0x042a4598` is called by worker`0x042a90ba`; it checks
runtime busy flag through`0x0429bd4c`, initializes store, copies the package
descriptor and begins a candidate. The advisory capacity wrapper`0x042a4628`
uses the same package-oriented core. Current active state bit is
`(*(uint8_t *)(*(uint32_t *)0x02011e28+0xa5))&1` when context is nonzero.
Do not infer a new thread-safe callable reservation service from these wrappers.

The critical reset route is **`0x0423eb52 -> 0x0423e8b4(1)`**. It checks runtime
busy state and a native reentry flag, writes wipe intent to KV`0x6008`, loads the
bad-sector bitmap, then erases and verifies **every good sector in all3MiB**.
It batches64KiB only when all16 sectors are good. It then writes completion state
to KV`0x6008`. This route is reachable from store initialization repair in
`0x042a43c8`, including a corrupt-store result. It is not restricted to the64KiB
directory. A CFW reservation excluded only from normal allocation would still
be erased here. Cache loss across firmware updates can be acceptable, but silent
collision during native plugin operations cannot be.

## Allocation, eviction and relocation

`0x042a13d8` finds a page-aligned extent inside given bounds, skipping occupied
record extents and every set bit in the96-byte bitmap at context+`0x1120`.
`0x042a05cc` rejects ranges containing set bits. Allocation searches can use the
full`[0x10000,0x300000)` region; stock has no permanent tail carve-out.
`0x042a1546` computes eligible reclamation using candidate/protection/same-name
rules and64-bit successful-use ordering. `0x042a1b74` may commit evictions and
compact entries to produce contiguous space. `0x042a0d36` moves one4KiB page at a
time through a256-byte buffer, journaling progress, then commits the new offset.
Therefore an unregistered hole can be filled or become a relocation destination.

`0x042a20aa` accepts only the current candidate's sequential expected offset,
nonzero bounded chunks and no chunk crossing a4KiB boundary. It erases pages or
aligned64KiB extents as needed, writes and reads back. Verified failures can mark
a sector bad and persist the bitmap. There is no discovered API here for an
independent random-write allocation whose lifetime is unrelated to a package.
The existing G2 cache adapter would need such a separate backend; package install
semantics cannot silently substitute for dynamic state semantics.

## Exclusion bitmap: useful mechanism, different ownership contract

Load`0x042a9d0a` reads KV`0x6009`, expecting116 bytes with magic`0x474d4231`,
version1, unified base`0x01500000`, size`0x300000`,96 bytes of bitmap and integrity
check. Missing key (status7) means an all-clear map. Save`0x042a9dd4` persists that
record with the native KV setter. `0x042a0972` rejects set bits in the first16
(directory) sectors or beyond capacity. Both allocator and full-store erase
honor the map.

This is evidence of **bad-sector management**, not an authorized reservation
namespace. Writing synthetic bad bits would misrepresent healthy flash and affect
stock repair behavior. Simply shrinking capacity to`0x2c0000` fails the exact
stored-capacity check and can provoke reset. Marking an occupied region excluded
can invalidate mount and provoke destructive repair. Neither is a safe shortcut.

A future platform implementation could keep an explicit CFW exclusion map
separate from genuine bad-sector state, combine them for all allocation and
reset decisions, and add hard read/program/erase bounds. That is a proposal,
not a proven native hook: all direct bypass routes, callback lifetime, persisted
bad-map writes and reset-entry coverage still require integration proof. Synthetic
bits must not be accidentally persisted as hardware failures, nor must genuine
bad sectors be cleared when reservation bits are removed.

## Concrete next proof and capacity plan

A simple *candidate*, not a reservation, is the last256KiB:
store-relative`[0x2c0000,0x300000)`, device1`[0x007c0000,0x00800000)`,
unified`[0x017c0000,0x01800000)`, XIP`[0x057c0000,0x05800000)`.
It occupies bitmap sectors704..767. Native package payload capacity would fall
from`0x2f0000` to`0x2b0000` after64KiB directory and256KiB reservation. This says
nothing about actual free space, fragmentation, existing entries or bad sectors.
A256KiB logical dynamic store also needs explicit metadata/journal/replacement
headroom; reserving exactly64 physical sectors does not prove atomic full-capacity
updates are possible.

Before selecting an extent, acquire **read-only** the64KiB directory via
`flash_read(1,0x500000+offset,owned_buffer,length)` with the same256-byte bound and
native-task constraints established earlier. The callbacks, eight-slot snapshot
reads and existing native read at`(1,0x500000,...,64)` establish this physical
range. Inventory must include all occupied/candidate extents, pending moves,
protected flags, sequence/journal integrity and bad sectors. No helper that
mounts with repair enabled or calls the cache initializer is appropriate for
read-only inventory. Current plugins' identities must be preserved; do not
invent a plugin entry to hold the reservation.

Then prove an explicit reservation-aware allocator/compactor and full-reset
path against the acquired directory, or design a reviewed migration that retains
all existing entries and their integrity. Any overlapping running/protected
entry is a hard conflict until its legitimate lifecycle/migration is resolved.
Independent mutable-store transactions and power-loss tests remain necessary.

This external region is a plausible capacity path with a clearer app-CRC
separation than the app tail. It is **not yet available CFW storage**. The native
owners and reset behavior are now concrete, so the next work is nondestructive
inventory and explicit coexistence—not raw flash carving by arithmetic.
