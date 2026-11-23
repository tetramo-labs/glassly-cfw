# Compiled probe-003 delta review

**No static blocker identified. The revised stock-command path adds no stack
frame and changes only caller-saved `t0`.** This supersedes the candidate-specific
probe-002 review; neither reviewed candidate was flashed by this agent.

[Independent verification results](compiled-probe-003-review.json) cover the
actual source/entry/linker hashes, ELF, flat blob and generated OTA:

- Blob: 208 bytes, SHA-256
  `e6d9edd7e761fcc0c661e4b441eb45a642b4ead4a8acdb690286ceec7f42726b`.
- OTA: SHA-256
  `ae04bec4649b685bf2a73265aa468ff8431e76a1371d584f35349e7de071de78`.

All 100 instruction bytes were reconstructed from the compiler disassembly and
matched to the actual ELF and flat binary. Read-only data also matches. The
actual OTA was decompressed and CRC-validated; its appended bytes match the
reviewed blob, and its hook plus preserved callback store remains
`b7c73904938707eabcd8`, loading `a5=0x0439bea0`.

## Entry gate

The assembler expands the source equality branch into an inverse branch and
unconditional jump. The actual bytes decode as:

```
0439bea0  li   t0,0x7e
0439bea4  bne  a0,t0,0x0439beac
0439bea8  j    0x0439beb6          # ping C implementation, no link
0439beac  lui  t0,0x42e4
0439beb0  addi t0,t0,0x680
0439beb4  jr   t0                  # stock 0x042e4680, no link
```

Decoded the actual B/J immediates and evaluated target selection for all 256
command values: only `0x7e` reaches the probe; every other value reaches the
original handler. Both jumps preserve `ra`. The stock path preserves `sp`, all
argument registers, `gp`, `tp`, all saved registers and all FP registers. No
instruction touches memory on that path. Clobbering `t0` conforms to the recovered
integer callback ABI. The stock handler returns directly to the original
dispatcher continuation, eliminating probe-002's extra 32-byte nested frame.

## Ping C path

At `0x0439beb6`, ping allocates a 32-byte aligned frame, saves `s0` and `ra`, stores
request at `sp+12`, and copies the response-slot pointer into `s0`. Non-NULL
request cleanup passes `&request` to `0x042eff8e` at `0x0439becc`.
The JSON constant remains at `0x0439bf04`; `0x0439bede` calls `0x042ef9f6` to
allocate/copy its type-5 response. Allocation failure calls `0x042ef924(4,NULL)`
at `0x0439bef8`. Both return paths store the resulting list through `s0` and
restore `s0`, `ra`, and `sp`. Sequence is untouched. Response ownership remains
with the stock dispatcher after return, matching [the native proof](report.md).

The final ELF retains RV32 compressed/single-float ABI, no writable allocated
sections, no final relocations and no unresolved symbols in the build evidence.
Neither path touches `gp`, `tp`, or FP registers. The linked ping entry is
2-byte aligned, valid for this compressed-instruction target.

The remaining limitations are unchanged: static review cannot demonstrate
expanded-image boot acceptance or executable access to the appended region.
Ping itself needs 32 bytes of stack plus stock helper frames, and no live
stack-watermark measurement was available. If both response allocations fail,
NULL causes no reply; it does not fabricate an invalid list pointer.
