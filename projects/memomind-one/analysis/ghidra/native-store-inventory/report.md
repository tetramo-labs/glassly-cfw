# Acquired CUS8 directory inventory

Both complete captures contain **65,536 bytes of `0xff`**, byte-for-byte identical:

- `captures/flash-read-runtime-20261031/metadata/plugin-directory.bin`
- `captures/flash-read-runtime-20261031/metadata-repeat/plugin-directory.bin`

SHA256 for each is
`71189f7fb6aed638640078fba3a35fda6c39c8962e74dcc75935aac948da9063`.
Capture manifests identify device1 offsets`0x00500000..0x00510000` and256-byte
sequential reads. The repeat improves consistency evidence but does not create an
atomic snapshot. No KV query, mount, repair, reservation or flash mutation was
performed during this inventory task.

## Exact native classification

The captured state is **erased/unformatted directory**, not a valid initialized
empty cache. All eight8192-byte slots have:

| Field | Observed |
|---|---|
| Magic / version | `0xffffffff` / `0xffffffff` (invalid format) |
| Raw generation words | both`0xffffffff`; not a valid selected generation |
| Stored snapshot CRC32 | `0xffffffff` |
| Computed CRC32 over first`0xff0` bytes | `0x2c17087a` |
| Snapshot commit atslot+`0x1ffc` | `0xffffffff`, not`0x434f4d54` |
| Journal records | All17024-byte slots erased; no committed record |
| Selected snapshot | None |
| Replay performed | None: native mount exits before journal replay |

This result is checked by executing the **actual pinned RV32 native mount code**
`0x042a0e46`, including native snapshot validator`0x042a0754`, native CRC and
memory/string routines, in local Unicorn2.1.4. The captured directory is supplied
through a bounded read callback; no native hardware flash calls execute. The
native body SHA256 is
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
Startup code/data copies and native`gp=0x02011688` are modeled from the existing
startup mapping, with synthetic isolated stack/context memory.

With valid callbacks and a **synthetic all-zero bad-sector bitmap**, the actual
native function returns **-1**, after16read callbacks (snapshot payload and commit
word for each slot). It selects no generation and invokes no mutating callback.
The native path's erased-header predicate is satisfied; the capture additionally
proves all remaining bytes are erased. A valid initialized empty snapshot instead
returns0, demonstrated by a separate fixture.

This is a conditional mount-format proof, not a complete device mount result.
KV`0x6009` and the real bad-sector bitmap were not acquired. A bad-map callback
failure or invalid directory-sector bit can make native mount fail before it
examines the directory. The harness config identity is synthetic and irrelevant
to this early empty-directory branch; it is not a claim about the current app's
length/CRC. Native hardware, SPI readiness, live runtime ownership and the
write-capable initializer/repair wrapper are not emulated.

## Occupancy and last256KiB

There are **no recorded occupied extents, protected entries, incomplete candidates,
or pending moves in either captured directory**. There is no recorded overlap
with the proposed store-relative`[0x002c0000,0x00300000)` last256KiB.
No entry array is parsed from invalid snapshot bytes; the absence follows from
all directory bytes being erased, not from interpreting`0xffffffff` state words
as valid records.

This does **not** establish that the payload sectors are erased, that there are
no live RAM-only users, that the bitmap marks these sectors healthy, or that the
region is reserved. Native initialization can format the store and then allocate
through the entire3MiB. Its recovery reset can erase all good sectors. The stock
CUS8 owner and mechanisms described in`../native-store-capacity/report.md` remain
in force. A reservation-aware platform design is still necessary.

## Replay validation and limits

`inventory.py` is analysis-local tooling. It computes per-slot raw field/CRC/
commit inventory, then uses the pinned native mount as the semantic evaluator.
On successful native mount only, it decodes validated context entries and reports
protected/candidate/overlap state. On failed mount it does not expose stale context
bytes as entries. Native execution is instruction-budgeted; mutation/validation
callbacks are forbidden, and local read callback offsets and destinations are
bounded. No source checkout, runtime script or capture is modified.

Thirteen offline tests passed, including12native execution cases:

- exact acquired erased directory and identical repeat;
- valid initialized empty snapshot;
- complete protected entry overlapping proposed last256KiB;
- incomplete candidate extent;
- successful-use journal replay;
- pending relocation progress requiring recovery (-6), with no move/write;
- corrupted committed snapshot rejection (-8), without silently ignoring it;
- newer valid but uncommitted snapshot requiring recovery (-6);
- committed journal with bad CRC rejection (-8);
- duplicate complete names rejection (-8);
- synthetic bad sector overlapping a complete entry rejection (-8);
- synthetic bad directory sector preflight rejection (-3);
- input length and expected-hash rejection before execution.

These fixtures preserve native semantics by executing machine code rather than
replacing it with a Python interpretation. They do not prove all possible native
inputs or power-loss states, nor do they validate real payload SHA256, the real
bad-sector map, or hardware mutation safety. No journal replay is needed for the
actual all-erased capture. `tests.json` records each native return, callback trace,
instruction count and observed stack use; `test.stderr` records all13test results.

Reproduce from repository root:

```sh
.tools/rv32-tests-venv/bin/python analysis/ghidra/native-store-inventory/inventory.py \
  captures/flash-read-runtime-20261031/metadata/plugin-directory.bin \
  --expected-sha256 71189f7fb6aed638640078fba3a35fda6c39c8962e74dcc75935aac948da9063 \
  --output analysis/ghidra/native-store-inventory/inventory.json
.tools/rv32-tests-venv/bin/python analysis/ghidra/native-store-inventory/test_inventory.py
```

`comparison.json` independently verifies both capture hashes/byte equality and
manifest agreement. `sha256.json` pins this analysis, source code, manifests and
native evidence. The findings support an unformatted-directory observation and
no recorded overlap; they do not authorize a write or claim a reservation.
