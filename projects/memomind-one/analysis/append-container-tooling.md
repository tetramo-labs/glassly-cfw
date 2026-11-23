# Bounded application append construction

`scripts/append_memomind_app.py` constructs an OTA offline from either the exact
captured stock image or the visually confirmed text-patch image. It appends to
component 3 inside its existing 2 MiB allocation. It does not change any partition
start, allocation, load address, version or entry point. Existing same-length
patch tools are unchanged.

The importable entry point is:

```python
output, audit = append_app(
    source_bytes, payload_bytes,
    expected_source_sha256="941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876",
    alignment=16,
    # Optional on first construction; required by CLI when writing an OTA:
    expected_output_sha256=None,
)
```

An empty payload returns the original OTA byte for byte, without alignment
padding. Nonempty payloads receive zero padding before the payload so its derived
XIP address satisfies the requested power-of-two alignment (1 through 4096).
The entire original application body remains an identical prefix. There is no
ELF import, relocation, hook installation or RAM allocation in this operation.

For both pinned sources the original body ends at offset `0x1b0e78`, derived XIP
address `0x0439be98`. At alignment 16, eight zero bytes precede the payload:

| Coordinate | Payload start | Existing allocation end, exclusive |
|---|---:|---:|
| Application body offset | `0x1b0e80` | `0x1fffe0` |
| Physical flash | `0x39bea0` | `0x3eb000` |
| Derived XIP | `0x0439bea0` | `0x043eb000` |

The maximum payload allowed by the application allocation at this alignment is
323,936 bytes. The separate staging bound can reject a smaller payload: compressed
size depends on the actual bytes. The OTA payload excluding its 18-byte envelope,
and its 4096-byte-rounded span, must fit the metadata type-4 allocation of
`0x25e000` (2,482,176 bytes). This matches the bound used by native capacity getter
`0x043415b4` and the `e2` parser. It is based on the pinned partition metadata and
native analysis, not a live flash read. An incompressible maximum-size tail is
explicitly tested and rejected despite fitting the application allocation.

Construction updates the application header body length and CRC32, the matching
partition metadata body-size word at raw metadata offset 76, compressed metadata
length, application raw/packed table lengths, table CRC32, packed-stream CRC32,
outer payload length and outer CRC32. The metadata's raw size stays 344 bytes.
Streams 1, 2, 4, 5 and 6 retain both their raw and compressed bytes exactly.
Reparsing checks every decoded stream, metadata correspondence and checksum.
Independent postconstruction assertions restrict all other header/metadata
changes and prove the application prefix and appended byte ranges.

The audit records exact source/output/payload hashes, padding, append ranges,
prefix hash, untouched stream hashes, file/flash/XIP coordinates and both bounds.
The CLI previews JSON without writing an image. Supplying `--output` requires
`--expected-output-sha256` from the preview; output and optional `--audit` files
must be new. This prevents accidental overwrites and pins the exact emitted OTA.

`analysis/append-container-validation.json` records in-memory synthetic append
audits for both actual fixtures; no candidate image was written for those audits.
Seventeen relevant tests pass: seven append tests, five existing same-length
patch tests and five existing container tests. They include exact application-end
growth, overflow from one byte or alignment padding, staging overflow, no-op byte
identity, hash rejection, native-equivalent CRC/accounting and composition with
the existing same-length repacker after appending.

These coordinates describe the firmware container and its existing mapping.
They are not a fabricated ELF load map. A real payload must be linked for the
reported address and separately assessed for startup, register/stack conventions,
RAM use, hook behavior and bootloader handling of a grown component. The successful
text patch does not by itself establish any of those properties.
