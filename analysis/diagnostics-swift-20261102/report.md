# Swift diagnostic and cleanup commands

New sources are frozen: DiagnosticCommands.swift and DiagnosticCommandsTests.swift. No existing production files changed; BundleCommand, Session and FirmwareImage remain untouched. No device operations.

```swift
RasterCommands.diagnostics(.clear) // Data([7, 0])
RasterCommands.diagnostics(.hide)  // Data([7, 1])
RasterCommands.diagnostics(.show)  // Data([7, 2])
RasterCommands.cleanupSession()   // Data([11])
```

`DiagnosticControl` is a UInt8, CaseIterable, Sendable enum with exactly clear/hide/show. These pure encoders cannot create a malformed envelope, so they do not throw. Output contains no transport or zlib framing. Clear is a diagnostic-state mutation, not a read-only query. Hide retains history; show does not itself request a frame refresh. The API neither transmits commands nor claims native capability/completion.

Pinned G2 contract: image_dispatch masks the high mode bit. Mode7 accepts missing/unknown subcommands as successful no-ops and ignores trailing bytes; sub0 clears sticky flags/counters and frame-order state,1 hides,2 shows. Mode11 ignores trailing bytes and returns the cleanup handler's result. Canonical APIs deliberately omit ignored highbits/trailing/unknown actions. Neither mode is legal inside mode8. Native cleanup covers only implemented controllers and resources; these encoders do not claim G2 native feature parity, stock UI restoration, timer deletion, or safe retries after ambiguous IO.

Validation:

- 12 focused Swift test methods pass:3 new diagnostic/cleanup tests and9 existing bundle tests. Includes exact literal fixtures, all256 enum raw values, canonical cleanup value ownership, and forbidden bundle admission for7/87/11/8b with trailing bytes.
- 2071 independent original-dispatcher checks pass. The exact mode7 and mode11 branches are extracted from pinned G2 zlib_glue.c; context header is pinned and its original16-entry FID ring retained. The oracle checks all256 subcommands, both mode heads, missing/trailing forms, null context and cleanup result propagation. Host diagnostic context/allocator-clear callback and cleanup callback are explicit mocks. Cleanup internals, native display quiescence and timers are not exercised.

Source commit `1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`; source and branch SHA256s are in reference.json and report.json. MIT provenance points to LICENSE.

```sh
python3 analysis/diagnostics-swift-20261102/generate_reference.py
swift test --package-path swift/MemoMindKit --scratch-path /tmp/mm-swift-diagnostics-tests --filter 'DiagnosticCommandsTests|BundleCommandTests'
```
