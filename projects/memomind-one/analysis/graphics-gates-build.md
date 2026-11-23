# Linked graphics gates and RV32 boundary tests

The two fixed assembly gates are in `runtime/graphics/entry.S`, linked by
`runtime/graphics/graphics.ld`. `service_entry` occupies 34 bytes at `0x0439bea0`.
It directs command `0x7e` to `glassly_graphics_probe`, `0x7d` to
`glassly_graphics_command`, and tail-jumps every other command to stock
`0x042e4680`. It allocates no stack and changes no memory or argument registers.

`display_gate` occupies 50 bytes at `0x0439bee0`. Its first instruction is exactly
the displaced `lw a0,-0x70(s0)`, bytes `032504f9`. It checks envelope byte 1 masked
with `0x3f`, then the little-endian event halfword at offset 4. Only class `0x3f`
and event `0x474c` reach `glassly_graphics_display`; all other envelopes tail-jump
to `0x0425b38a`. It uses only t0/t1 as scratch, makes no stores and allocates no
stack before either C/native boundary. The envelope is supplied by the worker;
valid frame/envelope pointers remain the stock caller's precondition.
The post-audit gate first checks the loaded envelope for NULL, forwarding NULL
directly to stock without dereferencing it. This preserves stock NULL handling.

Required C files are `runtime/graphics/graphics.c`, `runtime/graphics/native.c`
and portable `geometry.c`. The C prototypes are:

```c
void glassly_graphics_probe(uint32_t, void *, const uint8_t *, void **);
void glassly_graphics_command(uint32_t, void *, const uint8_t *, void **);
void glassly_graphics_display(void *envelope);
```

Build with `python3 -B scripts/compile_memomind_graphics.py NEW_BUILD_DIRECTORY`.
The compiler uses the existing task-local xPack GCC 15.2.0 toolchain, RV32IMAFC,
ilp32f, no small-data references and no relaxation. The linker pins both entries,
rejects gate overlap and nonempty data/BSS/TLS/GOT/constructor sections, and caps
the region at 32 KiB. A real file-backed zero pad aligns the output to 16 bytes.
Post-link validation independently checks actual ELF32/RISC-V identity and float
ABI, one RX load segment, matching file/memory sizes, the bounded mapped address,
no allocated NOBITS/writable sections, no relocations, and no undefined symbols.
The build records ELF/map/disassembly/symbols, all source/header hashes, flags,
blob hash and compiler `.su` reports. Concurrent input changes reject the build.

Per-function stack frames must be static and at most 512 bytes. That is **not a
cumulative call-chain bound or proof of the Bluetooth/display task stack size**.
The initial real build reports 304 bytes for the probe handler, 48 for the command
handler, 80 for the display handler and 224 for the geometry entry, before nested
callee frames. Root-owned runtime changes may require a new build and audit.

`--gate-fixture` instead links clearly labeled synthetic C entry stubs from
`tests/rv32/graphics_gate_stubs.c`. Successful fixture
`runtime/build/graphics-gates-003` is 128 bytes, SHA-256
`8c3562ed2e499b4ef8c6eb6427bdfa7b7f8e5295b6fab5931117b2151cd5809e`.
It is for gate testing, not a graphics implementation or flashable candidate.

`tests/rv32/graphics_gate_emulator_test.py` executes the actual linked RV32 gates
with Unicorn 2.1.4 and mocks only C/native entry boundaries. It accepts `--build`
for either fixture or real linked builds. It also executes the actual replacement
AUIPC/JALR instructions at worker callsite `0x0425c00a` and observes return to
`0x0425c012`, proving the displaced load obtains the envelope through the original
worker s0 frame. The C/native return itself is mocked, not a claim about C behavior.

All 1,344 cases pass on both the fixture and the initial real 7,744-byte build
`runtime/build/graphics-initial-002`: 512 service cases cover all command bytes
with null/nonempty requests; 768 cases cover every class byte with matching and
nonmatching events; 64 additional cases reject each one-bit event mismatch for
the four class-byte values whose low six bits equal 63. Every boundary checks
all integer registers except allowed t0..t2 scratch, preserves the original stack,
and rejects any memory write. Display checks allow only the displaced a0 change
and the callsite's expected return-address change.

Reports: `analysis/graphics-gate-emulation.json` and
`analysis/graphics-real-gate-emulation.json`. These are gate ABI/routing tests;
graphics C execution, ownership, UI lifecycle and hardware rendering require
separate evidence. No installed probe, flasher or device was changed.

The final gate run uses `runtime/build/graphics-004`, 7,808 bytes, SHA-256
`08d478321f5340d06eab0f7007a49741a1ee7b1d8a3f716534221672ceac0b39`.
Its 1,345 passing cases include the additional NULL-envelope case. The report is
`analysis/graphics-final-gate-emulation.json`. Real C/native-wrapper execution is
covered separately in [graphics-runtime-emulation.md](graphics-runtime-emulation.md).
