# Actual graphics C/native-wrapper execution in RV32

`tests/rv32/graphics_runtime_emulator_test.py` runs the actual compiled graphics
handlers, native.c adapters, ownership callbacks and portable geometry code.
It pins the final `runtime/build/graphics-004/graphics.bin` to SHA-256
`08d478321f5340d06eab0f7007a49741a1ee7b1d8a3f716534221672ceac0b39`, 7,808 bytes.
The real ELF is checked as ELF32 little-endian EM_RISCV, and Unicorn 2.1.4 executes
in `UC_ARCH_RISCV / UC_MODE_RISCV32`. No architecture relabeling is used.

Only the external firmware API addresses listed in the report are stubbed.
The actual compiled `request_bytes`, `find_owner`, `post`, `send`, `screen`,
`launcher_active`, `image_source`, `timer_userdata` and `try_alloc` adapters run.
The actual C `deleted` and `tick` callbacks also execute through an explicit
mock native DELETE-event return boundary. Native APIs may poison all integer
caller-saved registers; integer and floating-point callee-saved registers, gp,
tp, stack and return state must survive each completed handler call.

Eight test groups pass, comprising **37 successful handler calls**:

- Passive identity JSON is parsed and checked for the exact profile, modes,
  explicit shape types 1 through 13, and full-width hexadecimal free/low-water
  snapshots. Nonempty requests are cleaned up by address.
- Command extraction executes the actual native TLV layout reads: exactly one
  type-1 BYTES node, a 24-bit length and data pointer. Multiple nodes, wrong type,
  NULL header/data/sequence/request, oversized lengths and incomplete geometry
  are rejected without posting work.
- The actual command handler constructs version/event/length/job bytes. The
  queue stub copies them while the job is live; the request is released and the
  job subsequently freed. Injected queue drops produce no false immediate success.
- Display execution creates the real owner/descriptor/palette in guarded memory,
  invokes the actual geometry function and produces exactly one color-10 pixel
  in a 600×350 packed-GRAY4 image. All 105,000 pixel bytes and the 64-byte palette
  are compared; the native descriptor header, length and retained pointer match.
- Clear, lease expiry and UI transitions execute the actual deletion/timer
  callbacks. Timer, pixels and owner are freed once; the borrowed worker envelope
  remains live. Real native-wrapper child/event-record lookup finds the owner.
- Seven injected construction failures cover owner allocation, image creation,
  DELETE registration, timer creation, pixel allocation, early headroom and late
  headroom. Each returns the expected error and leaves no owned allocation,
  image or timer. JSON/status allocation failures exercise response fallback.

Every CPU data access is checked against live allocations, bounded flash or the
active synthetic task stack. Read-only request allocations, freed blocks and
allocation gaps reject writes or use-after-free. Native stub writes receive
matching checks. The modeled stacks are **4 KiB for BT** and **8 KiB for display**;
observed maxima are **336 bytes** and **352 bytes**, respectively, for these cases.
Those measurements are not exhaustive call-chain/task-stack proofs.

Run against a freshly compiled directory using:

```sh
.tools/rv32-tests-venv/bin/python tests/rv32/graphics_runtime_emulator_test.py --build runtime/build/graphics-004 --report analysis/graphics-runtime-emulation.json
```

`--build` accepts an external build directory, but the exact final blob hash
remains mandatory. This prevents an aggregate regression from silently testing
a stale artifact. Results and native-call traces are in
`analysis/graphics-runtime-emulation.json`; the test log is
`analysis/graphics-runtime-emulation.log`.

This remains **mocked-native execution, not hardware validation**. Native heap,
LVGL, queue and serialization internals are modeled contracts. Injected NULL
returns test C cleanup; real native LVGL allocation failures may assert instead.
Parsed TLV allocations must be valid: arbitrary forged pointers are not a
supported parser input. Geometry execution here uses a point-line record; other
primitive algorithms have separate portable tests. Scanout, actual transport,
concurrent RTOS scheduling and physical rendering are outside this harness.
