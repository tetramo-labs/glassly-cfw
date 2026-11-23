# External CUS8 reservation: exact native patch review

Read-only analysis and in-memory emulation only. No native source, firmware image,
manifest, runtime, device, KV record or flash byte was changed. The baseline is
stock1.0.3.127 app body SHA256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
`candidate-recipes.json` pins exact before/after instruction bytes for both
profiles. They are analysis recipes, not an installable image.

## Recommended profile

Reserve **1MiB**, device1`[0x00700000,0x00800000)`, unified physical
`[0x01700000,0x01800000)`, XIP`[0x05700000,0x05800000)`.
Leave native CUS8 capacity **2MiB** at device1`[0x00500000,0x00700000)`:
64KiB directory plus`0x1f0000` (2,031,616) bytes of package payload capacity.

The512KiB alternative is device1`[0x00780000,0x00800000)`, leaving native capacity
`0x280000` including directory. Both profiles use the same eleven instruction
sites; only the replacement capacity immediate differs. The1MiB profile gives
actual room for a256KiB logical scene store, rollback generations, metadata and
spare sectors. Two256KiB data banks plus two4KiB metadata sectors consume520KiB,
leaving504KiB in the1MiB region. This is a capacity illustration, not a completed
transactional backend. A512KiB raw reservation cannot hold two full256KiB banks
and any metadata/spares, so it is the less flexible choice.

External storage also avoids imposing the app-tail bound that leaves only10,912
bytes for further runtime code. These capacity patches consume **zero added code
bytes**:44existing instruction bytes are replaced in place. The app component
must still be reconstructed with its new CRC and verified by the strict builder.
No app partition shrink is required for this external reservation.

## Concrete minimal patch set for the identified managed-cache paths

Let`C=0x200000` for the recommended1MiB reservation, or`C=0x280000` for512KiB.
For each LUI below, retain the destination register and replace upper immediate
`0x300` by`0x200` or`0x280`. All are four-byte instructions; there are no displaced
following instructions or new branches except the explicit badmap change.

| Address | Original bytes (LE) | Effect |
|---|---|---|
|`0x042a44d8`|`37063000`|Primary native mount capacity argument|
|`0x042a4516`|`37063000`|Repair remount capacity argument|
|`0x042a452a`|`37063000`|Format/initialize capacity argument|
|`0x042a4572`|`37073000`|Advisory unformatted-context capacity field|
|`0x042a3e20`|`b7073000`|Native store read callback range bound|
|`0x042a40c4`|`b7073000`|Native store program callback range bound|
|`0x042a411e`|`b7073000`|Native store erase callback range bound|
|`0x042a41ae`|`b7073000`|Package verification XIP offset/length bound|
|`0x0423e9be`|`b7073000`|Whole-store reset loop termination|
|`0x0423ea4a`|`b7063000`|Whole-store reset block-size remaining-range bound|
|`0x042a0998`|`63ee2701`→`6f00c001`|`BLTU a5,s2,+28`→`JAL zero,+28`: decouple full physical badmap validity from reduced logical capacity|

For1MiB, examples of new LUI bytes are`37062000`,`37072000`,`b7072000`,
`b7062000`; the JSON contains every exact replacement for both profiles.
The last branch change is necessary: native`0x042a0972` otherwise rejects genuine
bad-sector bits beyond the reduced logical capacity, even though those sectors
still exist physically. The preceding branch at`0x042a0994` continues to reject
bad bits in directory sectors0..15. The loop at`0x042a09b6` still checks the
full physical768-sector/96-byte map. For sectors16..767 the replacement skips
this format-level rejection; actual allocation and entry checks still consult
bad bits through`0x042a05cc/0x042a13d8` inside their reduced capacity bounds.

No fake bad bits are set, cleared or persisted. KV`0x6009`'s base`0x01500000`,
size`0x300000`,96-byte map and integrity format stay unchanged. The physical
map describes all3MiB, while the native package allocator owns only its prefix.

## Why these changes cover allocation, compaction and reset

The native core already takes a capacity parameter. `0x042a0754` requires the
stored directory capacity to equal that parameter, validates each aligned extent
and move against it, and rejects overlap. `0x042a1b74` allocates and compacts using
context+`0x40` capacity. Its relocation search`0x042a13d8` takes that upper bound;
`0x042a0d36` executes previously validated moves. Hence no separate relocation
instruction patch is required for a correctly mounted reduced-capacity directory.
The existing checkpoint/journal and protected-entry rules remain unchanged.

Native store callback bounds prevent valid caller offsets/lengths from extending
past`C`; the package verifier's direct XIP view is bounded separately. Cached
verification state is RAM and is cleared on initialization/reboot; adoption must
not reuse a preexisting in-memory3MiB context. Install with no active plugin and
start the patched runtime fresh.

Normal cache reset`0x0423e8b4` bypasses those callbacks and erases raw device1
sectors. **Both** its loop end and64KiB batching remainder must be patched.
The region boundary is64KiB-aligned in both profiles. Reset still records its
own wipe intent/completion in KV`0x6008`, skips genuine bad sectors and verifies
erasure, but stops at`0x500000+C`. The reserved tail is never visited by that
patched reset path.

This is the minimal known set for the traced native managed-cache mount,
allocation, read/program/erase, validation, compaction and reset paths. It is not
a global flash firewall: arbitrary factory/service raw-flash APIs, missing ROM,
other processors and future firmware are outside that claim. Existing flash
program/erase execution and mutual-exclusion constraints still apply to the new
backend; an address reservation is not itself a safe flash driver.

## Adoption must not trigger destructive migration

The two acquired64KiB directories were byte-identical and entirely erased,
SHA256`71189f7fb6aed638640078fba3a35fda6c39c8962e74dcc75935aac948da9063`.
Actual native mount emulation classified them unformatted (-1), not initialized
empty. This makes initial reduced-capacity formatting possible **while the same
precondition remains true**. The pending raw-tail backup is useful evidence and
recovery material but does not establish ownership by itself.

Do not apply this recipe to a populated3MiB directory and let native auto-repair
handle it: the exact capacity mismatch returns-8 and can enter whole-store reset,
losing plugins. Preflight must require the still-unformatted directory, or a
separately implemented non-destructive migration with all entries/protection/moves
preserved. No such migration is provided here. Existing running contexts must be
absent; the captured erased directory does not alone prove that RAM condition.

The reduced cache retains the same version4 directory,28slots, protected-entry
policy, LRU accounting and candidate replacement semantics; usable capacity is
smaller. Packages and simultaneous old/new versions must fit the remaining space.
Insufficient capacity should follow the native failure path, not evict protected
entries or consume the new CFW region.

## Genuine badmap read ABI and mandatory tail health evidence

The pinned read interface is:

```c
int load_physical_badmap(void *unused_context, uint8_t *owned96, uint32_t bytes);
// address0x042a9d0a; call(0,owned96,96); 0success, -1failure
```

It calls`0x04235032(0x6009,owned_record,0x74,&actual_length)`, verifies116-byte
record magic`0x474d4231`, version1, base`0x01500000`, physical size`0x300000`,
integrity check and bitmap constraints, then copies96bytes. The required1MiB tail
is **bytes64..95**, sectors512..767. The512KiB tail would be bytes80..95.
Do not infer that slice is zero from erased directory or payload bytes.

Important distinction: native KV status7 means no record and this loader returns
an all-zero map as the native default. To require an actually acquired record,
retain the underlying getter's status/actual length and report absent separately.
Direct getter ABI established at this call site is
`int get(uint32_t key,void *owned_out,uint32_t capacity,int *actual_length)` at
`0x04235032`. Status0 plus length116 is the record-present path; status7 is absent.
The record's CRC/constraints must still be verified by the native reader or an
exact parser. This analysis performs neither call on hardware.

Keep the full physical map, including genuine tail failures, in plugin contexts.
Native saver`0x042a9dd4` writes the entire96-byte bitmap in KV`0x6009`; it must not
be repurposed to mark healthy reservation sectors bad. If the CFW backend will
also mark real bad sectors, prevent stale whole-map saves from losing another
writer's bits: use shared serialization and reload/monotonic-merge semantics or
another explicitly reviewed ownership contract. That concurrency adaptation is
not part of the44-byte capacity recipe and is required before simultaneous
independent badmap updates. Initial read-only tail health checks need no saver.

## Bounded scan of other capacity-like sites

Raw instruction scan found19`LUI *,0x300` occurrences. Four groups are not
reservation boundaries and must not be blindly changed:

- `0x042a9d9e` is the genuine physical badmap's3MiB identity. Preserve it.
- `0x0423ec38/0x0423ee80` construct/check`0x300001`, the FPND record format version,
  not a capacity.
- `0x0432fdb6/0x0432ff10` manipulate peripheral register bit masks, not flash extents.
- `0x04380626` lies in raw non-function data; raw disassembly alone is not a code
  ownership proof.

Three sites`0x042392ba/0x04239c24/0x04239ed4` belong to a3MiB **logical OTA
sector-map** over8192physical4KiB indices. They use`0x020135f4/0x020132f4` and
backend`0x0434603c/0x0434609a`, not CUS8's XIP callbacks. Registration
`0x04345f4c -> 0x043470c8` installs table`0x02010c6c` with read`0x04346784`,
write`0x04346c82` and initializer`0x04346966`. Native source strings identify
`gm_flash_py25q256lc.c`; initializer configures general SPI0 via`0x04320432` and
`0x043206f0`, enters4-byte addressing, and read/program use commands13/12 through
`0x04346714 -> 0x04320d9a`. CUS8 instead uses the separate XIP flash-controller
path`0x04329xxx -> 0x02008xxx` with24-bit device-relative addressing.

These witnesses establish distinct software/controller routes and explain why
those OTA constants are left intact. They do not substitute for a board schematic
or a full physical bus/pin ownership proof. The review does not claim arbitrary
factory accesses or every uninspected path can never target the physical chip.
If hardware-level absolute isolation is required before any write, resolve that
remaining board/controller mapping rather than shrinking unrelated OTA staging.

## Actual RV32 boundary experiments

`review.py` applies the exact proposed instructions **only to an in-memory copy**
of the pinned native body. It writes no firmware binary. Forty-six tests pass
across512KiB and1MiB profiles (`boundary-tests.json`):

- unformatted mount; reduced-capacity initialized directory; rejection of old
  3MiB directory; last allowed package page; first reserved-page rejection;
- native-before rejection versus patched acceptance of a real bad bit in the
  reserved region, while bad directory and active occupied bad sectors still fail;
- actual read/program/erase callback execution at the end, into the tail, crossing
  the boundary and at`0xffffffff`; only allowed calls reach mocked raw flash APIs;
- actual full reset function with all-good map and with an active bad page;
  recorded erase ranges cover exactly the reduced prefix, skip the bad page,
  stop at the new boundary and never access reserved bytes.

The full reset runs native loop/control code; SPI reads, erases, locks, readiness
and KV writes are explicit local stubs. Native code verifies fake erased bytes;
this is control/bounds evidence, not hardware timing, flash safety, callback
concurrency or recovery validation. The earlier native-directory harness supplies
actual mount execution with explicit synthetic map input. No real badmap is
inferred by these tests. `review.py` has a finite instruction budget; boundary-hook
counts in test output are callback events, not whole-function instruction counts.

Reproduce:

```sh
.tools/rv32-tests-venv/bin/python analysis/ghidra/external-reservation-review/review.py
```

## Stock OTA and recovery policy

A stock update restoring original capacity/erase instructions makes the full3MiB
CUS8 region available to stock again; cache recovery may reset it. The CFW region
must therefore be treated as invalid/disposable across unpatched firmware, not
promised persistent through OTA or factory recovery. Reinstalling CFW later must
repeat directory/occupancy preflight: stock may have placed packages in the tail.
Never trust stale CFW superblocks after a stock ownership interval without a
new version/ownership check. Reservation-aware CFW upgrades can preserve their
own store only under an explicit compatible layout contract.

The recipe is concrete and feasible for the identified native cache path on the
observed unformatted state. Remaining gates are current-state preflight and tail
health/backup, flash-driver execution/ownership review, explicit new mutable
backend/rollback semantics, and any required physical-controller isolation proof.
It is not a completed dynamic cache implementation or permission to write yet.
