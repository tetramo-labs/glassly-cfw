# Actual RV32 probe executable tests

This harness executes the exact 208-byte `runtime/build/probe-003/probe.bin`
(SHA-256 `e6d9edd7e761fcc0c661e4b441eb45a642b4ead4a8acdb690286ceec7f42726b`)
at its linked entry `0x0439bea0` using Unicorn's real `UC_ARCH_RISCV` and
`UC_MODE_RISCV32`. The compiled compressed instructions and C function run in
the emulator. The ELF companion must identify itself as ELF32 little-endian
`EM_RISCV` (243), with the expected entry. Its architecture is never rewritten.

This is **mocked-native execution, not hardware validation**. Four native helper
entry boundaries have explicit stubs using the contracts established in
`analysis/ghidra/append-hook/report.md`:

| Address | Mocked contract |
|---|---|
| `0x042e4680` | Observe original stock handler entry and stop, without executing its body |
| `0x042eff8e` | Receive a pointer to the local request pointer, record cleanup and clear that slot |
| `0x042ef9f6` | Read/validate the linked JSON text and return an opaque response-list pointer or NULL |
| `0x042ef924` | Verify status 4 and NULL text, then return an opaque response pointer or NULL |

The stub locations contain valid RV32 RET instructions solely to let Unicorn
translate those entry boundaries. The pre-instruction hooks handle them before
the shim instructions execute. All other unexpected executable addresses fail.
The request is opaque: native TLV-node traversal, allocation and actual freeing
are deliberately not claimed. Register poisoning at native return points tests
that the wrapper does not depend on caller-saved values surviving a helper call.

Coverage includes all 256 command-byte values with both NULL and nonempty request
pointers, plus six explicit success/failure response combinations: **518 successful
execution cases**. Two negative tests confirm rejection of an adjacent canary
write and an unmapped response write.

- Every command except `0x7e` reaches stock with `a0..a7`, `ra`, `sp`, `gp`, `tp`
  and all integer callee-saved registers unchanged; no stack space or writes occur.
- Command `0x7e` uses exactly 32 bytes of stack. A nonempty request is passed to
  cleanup by address exactly once before response allocation; a NULL request
  does not call cleanup.
- The linked JSON matches the expected profile/ABI/entry, and its returned list
  pointer is assigned to the caller's response slot. JSON allocation failure
  calls the native status helper with `(4, NULL)`. Failure of that helper assigns
  NULL. Sequence and other caller memory remain untouched.
- Every tested path preserves `ra`, `sp`, `gp`, `tp`, and `s0..s11`. CPU writes
  are restricted to the 32-byte frame and exact four-byte response slot. Mocked
  native writes receive the same bounds checks. Code and opaque request pages
  are read-only, and surrounding stack/caller canaries are checked afterward.

Synthetic RAM addresses are harness fixtures, not an assertion about free memory
on the glasses. These tests establish behavior under the mocked helper contracts;
they do not test native allocator internals, RTOS scheduling, firmware startup,
transport framing or hardware execution.

## Reproduce on macOS ARM64

The task-local dependency is Unicorn 2.1.4, installed from its official PyPI wheel.
The requirements file pins that wheel's SHA-256; no global installation is needed.

```sh
python3 -m venv .tools/rv32-tests-venv
.tools/rv32-tests-venv/bin/python -m pip install --require-hashes --only-binary=:all: -r tests/rv32/requirements-macos-arm64.txt
.tools/rv32-tests-venv/bin/python tests/rv32/probe_emulator_test.py --report analysis/rv32-probe-emulation.json
```

`analysis/rv32-probe-emulation.log` records the test run. The JSON report retains
every successful case, native calls, stack/write counts, exact blob/ELF hashes,
and executed probe instruction addresses. Assertions are part of the harness:
run normal Python, not `python -O`.

The aggregate `tests/run_tests.py` recompiles the checked-in probe first, then
passes that new directory with `--build`. The emulator still requires the exact
installed blob hash, so a source change cannot silently test an older binary.

The test approach is patterned on G2's
`patches/host/keyboard_emulator_test.py`: execute the actual compiled extension,
stub explicit native imports, inspect arguments and memory, and fail on unknown
calls. This is a separate RV32 implementation; G2's ARM binary and repository
are not modified or relabeled as MemoMind firmware.

## Render instruction profile

`scene_render_benchmark.py` replays scene commands a phone renderer produced
(`fixtures/dashboard-scene-commands.json`: a dashboard cold open, a clock tick, a
tween, an unchanged frame, HIDE and reopen, captured from the iOS renderer) through
the real display job of a linked build and attributes every instruction to the
runtime function it ran in, with the most frequent caller -> callee entries on
request. Native fonts, flash and LVGL are the existing mocks, so this measures the
runtime's own work for comparing builds, not time on the glasses.

```sh
cd tests/rv32 && ../../.tools/rv32-tests-venv/bin/python scene_render_benchmark.py \
  --build ../../analysis/renderer-20261105/build-12-05 \
  --commands fixtures/dashboard-scene-commands.json --report /tmp/bench.json --calls 12
```

`analysis/renderer-20261105/benchmark-v11.json` and `benchmark-v12.json` are the
revision 11 and 12 profiles of that fixture.
