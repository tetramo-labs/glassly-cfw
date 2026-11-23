# App-tail arena and opt-in service hook: static proof

The existing partition has room for a small append-only, read-only extension.
The inspected application startup does not copy or clear that tail. A narrowly
scoped service-handler pointer hook can preserve every existing command and add
one diagnostic response. These are layout and calling-contract findings;
bootloader acceptance and execution of an extended image are not yet proven.
No firmware bytes or device state were changed by this investigation.

## Exact arena boundary

Machine-readable values, original byte guards and source hash:
[proof.json](proof.json). The stock segment-3 body is 1,773,176 (`0x1b0e78`) bytes,
SHA-256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.

| Region | Start | End, exclusive |
|---|---|---|
| Existing app flash allocation | physical `0x001eb000` | `0x003eb000` |
| Existing image header | physical `0x001eb000` | `0x001eb020` |
| Existing body | XIP `0x041eb020` | `0x0439be98` |
| Candidate 16-byte-aligned append arena | XIP `0x0439bea0` | `0x043eb000` |

The candidate requires eight padding bytes after the complete original body and
has 323,936 bytes of address space available. The first ping should consume only
its small linked code/constant size, not enlarge the image to fill this arena.
The corresponding first physical append address is `0x0039bea0`; it remains in
the same existing 2 MiB app allocation. This does not establish erased contents,
permission attributes, or acceptance of every byte in the unused area.

Startup at `0x041eb03e` sets `gp=0x02011688`; `0x041eb046` sets `sp=0x020ffe00`.
[0x041fb1ec](function-041fb1ec.asm) copies a fixed code range from XIP `0x041eb084`
to RAM `0x02000000..0x0200f8b4`, then fixed initialized data from XIP `0x04399fc8`
to RAM `0x0200f8b8..0x02011730`. The latter source ends at `0x0439be40`.
The final 88 original body bytes are zero and remain part of the preserved body.
Startup clears BSS `0x02011878..0x0205e128`. Appending code and constants does not
extend any of these fixed operations. Therefore the extension must not assume
new `.data`, `.bss`, constructor, TLS, or small-data initialization.

Image-header word 6 is `0x020fee00`. Its meaning is **unresolved**, and its
proximity to the initial stack is not sufficient to call it a stack/heap boundary.
Preserve it. Existing `0x020ffe00` references include crash-record storage, as
shown by [0x041fc3fa](tlv/function-041fc3fa.c); this is not free extension RAM.

## Image-size and verification boundary

The acquired bootloader/ROM coverage is still absent. No direct Ghidra reference
to the original body-end address was found in this project, and raw little-endian
u32 scans found no body occurrences of the original body length, header-inclusive
length, body-end address, or partition-end address. These negative scans cannot
exclude split immediates, indirect calculations or checks in other boot stages.

The previously inspected app OTA verifier `0x04341c08` validates container layout,
staging bounds and CRCs; it does not hard-code this segment's original body size.
An extended image still requires updated image body length/CRC, matching partition
metadata body size, LZMA unpacked/packed sizes, container boundaries and CRCs.
The 2 MiB partition allocation and following partition must remain unchanged.
The outer total must also fit the existing OTA staging allocation. Root owns the
container audit and build tools. Successful boot of the earlier same-size text
patch does not by itself prove the bootloader accepts a changed decompressed size.

## One pointer hook, exact instruction witnesses

Initializer `0x042e8114` installs the service-15 callback with:

```
042e82e0  lui  a5,0x42e4
042e82e4  addi a5,a5,0x680       # original handler 0x042e4680
042e82e8  c.sw a5,0x70(s1)      # preserve this store
```

The two 32-bit instructions occupy body offset `0x0fd2c0..0x0fd2c8` and have
original bytes `b7472e0493870768`; the following compressed store is `bcd8`.
Only the pointer-loading pair needs redirection. For the illustrative entry
`0x0439bea0`, rounded HI20 is `0x0439c` and signed LO12 is `-0x160`, encoding
`b7c73904938707ea`. Recompute these if the linked entry differs. This is evidence
for a possible patch, not an applied edit.

Dispatcher `0x042e70a4` indexes callbacks at `table + 0x34 + service*4`, yielding
`0x70` for service `0x0f`. At `0x042e73c2..0x042e73d0` the call is:

```
lw    a1,0(s3)        # parsed request TLV-list value
addi  a3,s0,-0x48     # address of response TLV-list slot, initialized NULL
addi  a2,s0,-0x4c     # address of sequence byte
mv    a0,s1           # command
c.jalr s5             # callback pointer
```

Thus the callback contract is `void handler(uint32_t command, void *request,
uint8_t *sequence, void **response)`. The callback return value is not used.
The dispatcher later sends any non-NULL response using the current connection,
service, command and sequence, frees the response list at `0x042e7362`, and clears
the caller's request slot at `0x042e736e`.

## Minimal diagnostic command and ownership

Candidate command **service `0x0f`, command `0x7e`, empty payload** is outside all
stock handler cases and outside the dispatcher's special `0x30/0x31` diversion.
The admission helper `0x041fa9cc` returns 1 without installer-state changes for
this command: only `0x21..0x24` and `0x2b..0x2e` take its stateful path.
Generic GM framing/checksum/TLV parsing still applies.

[0x042ef9f6](function-042ef9f6.c) creates a type-5 text response from a nonempty
NUL-terminated string. Its underlying [0x042efe44](tlv/function-042efe44.c)
allocates the list node plus payload, copies the text, and adds a terminator.
Consequently a linked constant JSON string may be used directly; the dispatcher
owns the returned allocated list after the callback returns. Existing caps uses
this exact helper at `0x042e4866` before freeing its temporary source buffer.

[0x042eff8e](function-042eff8e.c) takes a pointer to a list pointer, frees its
nodes, and zeros that pointer. The stock handler owns nonempty request lists:
its unsupported-command path at `0x042e46ca` disposes the request then constructs
status 2 via [0x042ef924](function-042ef924.c). Never free a request before
forwarding it to the original handler, and never return a static string as the
response-list pointer.

A minimal wrapper can accept only an empty ping, avoiding any new parser:

```c
// Illustrative contract, not a compiled or installed patch.
void hook(uint32_t cmd, void *request, uint8_t *seq, void **response) {
    if (cmd != 0x7e || request != NULL) {
        stock_handler(cmd, request, seq, response); // 0x042e4680
        return;
    }
    *response = stock_text_response("{\"glassly\":\"ping\",\"version\":1}");
    // stock_text_response = 0x042ef9f6; leave *seq unchanged.
}
```

The empty request owns no list allocation. A nonempty command-0x7e request falls
through to the original unsupported-command path, which consumes it safely.
Allocation failure may leave the response NULL, matching the stock helper's
existing behavior; it must not be treated as a successful received ping.

Use the target RV32IMAFC/ilp32f integer calling convention. Preserve `gp`, `tp`,
callee-saved integer registers, and any callee-saved FP registers actually used;
keep `sp` 16-byte aligned at calls. The original handler demonstrates saving
`ra,s0,s1,s2,s3` in a 96-byte frame and restoring them before return. A true tail
forward may clobber caller-saved temporaries but must retain all four arguments
and the caller's return address. For the first extension, avoid floating point,
new writable globals, dynamic relocations, runtime/libc imports and generated
startup. Disable small-data assumptions and linker relaxation that could create
new `gp`-relative accesses; audit the final disassembly, not just compiler flags.

The next proof is an independently validated build that boots and returns the
new opt-in response while stock capability and device-info commands still work.
This report establishes neither a broad patch framework nor a recovery guarantee.
