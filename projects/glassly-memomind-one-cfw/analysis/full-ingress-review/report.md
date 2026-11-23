# Full 65535-byte, two-origin ingress design

The reserved 1 MiB region can hold the full 256 KiB transactional logical cache
and three 64 KiB spools, provided **at least 177 of its 256 sectors are usable**.
This does not yet make the existing runtime full-capacity: its transport takes
contiguous RAM, its native display envelope truncates large job lengths, its
scene command parser still takes pointers, and two inflater histories plus the
current metadata undo block exceed the existing headroom policy. A feasible
next implementation uses bounded outer packets, three explicitly owned spool
roles, immutable record readers, source-based persistent zlib, and a metadata
authority design. The stronger candidate adds11 dedicated metadata sectors;
simple flash undo alone does not retain the existing nonfailing rollback contract. It preserves 65535-byte wire/decoded records, both independent
histories, ACK history and the entire logical cache; reducing any of those is
not the proposed solution.

This is a source-backed design, not an implementation or device-capacity proof.
`plan-model.json` pins inspected files and records 561 arithmetic/role checks;
those are **design-model checks**, not additional firmware regression passes.
The G2 source pin is `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`.

## Exact present limits

| Boundary | Actual limit / lifetime |
| --- | --- |
| G2 record | Five-byte clear header, wire body 0..65535, decoded body 0..65535; CRC16 over decoded bytes |
| Portable transport | Two origin slots; currently each owns a contiguous wire allocation and a persistent inflater; one synchronous decode allocates max_record+1 |
| Inflater | RFC1950 windowBits15, 32768-byte window per origin; RV32 total 39944 per origin / 79888 for both |
| G2 outer packet | `packet[3] == length-8`, u8 field: total 11..263, stream data at most252 bytes; demo split229 is not a record cap |
| MemoMind GM ingress | Native body fragments642, complete declared logical length at most81920; one BYTES TLV at most81907 |
| Current graphics admission | 8192 bytes; copied native job adds four bytes |
| Native display envelope | `0425a764` allocates/copies a u32 payload length but writes `(uint16_t)length` at envelope+6; data starts+8 |
| Existing copied raw job | Max safe raw length65531 from the envelope field alone; 65535+4=65539 becomes3, so merely raising the current macro is incorrect |
| Scene source input | Public max65535, but pointer-based prepare/dispatch and retained reassert pointers require the complete input stable through dispatch |
| Scene logical store | 262144 bytes; full replacement/rollback needs64 active+64 staged+1 replacement physical sectors |

`042f0306` admits `(declared_full_length-9)<0x13ff8`; the service15/cmd7d
request does not use the special8192-byte zero-copy plugin path. Its native
parser staging buffer and separately copied TLV briefly coexist. A single
65535-byte BYTES request is structurally admitted by GM but costs roughly two
large native allocations before our handler can reject it. Our lower
try-allocator cannot make those earlier generic OOM-hook allocations safe.

Current command ownership is: native TLV borrowed; custom temporary job copies
it; request released; `0425abe8` synchronously copies the job into an envelope;
custom temporary freed; stock display worker exclusively owns/frees envelope.
There is no owned pointer transfer in that path. Queue priority2 has admission
threshold6, and return0 does not establish acceptance. Preserve this distinction
in any new receipt protocol.

Sources: `runtime/portable/transport.{c,h}`, `TRANSPORT.md`,
`runtime/graphics/graphics.{c,h}`, `native.c`, `scene_session.c`, and
`analysis/ghidra/display-adapter/{report.md,queue/function-0425a764.c,fragment-review/report.md}`.

## Physical partition and slot ownership

The full region remains device1 `[0x700000,0x800000)`: 256 sectors of4096.
Acquire/validate the genuine native96-byte map, use bytes64..95 for this region,
and preserve native record identity and absence provenance. Select48 **good**
physical sectors as three logical16-sector extents. They need not be physically
contiguous: an explicit sector vector maps each spool offset. This avoids
rejecting a sufficient-capacity map merely because its good sectors are scattered.

Give the cache a private32-byte unavailable map:

```
cache_unavailable = real_unavailable OR spool_ownership
```

This is an in-memory allocator exclusion, never a fake native bad-sector record.
No diagnostic/save/setter may publish these ownership bits. The spool checks
real badness and its own selected extents, rather than the cache's exclusion map.
At least177 good sectors are required:48 spool+129 cache. At most79 genuinely
unavailable sectors are tolerable for this plan. An80th means unavailable
capacity, not permission to shrink the cache/message/window. Native2MiB store
reservation, current-state preflight, controller serialization, cache
synchronization and genuine-map changes remain separate binding prerequisites.

Keep the48 ownership sectors fixed during a live cache epoch; changing the
cache's init bitmap without reconciling active/staged maps is forbidden. At
new empty epochs placement may rotate among good sectors. Within the48 sectors,
roles may rotate only when their old readers are released. No fixed claim that
"the last three contiguous64KiB ranges are free" is needed or justified.

Each spool permits65536 physical bytes. Wire records use at most65535; the shared
decode spool accommodates the65536th overflow-observation byte, then rejects
that record. Padding is not logical input and is excluded from CRC. Length,
written-page state, ownership generation, role and sealing status live in RAM.
Spools are ephemeral; neither their metadata nor the cache maps promise reboot
persistence. A reconnect/new epoch must use explicit protocol reset rules, not
recover arbitrary stale bytes as an authenticated/resumable stream.

## Three roles also address RAM undo

The two wire slots retain independent partial origins. Only one completed
record is decoded/handled at a time, as in the existing synchronous transport.
The shared decoded slot is sufficient even when both origins have partial
records; a record is handled before its remaining packet bytes advance to a
subsequent record.

| Phase | Origin completing now | Other origin | Third slot |
| --- | --- | --- | --- |
| Receive | Wire body | Partial wire body | Free |
| Compressed decode | Immutable compressed input | Partial wire body | Decoded output |
| Compressed dispatch, after CRC success | **Recycled metadata undo** | Partial wire body | Immutable validated record |
| Plain dispatch, after CRC success | Immutable validated record | Partial wire body | **Metadata undo** |

For compressed input, release/reassign its wire lease only after successful
complete decode, output sealing/readback/CRC and all input-dependent checks.
Inflater dictionary history is separate RAM and survives this reassignment.
For uncompressed input do not copy the entire record merely to use the third
slot: dispatch reads its sealed wire slot and undo uses the unused decode slot.
Keep the record and undo leases until handler/rollback and reply copying finish.
Never let a nested receive, timer, context teardown or second origin reuse them.

Measured existing RV32 layouts give this arithmetic (not an admission guarantee):

| Item | Bytes |
| --- | ---: |
|600x350 GRAY4 canvas+palette|105064|
|Two full zlib contexts|79888|
|Scene descriptor/cache|43420|
|Current metadata undo base|45468|
|Vector work|10752|
|Flash COW workspace+context|4416|
|Scene+transport contexts|1704|
|Subtotal with RAM undo|290712|
|Subtotal when undo is external|245244|

The historical333956-byte free sample leaves43244 with RAM undo, already less
than the existing48KiB policy before queue/allocator/ingress overhead. Moving
undo leaves88712, or39560 after that48KiB margin, before all omitted overhead.
This is a plausible budget to measure, not permission to reduce headroom. The
new slot maps, page staging, reader cursors, ownership records, native request/
queue allocation, task stack, native font and response allocations still count.
The parent now reports a334076-byte idle sample (120 more), leaving88832 /39680
under the same two subtractions; this does not change the conclusion and is not
an independently reacquired sample in this review. Source inflater code adds
about10839 text+rodata bytes before GC; source/profile
code space must be checked independently.

An external metadata snapshot needs only the43420-byte `cfw_cache` image when
asset-byte rollback uses COW; the existing45468-byte undo object also includes
an unnecessary2048-byte saved-granule bitmap for this branch. Even retaining
the complete45468-byte snapshot conservatively fits12 sectors of the recycled
slot. `cfw_txn_save_asset_bytes`' old filled-range lookup can be bypassed on the
external-COW branch because its eventual `cfw_txn_save_bytes` is already a no-op.
Snapshot/seal/read-verify **before any descriptor mutation or asset transaction**.
On abort restore the original cache, then apply the saved small failure-status/
missing-ID reply fields in RAM; do not try to rewrite bits in the sealed flash
snapshot. Commit drops the snapshot lease.

A metadata restore read failure is a serious new failure boundary: do not
continue with a partly restored cache or claim successful rollback. Poison the
whole scene/session and forbid presentation/ACK until explicit recovery. This
must have fault-injection coverage. External undo is not yet equivalent to the
current infallible RAM metadata copy under arbitrary read failure; that exact
boundary remains implementation work, not a completed full-parity claim.

## Stronger metadata alternative: immutable active snapshot, staged RAM

The three-slot undo reuse is the smallest-space proposal, but **must not be
advertised as preserving the existing nonfailing RAM-undo contract**. A second
read error while restoring the cache can leave its RAM image partial. If this
path is chosen, its documented outcome is unavailable/poisoned session with the
original flash snapshot retained, never silent success or a fabricated empty
cache. No reset should be implicit; loss of the old epoch requires an explicit
recovery decision. The old logical data may still be intact but temporarily
unreadable, which differs from immediate in-RAM rollback.

A stronger design keeps an immutable committed metadata handle and active asset
mapping authoritative, using the one43420-byte RAM cache as a working/mirror
image. Abort then drops the working image and staged asset map **without I/O**;
it does not require a fallible flash read to restore authoritative state. Reads
of that preserved state may still fail, just as preserved flash assets can be
unavailable, but failed reads must not change the active handle or mutate it.
A successful subsequent reload can resume the same epoch; no false RESET reply.

Concretely reserve an additional11 good sectors (45056 bytes) for the committed
43420-byte cache snapshot and integrity/lifetime header. Now the private pool
has59 sectors:48 spool sectors+11 active metadata sectors. The cache still has
its full129-sector minimum: **188 good sectors total, at most68 genuinely
unavailable**. This fits the same1MiB region without reducing either65535 record
or256KiB cache. If storing the old45468-byte undo object instead,12 committed
sectors are needed:189 good sectors, at most67 unavailable. Prefer the explicit
metadata image without the redundant saved-granule bitmap.

During compressed dispatch, candidate metadata can occupy11 sectors of the
consumed wire slot; plain dispatch uses11 of the free decode slot. At commit,
exchange the active11-sector handle with the candidate; the old active11 plus
the five unused sectors reconstruct the freed16-sector spool. The physical
pool ownership bitmap stays fixed, while its role/sector vectors rotate.
The other origin's16-sector partial input and the16-sector immutable record
remain intact. This gives enough space for old and candidate metadata without
claiming that arbitrary flash bytes are native bad sectors.

Transitions need an explicit authority state:

1. In idle/rendering, the RAM mirror may advance animation clocks/positions.
   Before the next mutating transaction, capture the **current** metadata,
   including those timer changes, into a sealed/read-verified active snapshot
   before mutating RAM. Failure here leaves authoritative RAM unchanged and
   rejects admission. A stale last-command snapshot is not sufficient.
2. Only after that snapshot succeeds, mark RAM as the staged working image and
   begin asset COW. Keep a small separate RAM record of snapshot handle, asset
   active map, epoch/generation, and reply failure fields. Never keep authority
   solely in bytes inside the working cache that will be overwritten.
3. Finish all metadata transforms, reader-dependent reasserts/SHOW operations
   and semantic checks in staged RAM; seal/read-verify candidate metadata before
   publishing. Existing `mm_external_commit` currently precedes
   `cfw_txn_commit`, and SHOW subsequently updates active lists, clocks, tags and
   operations: those phases must be restructured. Otherwise asset bytes could
   commit before a late reader/metadata failure. Defer presentation, timer and
   settled side effects until the joint commit point while preserving their
   original order and captured time semantics.
4. Publish the candidate metadata handle and staged asset map together under
   the single owner, without I/O or any failing operation between them. This
   is a live-epoch atomic authority change, not a power-loss journal.
5. On failure before publication, discard staged RAM and maps. Active handles
   remain unchanged. If no reload is possible, return explicit unavailable,
   stop scene advancement/presentation, retain both origin contexts/partial
   records as owned until explicit transport failure/reset rules dispose them,
   and retain the authoritative snapshot. Never run STATE/SHOW against a
   half-loaded mirror. A new input can be queued only under the real backpressure
   contract; it cannot overwrite metadata or manufacture a successful rollback.

This is a larger accessor/lifecycle conversion than changing `memcpy` to a
flash reader. It must cover non-PUT metadata mutations too: HIDE, CONTROL drop/
period/reset, STATE's reap, animation ticks, settled tags and owner deletion.
A full-scope implementation cannot freeze animation metadata forever, serialize
new snapshots every20ms without measuring wear, or drop these mutations from
rollback/state reporting. Snapshot-at-transaction-boundary is the proposed way
to retain timer semantics without obligatory per-tick erase traffic.

Keeping immutable active metadata in RAM and storing only a staged flash delta
is another possibility, but not an immediate memory proof. Worst-case delta
can modify all256 object descriptors, asset descriptors, journal and bitmap;
an unbounded/full-size RAM overlay restores the original45KiB problem. Applying
an external delta destructively to active RAM still requires fallible reads
mid-commit. It needs a persistent reader/overlay authority model or a proven
bounded complete materialization before commit. Do not claim strict rollback
from a "small delta" assumption unsupported by the full original suites.

The recommended full-parity prototype should compare these authority models
under fault injection before choosing a native binding. The59-sector owned-pool
variant is the concrete capacity-feasible stronger candidate. Its unchanged
active metadata/asset handles are testable after every staged I/O failure;
availability after a read failure, animation continuity and task timing remain
separate explicit obligations.

## Ingress and scheduling without a reduced record window

The least disruptive native envelope carries an unchanged validated G2 packet
(up to263 bytes), plus a small version/origin discriminator, in one MemoMind
BYTES TLV. An illustrative three-byte discriminator makes266 bytes,270 including
TLV header,279 GM logical bytes, and270 display-job bytes with the current four-
byte job header. It fits one inbound642-byte fragment and the native u16 queue
length with ample room. This is a proposed new adapter envelope, not a selector
already supported by firmware. Root must choose/advertise a fixed selector
without colliding with existing raw scene requests.

Validate original header/SID/length/CRC/flags and logical origin1/2; pass original
sequence, selected-target flags and record bytes unchanged. The backend may
accept larger MemoMind packet chunks later, but that must not alter the original
record semantics or use a smaller sender record/window as a capacity workaround.
Original G2 packets already supply a suitable bounded unit. Full65535-byte
records span arbitrary packet/header boundaries and sequence wrap normally.

A serialized owner processes each accepted packet and may execute several
records from it. The display task is the current proven owner for scene/render;
putting flash/decode there is simplest for correctness but may block refresh,
leases and stock UI. If a separate ingress task is used, it needs explicit
owned-message/slot leases, an asynchronous completion continuation, and an
ordering gate; the present synchronous `handle` ABI cannot just enqueue a reader
and return success. No flash operation belongs in ISR/observer/critical context.

Native GM fragment ACK confirms parsing only. A new adapter packet receipt must
mean the display/ingress owner actually consumed the packet and safely retained
its state, **not** that a complete G2 record was applied. Keep those receipts
separate from unchanged kind1/3/5 transport replies. Credits/backpressure must
reflect actual bounded queue capacity and permit the original sender's record
pipeline/two-origin interleaving; forcing a one-record window is not a full-port
solution. Do not ACK a dropped queue job. Lost receipts produce ambiguity: stop
or explicit reset/resync; no blind resend that could execute effects twice.

The native stock queue's ambiguous return needs a concrete admission/completion
contract before this is ready. A firmware-owned small ingress queue plus a
reliable/pollable owner wakeup is one candidate, but its synchronization and
session lifetime need native proof. Copy only bounded packets into it; do not
transfer borrowed TLV pointers or host-controlled RAM addresses. Cancellation
must not free a queue/slot while worker/native I/O still owns it. Reject stale
job generations after owner recreation. Transport state cannot live only in an
LVGL owner that is freed while queued ingress still refers to it.

This design does not claim MemoMind has two lens processors. It preserves two
origins for each configured logical endpoint; target-subset behavior stays
unchanged. Advertising two physical endpoints or applying a BOTH command twice
to the same scene would require a separate topology/semantics decision.

## Decoder, integrity and ACK invariants

No native persistent zlib ABI was found. Vendor the already-reviewed local
zlib1.3.1 inflate-only source with its license/hash provenance, `Z_SOLO`,
`NO_GZIP`, static const fixed tables and checked allocators. Retain two full
39944-byte RV32 states. Do not use LZ4/LZMA, raw-DEFLATE, a smaller window,
`inflateResetKeep`, or an evicted history as substitutes.

Refactor decoding to pull bounded input pages and push bounded output pages.
The adapter retains `z_stream` across records, consumes every wire byte,
requires progress, rejects `Z_STREAM_END` and supports the exact `Z_SYNC_FLUSH`
contract. Validate final `00 00 ff ff` before decode just as current core does.
Clear borrowed next_in/next_out on every exit. A chunk boundary must not become
an invented flush/reset boundary: `avail_out==0` for a temporary chunk means
flush/refill that chunk, whereas reaching65536 total decoded bytes rejects the
record. Differential tests against the contiguous adapter must cover boundary
return statuses and dependent histories; do not assume a page-loop rewrite is
automatically equivalent.

Wire CRC16 and decoded CRC16 have distinct purposes. Preserve original record
CRC-16/CCITT-FALSE (`ffff`, polynomial1021) over actual decoded bytes. The outer
packet CRC remains validated independently. Readback/CRC for a sealed spool
protects the flash copy: computing CRC only over bytes before program does not
verify what the scene later reads. Internal CRC32/per-page integrity may detect
spool corruption but never replaces the original wire CRC. A read/program/erase
failure invalidates that attempt, disposes that origin's inflater/context as
required, and cannot produce success. Never synthesize bad bits or retry an
ambiguous write automatically.

Preserve packet RESET versus record RESET_CONTEXT, silent skipped-target
records and ordinal advancement, END truncation, sequence wrap/gaps, reply
capacity up to255, three explicit ACK-history entries, and reply-before-ACK.
A record success is emitted only after its handler transaction/presentation
scheduling semantics complete. A successful handler followed by send failure
stays processed in ACK history. Outer packet receipts must not alter that state
or imply all missing ordinals succeeded. Plain, zero-length, malformed and
multi-record packets remain in scope. Binary BYTES replies can carry the full
255-byte reply plus TLV/header within503 outbound bytes; no need to lower reply
capacity just to fit JSON hex into a single frame.

## Reader conversion: precise source boundaries

Existing `MM_SCENE_EXTERNAL_STORE` already makes retained asset reads offset-
based, but it does **not** make command input offset-based. Reuse the bounded
`mm_scene_bytes`/256-byte cursor idea with a read-only immutable record reader;
do not fake a permanent pointer from `mm_flash_store_view` or XIP mapping.

Required conversions in `scene_cache.inc` include prepare/undo scanning,
`cfw_put_entry_len`, PUT headers/payloads, `cfw_shape_record_len/decode`, SHOW
reference/operation scans, STATE/CONTROL prologues, and transaction reassert
records. `reassert_records[]` currently keeps pointers into the message until
commit: replace with offsets/lengths in its retained reader lease. The input
must remain stable across both validation passes and commit/abort. Keep exact
bounds and metadata rollback; don't process a malformed suffix after already
publishing a prefix. Session dispatch and immediate image/font/geometry paths
also need reader admission, stable source handles and alias/ownership checks.

Small fixed shape/op headers can be copied into bounded locals. Inline text is
at most128 bytes. Original path commands are at most8192: an explicitly budgeted
8192-byte temporary copy preserves that existing limit while using unchanged
`mm_vector_compile`; a reader compiler can remove that temporary later. RLE
images/fonts and large asset chunks must use cursors/readers. Keep existing
object/asset/command counts, winding rules, rotations, transaction chunk limits
and validation predicates; the new source interface does not relax them.

Do not call current COW `write` for every256-byte input chunk: each call rewrites
a full logical4096-byte sector, multiplying erase/program traffic by up to16.
Add `write_from_reader` that performs one COW per logical-sector segment: read
old sector into the existing4096 workspace, fill its changed span through the
spool reader, then erase/program the replacement exactly once. Source callbacks
must not alias the cache workspace or invoke cache APIs recursively. Maintain
active/staged isolation and all existing failure cases. Separate PUT operations
may still revisit a sector; coalescing them must preserve staged reads and
validation semantics, not defer required visibility.

## Concrete next code/API sequence

1. New portable `record_spool.{c,h}`: explicit context, real-map/ownership split,
   three16-sector maps, begin/append/seal/read/release and role generations;
   synchronous page read/program and sector erase callbacks. Init is read-only,
   effects occur only under admitted begin/append; no native addresses/globals.
2. A shared immutable `mm_record_reader { user, length, read_at }` and sink API.
   Reads copy into caller memory, use u32 offsets/count totals, reject overflow,
   and retain no borrowed pointer. Add CRC16 update, sealed byte-count/integrity
   checks, and a streaming zlib reader-to-sink adapter with unchanged end/reset.
3. Add an optional storage backend to the existing transport parser rather than
   duplicating its semantics. Replace wire-buffer ownership and contiguous
   `decode/handle` with storage handles/readers for that backend; retain the RAM
   adapter and run the same original five scenarios and all adversarial tests
   against both. `max_record` remains65535. Slot acquisition failure is a real
   resource failure, not an advertised reduced cap.
4. Reader-based scene dispatch/prepare and explicit metadata authority/snapshot
   callbacks. Choose the stronger active-handle design or explicitly expose the
   smaller flash-undo design's unavailable recovery boundary. Preserve
   existing APIs through RAM-reader wrappers; update reassert offsets and
   sector-coalesced asset writes. Route the complete original scene/vector
   assertions to the reader implementation as well as default RAM behavior.
5. Only then native packet adapter/owner lifecycle/credits and flash bindings,
   with exact native allocation/queue/cache/task proofs and machine tests.
   Keep current8192/64KiB profile unchanged until this different full profile
   passes; do not advertise full capacities from arithmetic alone.

Candidate signatures (design, not existing ABI):

```c
int mm_spool_begin(mm_spool *, unsigned slot, uint32_t capacity, uint32_t *generation);
int mm_spool_append(mm_spool *, unsigned slot, uint32_t generation,
                    const void *, size_t);
int mm_spool_seal(mm_spool *, unsigned slot, uint32_t generation,
                  mm_record_reader *owned_lease);
int mm_record_read(const mm_record_reader *, uint32_t offset, void *, size_t);
int mm_transport_receive_stored(mm_transport *, /* same packet metadata */ ...);
int mm_scene_dispatch_reader(mm_scene_context *, const mm_record_reader *,
                             int present, mm_scene_dirty *);
int mm_flash_store_write_reader(mm_flash_store *, uint32_t destination,
                                const mm_record_reader *, uint32_t source, size_t);
```

Role release/reassignment, backend error mapping and metadata snapshot methods
must be defined alongside these interfaces; ellipsis above is explanatory, not
an invitation to expose a variadic production entry point.

## Performance, wear and completion gates

A max compressed wire and decoded record can require32 sector erases and512
page programs before scene work; a metadata snapshot adds up to12 erases/178
page programs if storing45468 bytes. A full logical cache replacement is another
64 erases/1024 programs plus old-sector reads. Use actual page-rounded length,
not always erase/program every spool byte for tiny messages. Small partial
pages can remain in owned staging RAM until sealed, but no reader/receipt may
claim stronger persistence than that RAM lifetime. No cross-record dictionary
bytes belong in flash pages being erased.

Repeated spooling creates real wear. Fixed48-sector ownership is a bounded
allocation policy, not wear leveling. No erase endurance, erase latency,
throughput, sustainable video FPS or watchdog/lease margin has been established.
Measure bounded native operation and whole-record latency before choosing
credits/timeouts; the existing1-second display lease and20ms tick may expire or
stall during a large flash-backed transaction. Preserve lease semantics with an
explicit owner/busy/lifecycle design rather than silently increasing windows or
sending fake keepalive effects. On reset, OTA, recovery or stock ownership
restoration this cache/spool epoch may be lost; it must reinitialize cleanly.

Required regression includes every packet split and sequence wrap for65535,
both interleaved partial origins and dependent histories, skipped-target reset,
65536 decoded overflow, multi-record packet completion, full255-byte replies,
ACK/history on send failure, reused/stale leases, all page/sector boundaries,
177-good-sector success versus176 failure, scattered bad sectors, genuine-map
immutability, decode/CRC/parser rejection before commit, rollback with reassert
references, and read/program/erase fault injection at every admitted operation.
Native tests must cover queue drop/stale generation/owner deletion, no borrowed
TLV use after release, no fake badmap writes and envelope u16 bounds. Actual
hardware headroom, wait/erase/cache safety and live full-capacity effects remain
unproved until those later stages run.
