# Fixed two-hook graphics container construction

`scripts/build_memomind_graphics.py` is a separate offline profile. The installed
single-hook probe builder and flasher remain unchanged. It accepts only the
visually confirmed text OTA with SHA-256
`941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876`.
It appends the supplied blob at `0x0439bea0` with the established eight-byte zero
padding, then applies exactly these two guarded hooks:

| Name | Address / body offset | Original eight bytes | Replacement |
|---|---|---|---|
| Service-15 callback initializer | `0x042e82e0` / `0xfd2c0` | `b7472e0493870768` | LUI/ADDI a5 targeting `0x0439bea0` |
| Display-worker dispatch call | `0x0425c00a` / `0x70fea` | `032504f9eff0cfb7` | AUIPC ra / JALR ra,ra targeting `0x0439bee0` |

The initializer's following `c.sw` (`bcd8`) must match and remains untouched.
The display continuation's load (`032504f9`) at `0x0425c012` must match and also
remains untouched. The new eight-byte call writes that continuation to `ra`.
Both replacement instruction pairs are generated from the fixed addresses;
signed low-immediate rounding is tested independently, including negative and
positive displacements and halfword-aligned callsites.

The display gate must begin with the displaced `lw a0,-0x70(s0)`, bytes
`032504f9`, before any prologue alters the worker's frame pointer. Construction
checks those bytes at blob offset `0x40`. This is one necessary ABI witness,
not verification of the rest of the gate. Ordinary dispatch must tail-jump to
`0x0425b38a` with the original stack and return address; custom execution returns
to the same continuation. The envelope is borrowed: the worker frees it, so the
gate must not free or retain it. These contracts come from
[display-adapter/report.md](ghidra/display-adapter/report.md).

Blobs must have a length divisible by 16 and no greater than 32,768 bytes. The
gate at offset 64 must fit, making the effective minimum 80 bytes. A 16-byte
blob cannot implement this two-entry profile and is rejected. Construction does
not infer an ELF map or claim that arbitrary bytes implement the declared ABI.

The manifest records both named hooks, exact addresses/before/after/following
bytes, targets, return address, ISA/calling convention and ownership contract,
plus source/blob/output hashes. `verify_graphics` reconstructs the entire output
and requires an exact manifest, including JSON value types; callers cannot
provide arbitrary patch offsets or alternate addresses.

```python
from build_memomind_graphics import construct_graphics, verify_graphics
output, manifest, proof = construct_graphics(text_source_bytes, linked_blob_bytes)
verified_output, proof = verify_graphics(text_source_bytes, linked_blob_bytes, manifest)
```

The CLI takes source and blob paths, with an optional new output directory.
Without that directory it previews the manifest. `--manifest PATH` requires an
exact reconstruction. A new output directory contains firmware, blob, manifest
and verification JSON; existing directories are not overwritten.

The append builder updates matching metadata and checksum layers. After both
hooks, the graphics builder recompresses and checks final application allocation
and staging capacity again, including the 4096-byte-rounded payload span. It
proves the complete original prefix differs only inside the two pinned ranges,
the exact padding/blob follow it, metadata equals the append stage, and all
other component streams remain identical to the original source.

Eight test groups cover exact byte preservation, instruction decoding and signed
displacements, both hook and following-instruction witness failures, overlap and
range guards, blob bounds/gate replay, source/output/blob/manifest/ABI tampering,
and final staging/allocation overflow. The maximum 32 KiB blob cannot naturally
exhaust the current approximately 296 KiB staging headroom; the final-overflow
test therefore injects an oversized repack result and checks rejection before
parsing. No modified source profile is accepted to manufacture that condition.

`analysis/graphics-container-validation.json` records synthetic, in-memory
construction fixtures. They are container tests, not executable graphics builds.
No candidate images or device actions are produced by that validation. Rendering,
queue lifecycle, code ABI, coexistence and hardware readiness require independent
runtime tests and evidence.
