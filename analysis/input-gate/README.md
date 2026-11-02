# Optional cooked-input observer gate

The compiler's `--input-observer` flag requires `--scene-session`, defines
`MM_GRAPHICS_INPUT=1`, adds `runtime/graphics/input.c`, and retains
`glassly_input_command` / `glassly_input_observe`. Default builds preprocess the
new assembly branches out. The scene-only check build remains44,592 bytes with
SHA256 `cd849a72ecd662a79327d01f792ddbe6b09cd5d7a2a683aa05440301dced2bbd`.
The original scene emulator pin is unchanged. Final app/staging and64KiB ELF
limits remain enforced by the existing compiler and constructor.

Service15 command0x7c tail-routes to the four-argument input command handler;
0x7d/0x7e keep the existing handlers, and all other commands tail-route stock.
The service gate is46 bytes, inside its64-byte slot. Display gate entry remains
0x0439bee0 and begins the exact displaced `lw a0,-0x70(s0)`. NULL passes stock.
Class low6bits2, len0 admits only1f7b..1f7f and1fb0..1fb9; class3, len0 admits
only1..8. Matching input calls `void glassly_input_observe(const void *envelope)`
with borrowed original storage, then always tail-routes stock0x0425b38a.
Graphics class63/event474c keeps the custom graphics route.

The observer call uses a144-byte aligned temporary frame saving ra, a0..a7,
t2..t6, all ABI caller-saved FPRs and fcsr. Its ABI must preserve callee-saved
integer/FPR state and gp/tp. On stock entry the original stack, return address,
argument and preserved register state are restored; only t0/t1 are scratch.
No observer event is consumed. No other ordinary path writes memory or allocates
stack. The stock worker remains owner of the envelope and cleanup continuation.

`fixture-001` links actual gates with clearly labelled synthetic C bodies; it
does **not** include the scene or input C implementations. Its manifest marks
the intended scene/input profile for the gate harness and explicitly identifies
its fixture scope. `fixture-001-gates.json` passes7,955 cases with92 admitted
observer calls. The mock deliberately poisons caller integer/FPR/fcsr state;
actual assembly restores it before stock dispatch and reaches the actual
patched callsite continuation. All256 service commands, all256 class bytes,
known/invalid events, nonzero lengths, and NULL are exercised. `default-scene-
gates.json` passes the previous1,345 gate cases on the byte-identical default.

**Normal stock FP context is now supported by independent native evidence:**
startup sets FS=3, display task creation preserves it, and the scheduler saves/
restores all32 FPRs; see `../ghidra/input-adapter/fpu-context.md`. FSW/FLW/fcsr
instructions still trap with FS Off; the harness explicitly enables FS=Dirty
and uses real CSR instructions to initialize/clobber/check fcsr. The native
switch excerpts do not establish per-task fcsr isolation. Gate tests alone
neither execute observer C nor establish hardware input or whole RTOS stack
safety. No device actions occur in this test work.

## Implemented input-004 profile

The complete C/native integration is described in
`../../runtime/graphics/INPUT.md`. Input-004 is49,248 bytes, SHA256
`3f8e637dff1f9da760b8842d1041eb88579cabc1b864bb5605d21bb9205167b4`.
`input-004-gates.json` passes all7,955 cases on that exact blob.
`input-004-runtime.json` executes real linked C/native adapters:6 groups,
1,710 calls;48 BT calls/14,509 instructions and1,662 display calls/496,089
instructions. Observed synthetic stack is464 B BT /800 B display, excluding
mocked native frames. The whole-C harness calls the C observer directly;
observer-to-stock assembly preservation is checked by the separate gate harness.
It also exercises hidden and visible graphics owners simultaneously, actual
DELETE callbacks, and four-byte-only owned allocation alignment.

`host-005/report.json` records ASan/UBSan tests and the production Python client's
schema checks against actual C-generated JSON. No-input default builds remain
byte-identical: graphics7,808 B/SHA08d47832… and scene44,592 B/SHAcd849a72… .
Independent native implementation review is
`../ghidra/input-adapter/input-review.md`. It reports no concrete lifetime/ABI
blocker in the pinned snapshot and retains the native OOM/timing/whole-stack
limitations. Offline OTA candidate, manifest and integrity/bounds proof are in
`../../captures/firmware/input-observer-001/`; none was sent to a device here.
