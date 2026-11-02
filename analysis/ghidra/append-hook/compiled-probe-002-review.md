# Compiled probe-002 review

**No static ABI or request/response ownership blocker was identified for this
exact candidate.** This review does not prove boot acceptance or live execution.
No device action or firmware modification was performed by the reviewer.

Inputs were `runtime/probe.c`, `runtime/probe.ld`, the actual ELF/flat binary and
compiler outputs under `runtime/build/probe-002`, and the final generated OTA.
Independent checks are recorded in
[compiled-probe-002-review.json](compiled-probe-002-review.json).

- Blob: 208 bytes, SHA-256
  `217431d6b0b8c7b6c5dc9f31d13e761938acd2a9e8b02de8ff4c1d38de89ba2c`.
- OTA: SHA-256
  `775ad2376a7231b8929fa31880d52074dede507530f1b2edd55adeeef5364ed7`.
- Parsed the actual OTA with the validated parser; all container/component CRCs
  pass. Its extracted app tail equals the reviewed blob. Hook plus preserved
  store is `b7c73904938707eabcd8`; decoding the two instructions gives
  `a5 = 0x0439bea0`.
- Reassembled all 98 disassembled instruction bytes and matched them to both
  the flat binary and ELF `.text`; ELF `.rodata` also matches the blob. The
  embedded JSON is valid and identifies `runtime-probe`, ABI 1, H001Y-1.0.3.127,
  entry `0439bea0`, and zero writable static bytes.

## Actual control-flow and register witnesses

At `0x0439bea0`, the wrapper subtracts 32 from `sp`, saves `ra` at `sp+28`, and
stores incoming `a1` (request) at `sp+12`. It compares `a0` with `0x7e`.
For every other command, `0x0439beae..0x0439beb6` loads and calls the original
handler `0x042e4680`. Incoming `a0,a1,a2,a3` are unchanged at that call. The
wrapper then restores `ra` and `sp` and returns at `0x0439bebc`. This is a normal
nested call, not a tail call.

For ping, `0x0439bebe` saves `s0` at `sp+24`, then keeps the response-slot pointer
from `a3` in `s0`. When request is non-NULL, `0x0439becc` passes `sp+12` to the
stock list destructor `0x042eff8e`. This is the address of the local request
pointer, matching the stock destructor's contract. There is no subsequent reuse
or second free of that request.

`0x0439bed8..0x0439bee0` passes the linked JSON constant at `0x0439bf04` to
`0x042ef9f6`, which allocates/copies a type-5 response list. The returned list is
stored through `s0`. If allocation fails, the branch at `0x0439beee` calls
`0x042ef924(4, NULL)` and stores its result instead. Both ping exits restore `s0`,
`ra`, and `sp`. The sequence pointer is never dereferenced or modified by the
wrapper. The dispatcher subsequently sends and releases the response list, as
established in [the native contract](report.md).

No wrapper instruction changes `gp`, `tp`, `s1..s11`, or any FP register. The
only modified callee-saved register, `s0`, is saved/restored on exactly the ping
branch that uses it. The 32-byte frame maintains 16-byte stack alignment.
The compiler's stack-usage output agrees. The final ELF identifies ELF32 little
endian RISC-V, compressed instructions and single-float ABI; it has only
`.text`/`.rodata` allocated sections, no final relocations, and no undefined
symbols in the supplied build evidence.

The ELF program-header mapping starts before the entry because of ELF page
alignment; this is not the flashed representation. The verified flat blob begins
at the actual linked `.text` entry and is what the container appends.

## Remaining limitations

The forwarding path adds a 32-byte wrapper frame to stock handler stack use;
no live stack high-water measurement was available. Both response allocations
can fail, in which case the stored NULL causes no response; it does not create
an invalid response pointer. Changed image-size acceptance, executable access to
the appended region, and successful operation remain live-test questions. The
previous visual text-patch success does not resolve those questions.
