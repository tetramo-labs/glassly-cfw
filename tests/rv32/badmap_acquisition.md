# Native badmap acquisition regression

```sh
.tools/rv32-tests-venv/bin/python tests/rv32/badmap_acquisition_emulator_test.py --output /tmp/memomind-badmap-new-run
```

The output must be a new directory outside `analysis/ghidra`. The runner refuses
Python `-O`, missing dependencies, and any Unicorn version except 2.1.4.
Success or failure writes `report.json`, including partial cases, invocation,
source hashes and errors. An existing output directory is never overwritten.

This promotes all 43 cases from the frozen
`analysis/ghidra/badmap-acquisition-review/emulate.py`. Both its native emulator
harness and its case predicates are retained, with only the CRC-table loading
moved after source verification. Runtime textual checks compare those blocks
against the SHA-pinned original. All 43 unique case names, their order and every
result field must match the SHA-pinned original `emulation.json`; removed cases
or weaker assertions cannot silently pass. Original source and baseline hashes
are constants in the runner, alongside application body SHA-256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.

The actual RV32 KV getter, sector iterator, cached-base getter, badmap loader,
CRC32, bitmap validator, CRC8 and native memory functions execute. Only RTOS
mutex take/give are mocked; synthetic initialized globals and read-only KV
pages replace device state. Allocator, initializer, assertion, mutation and
badmap-save entry points are forbidden. Target writes must remain in synthetic
scratch/stack RAM. Guards, callee-saved registers, gp/tp/sp, lock pairing, output
bytes and status/length are checked. Cases cover both KV formats, absent keys,
valid zero/nonzero maps, directory/tail bits, wrong physical identity, malformed
record lengths and CRCs, KV corruption, null arguments and uninitialized KV.

The promoted run passed 43/43 with all observations identical to the frozen
baseline; maximum observed native stack was 272 bytes for the full loader,
excluding real RTOS and interrupts. Reused-output, frozen-directory and disabled-
assertion guards also passed. First promotion artifact:
`/tmp/memomind-badmap-promotion-01/report.json`.

These tests acquire no real device bitmap and establish no physical locking,
concurrency, cancellation, worst-case stack or flash-persistence guarantees.
