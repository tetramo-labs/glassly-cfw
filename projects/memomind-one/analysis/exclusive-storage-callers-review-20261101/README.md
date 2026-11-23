# Executable exclusive-store caller regressions

Runner: `tests/rv32/exclusive_storage_callers_emulator_test.py`.

```sh
.tools/rv32-tests-venv/bin/python tests/rv32/exclusive_storage_callers_emulator_test.py \
  --output analysis/exclusive-storage-callers-native-NEW
```

Requires assertions enabled and exactly Unicorn2.1.4. Output must be a new directory under `analysis/`, outside frozen `analysis/ghidra/`. The runner fails on missing dependencies, source hash mismatch, unexpected native execution/data access, or exhausted instruction budget; it never skips these checks.

The runner applies the production constructor's six exact owner gates to the SHA256-pinned original app body. All caller instructions execute from that body. Initialized SRAM copies use the established startup mapping; BSS begins zero. A valid RET stop sentinel is emulation infrastructure and is never executed as target code.

The 28 cases cover:

- Installer `042a4598`: real teardown then mount refusal, synthetic old-allocation teardown, real busy/nonbusy tests, invalid ABI, null descriptor/output.
- Capacity query `042a4628`: mount refusal with output unchanged, existing-context refusal, invalid ABI, null descriptor/output.
- Select `042a4994`, remove `042a49e2`, clear `042a4a2c`: mount refusal before using deliberately unmapped arguments; applicable real busy/nonbusy paths.
- Both reset wrappers `0423eb42/0423eb52`: actual wrapper selects mode0/1, calls the real production reset gate, and propagates `-1`.
- Full worker entry `042a90ba`: reset `fffc`, installer `a8`, and capacity query `b0` jobs. Each is tested with immediate completion-enqueue acceptance and two failures before acceptance. Actual dispatch, native copy/zero, caller error handling, status/timestamp writes, and retry branches execute. The worker is stopped when it next requests a job after accepted completion.

Mocks are restricted to heap free, one owned job delivered through queue receive, ticks, display completion enqueue and sleep. Heap-free calls must match the exact null or synthetic owned token sequence. There are no allocation, lock, store, flash or KV mocks: reaching any of those routines is a failure. XIP store, peripheral and null memory remain unmapped; code/data hooks also allow only the reviewed native functions and expected memory ranges. Direct returns must preserve callee-saved registers, stack, gp/tp and all caller data. Worker task entry does not return, so callee-return checks are not claimed for it.

The separate existing `exclusive_storage_emulator_test.py` checks all six entry gates directly. This caller runner does not pretend to exercise internal program/erase/badmap callers once mount is refused; those paths are intentionally unreachable here.

This is not whole-boot execution, live device validation, actual RTOS contention, native allocator validation, running-plugin cancellation, downstream display/GM response execution, power-loss recovery, a native writer test, or exclusive ownership proof. Stack figures are observed selected-path usage, not worst-case task/interrupt budgets.

Execution history: child execution exited SIGILL132 in its local JIT environment (no report). Root run002 retained an explicit UC_ERR_EXCEPTION failure on the first case; the stop sentinel was then corrected. Root run003 passed all28cases: [report](../exclusive-storage-callers-native-003/report.json). Observed maximum selected-path stack was 320bytes. Test source is frozen at SHA256 `5e35f9ceab060abe0bfa502cf19459899a9621ae32622b80446a5a1d9121b94a`. Root executed the native JIT; this agent inspected its complete successful result and matching source hash. No failed-run artifacts were overwritten.
