# Read-only storage diagnostics

Build explicitly with `--scene-session --input-observer --flash-reader
--external-tail-reader --storage-diagnostics`. This retains the external read
ranges and advertises profile `H001Y-1.0.3.127-storage-diag-v1` on service15,
command0x7b. A request is exactly one BYTES TLV. Existing opcode0 queries the
profile; opcode1 performs the existing bounded physical reads.

Opcode2 is exactly the byte `02`. It samples only the fixed RAM scalar slots
in [the topology review](../../analysis/ghidra/flash-topology/diagnostics.md)
twice and reports normalized values. Driver codes are0=none,1=85family,
2=c8family,3=unknown. `consistent=1` means both scalar samples matched; it does
not prove an atomic snapshot or exclude an ABA change. All booleans are JSON
integers0/1. The device1 legacy ID is exposed only for a valid85-family cached
probe. Neither pointers nor UID-derived bytes are returned. Shared c8 state is
explicitly labeled shared, and does not establish device1 capacity. The query
never initializes a controller or sends a bus command.

Opcode3 is exactly the byte `03`. It calls the initialized native KV getter
once with fixed key0x6009, owned116-byte destination and a separate aligned
length. The copied record must pass the exact physical3MiB identity, CRC32 and
directory-sector bitmap checks before bytes are exposed. `recordState` is:

- `present`: one validated persisted record; `recordHex` is116bytes and
  `mapHex` is its96-byte bitmap. The host independently validates both.
- `absent`: getter status7, no record. `recordHex` is empty and `mapHex` is the
  effective96-byte zero default defined by the native loader. It is not a
  claim that a zero record was acquired.
- `invalid`: getter status0 but length, identity, CRC or bitmap validation
  failed. No record/map bytes are exposed.
- `unavailable`: another getter status, including uninitialized2, corruptKV4
  or invalid-capacity13. No initialization, repair or retry is attempted.

The full physical bitmap remains96bytes even when logical native capacity is
later reduced. The proposed device1 region0x700000..0x800000 uses bytes64..95,
bits512..767. Preserve genuine bad sectors; never synthesize reservation bits.
A valid map is only one reservation prerequisite.

Request memory is released after parsing the fixed opcode. The handler then
allocates one1024-byte owned workspace under the existing32KiB headroom policy,
copies its JSON response synchronously and frees the workspace exactly once.
There are no erase/program/setter/formatter APIs. The getter uses the native KV
mutex and can assert or block on its native timeout; a host deadline cannot
cancel it. The source review's observed stack paths exclude real RTOS frames
and interrupts. See [ABI and executed native tests](../../analysis/ghidra/badmap-acquisition-review/report.md)
and [implementation review](../../tests/rv32/storage_diagnostics_review.md).

`scripts/capture_memomind_storage_diag.py` verifies the exact profile and
candidate app header before acquiring topology→badmap→topology. It fsyncs its
wire journal, refuses existing output directories, and writes a completion
manifest only after success. Unknown/invalid map state stops acquisition.
Even a successful acquisition reports `reservation_established=false`.
