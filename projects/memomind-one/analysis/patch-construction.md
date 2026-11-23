# Reproducible offline patch construction

`scripts/apply_memomind_patch.py` adds the hash and byte-witness approach used
by g2flash to the recovered MemoMind container. It imports no device transport.
It does not select an executable hook or provide a ready-to-flash custom image.

The JSON manifest contains exactly these top-level fields:

- `format`: `memomind-body-patch-v1`.
- `source_sha256`: exact original OTA SHA-256, lowercase hexadecimal.
- `output_sha256`: exact expected rebuilt OTA SHA-256.
- `edits`: nonempty array of explicit component-body edits.

Each edit contains exactly `component` (integer1–6), `body_sha256` (original
decompressed body hash), `offset` (nonnegative byte offset after its32-byte
image header), `before` and `after` (nonempty hexadecimal strings without
spaces), and `reason` (human-readable rationale). Bytes must actually change
without changing length. Original-byte mismatches, overlapping edits, changed
base/body hashes, unknown keys and mismatched final output hashes are rejected.

The existing `memomind_ota.py repack` command can construct a candidate from a
reviewed same-length replacement body and report its output hash. A patch
manifest then pins that expected artifact for independent replay. The patch
tool rebuilds component CRCs, compression lengths and all known container
checksums, re-parses the result, and verifies untouched streams remain exactly
identical. Source and output hashes make compiler/compressor differences fail
explicitly rather than silently creating a different firmware artifact.

```sh
# Construct and verify in memory; no output image written.
python3 scripts/apply_memomind_patch.py stock.bin reviewed-patch.json

# Write only after successful validation; existing files are never replaced.
python3 scripts/apply_memomind_patch.py stock.bin reviewed-patch.json \
  --output new-custom-candidate.bin
```

Five tests exercise the actual captured stock container, including wrong
source/body/output hashes, byte witnesses, offset/type/length checks, overlap,
empty/no-op edits, and preservation of unrelated streams. Their deliberately
meaningless single-byte edit stays in memory; it is not an executable patch,
not saved as a firmware candidate and not sent to glasses.

These checks establish reproducible container construction. They do not prove
that an instruction change is correct, that the boot path accepts it, or that
the device can recover from it. The separate stock transaction driver rejects
all modified images. A real feature patch still needs exact code/data witnesses,
a supported firmware ABI, and evidence for its execution and recovery path.
