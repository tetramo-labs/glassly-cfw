# Swift mode15 encoder

The Swift encoder and mode8 admission update are complete. The focused Swift run passes all16 test methods (7 text,9 bundle); the independent pinned G2 parser oracle passes963 cases. No device operations, native runtime changes, catalog edits or Session changes were performed.

API:

```swift
try RasterCommands.builtinText(bytes: data, x: -1, y: 100, options: 0x1f)
try RasterCommands.builtinText("TEXT 15", x: 70, y: 100, options: 0x1f)
```

Both return canonical `[0f][x:s16LE][y:s16LE][options:u8][byteCount:u8][bytes]`, exactly7+count bytes. Coordinates may be outside600×350 provided they fit signed16; native glyph clipping remains separate. Empty text is legal, max255 bytes yields262 command bytes. String input counts UTF-8 bytes, never truncates or normalizes. Raw input preserves exact bytes and rejects NUL separately from malformed UTF-8. Controls1..31 move x by byte-11; LF and CR are not line breaks. DEL and valid Unicode noncharacters remain syntactically accepted without promising font coverage. The upper options bits0xc0 are preserved/ignored,0x20 inversion and0x10 original-zero transparency precede low-nibble intensity scaling. Default0x0f is opaque full intensity.

`RasterCommands.bundle` now accepts15/8f, enforcing exact7+byteCount and preserving raw bytes/highbit. Its established validation boundary remains envelopes only; raw child NUL/malformedUTF8 may be encoded into a bundle and rejected by native execution. Prefer the typed text encoder for syntactic validation. Canonical text output always uses0f; callers may manually set8f for upstream-compatible ignored-highbit behavior. Native capability must be checked before transmitting. Bundles remain sequential with possible earlier effects on later failure.

## Evidence

Pinned upstream commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`: `patches/texture_cache.c` strictUTF8 and `cfw_builtin_draw_string_buf`; `patches/zlib_glue.c` masks mode highbit and passes mode15 payload. SHA256s are in report.json/reference.json and checked against tests/g2_compat/UPSTREAM.json. MIT headers and existing LICENSE preserve provenance.

The independent oracle uses Python struct.pack for wire construction and the verbatim original C UTF8/parser/render loop. Its live lease, font metrics, zero-area glyphs and pixel callbacks are explicit mocks. It checks all256 single bytes/options, signed extremes, empty/max payload, strictUTF8 scalar boundaries, malformed forms, every fixture truncation, trailing rejection, and both mode heads. It makes no actual native glyph/pixel assertion. Generated literal Swift fixtures are compared byte-for-byte; Swift tests additionally exercise Data slices, coordinate overflow,255/256 byte lengths with multibyte strings, all controls/options, NUL/malformed distinction, no Unicode normalization and highbit bundle preservation.

The initial Swift run exposed a test conversion issue: Foundation's String(data:encoding:) consumes a leading UTF8 BOM when constructing a String. The encoder's raw path never reserializes this temporary validation String and already preserved bytes correctly. The fixture conversion now uses String(decoding:as:) on independently validated fixture bytes, preserving BOM. The original failed log is retained; the final run passes. No production behavior workaround was required.

Commands:

```sh
python3 analysis/text-swift-20261102/generate_reference.py
swift test --package-path swift/MemoMindKit --scratch-path /tmp/mm-swift-text-tests --filter 'TextCommandTests|BundleCommandTests'
```

Reference regeneration writes only this analysis directory and TextReferenceVectors.swift. The focused tests do not establish real native font coverage, display ownership, visual output or hardware compatibility. Those remain separate native/emulator/hardware evidence.
