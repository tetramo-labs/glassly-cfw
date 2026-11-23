# Native Swift mode8 bundle encoder

`RasterCommands.bundle(_ commands: [Data]) throws -> Data` emits canonical `[08][count:u8][length:LE16][child]...`, preserving child order and bytes. Count0..255 is accepted. The whole command is limited to the current MemoMind8192-byte ingress capacity. Empty children, children exceedingLE16, nested bundles, control modes outside the allowed set, and mode15 are rejected. Mode15 remains unavailable in this MemoMind adapter.

Allowed base modes are3/6/9/19/20/36/37..41. Child highbits are preserved while admission checks `mode & 0x7f`, coordinated with the native agent.83/89 retain first/left display selection; other highbits are ignored by the native dispatcher. The API emits only canonical08, not88, and emits no trailing bytes. The original G2parser accepts08/88 and ignores trailing bytes.

Canonical child-envelope checks cover minimum headers, exact mode19 length10, and mode20 length11+its byte10 string count. The encoder does not parse RLE expansion, rectangle bounds, variable shape records, retained scene entries, asset resolution or epochs. Typed child encoders should be used where available; successful construction does not guarantee native acceptance. Native capabilities and display state must be checked by the live caller.

A successful bundle schedules one final presentation after sequential subcommands. This is not a transaction: a later failing child can leave earlier pixel/cache mutations in place. Only the final cache-reply scratch is retained; no per-child reply list is promised. Empty bundles still request final presentation.

All eight Swift test methods pass. They cover all supported highbit forms, every unsupported raw mode byte, every truncated fixed envelope, exact255/256 command count, declared string lengths, LE16 lengths, exact8192/8193 capacity, ordering and data slices. Tests explicitly demonstrate that malformed child semantics may pass envelope-only checks.

The independent reference harness retains the entire pinned G2mode8 dispatch branch verbatim, with child calls replaced by a recorder and simulated failure. All307 checks passed: calls preserve order, receive present=0, failure after child2 preserves child1 effect and suppresses final presentation, and count/truncation/mode boundaries match. These are branch-envelope tests, not full child dispatch, transport maximum, framebuffer or hardware tests. The source, branch and final Swift hashes are in `reference.json` and `report.json`. Original revision1a6db4fd75de202a96599cc8f9f12fa721e7c3ce, MIT; full license at `LICENSE`.

No existing Swift source, firmware, catalog, CLI, device or Ghidra files were modified. The fixture generator is an explicit developer operation that rewrites its generated Swift fixture file; ordinary Swift tests need no Python or C runtime.
