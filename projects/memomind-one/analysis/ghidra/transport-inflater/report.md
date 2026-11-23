# Streaming inflater discovery

Scope: read-only static stock firmware and SDK inspection, plus analysis-only
compilation/smoke tests of an already installed local source option. No device,
runtime, SDK source or Ghidra project edits. REA does not admit this raw RV32
image; the existing explicitly mapped standalone Ghidra project was opened with
`-readOnly -noanalysis` (logs retained).

## Finding

**No callable native RFC1950/zlib persistent inflater, reset or cleanup ABI was
identified.** Do not bind `runtime/portable/transport.c` to a guessed address.
The established native/public compression paths are raw LZ4 and LZMA; neither
implements the transport's persistent DEFLATE dictionary contract. This is a
bounded negative result, not proof that no other implementation exists in an
uninspected ROM/component or stripped/generated code.

## Firmware and SDK evidence

The scanned stock OTA is SHA-256
`08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`.
All six CRC-verified decompressed component bodies were searched: 3,747,714 bytes.
The application body is 1,773,176 bytes, SHA-256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, mapped at
`0x041eb020`. Per-body hashes, sizes and matching strings are in
`stock-string-search.json`.

Searches found no `inflate`, `zlib`, `adler`, `deflate` or `uncompress` identifiers
or standard error strings. Exact DEFLATE distance-base, length-base and dynamic
code-order sequences were checked as applicable 8/16/32-bit little-endian tables;
none matched any scanned body (`deflate-table-search.json`). These searches do
not cover alternative/computed/encoded tables. The Ghidra listing had no literal
65521 operand; split constant construction and other Adler implementations are
not excluded by that check. `zZip` in a non-code asset body is not a zlib API.

Public SDK checkout `171098bff25934a534a49f95b88df58fbed404c7` declares extension
ID 2 as **independent raw LZ4 block operations** in
`GlassSDK/include/gm_plugin_extensions.h:243` and `docs/ABI.md:75`.
No public persistent zlib service appears in its headers. The package builder's
Node `deflateRawSync` creates a phone-side ZIP package; this is not evidence for
a firmware inflater.

The captured firmware independently confirms the SDK table:

| Address | Evidence and interpretation |
| --- | --- |
| `0x0429a3a2` | Extension lookup; ID2 returns table `0x043661fc`. Existing export under `analysis/ghidra/display-adapter` resolves only IDs1–5. |
| `0x043661fc` | Three actual words: `0x04299c40`, `0x0429a402`, `0x04299c1e` (bound/compress/decompress). |
| `0x04299c40` | Tail wrapper to `0x042442c0`, SDK `int32_t compress_bound(int32_t size)`. |
| `0x04299c1e` | SDK `int32_t decompress_safe(src,dst,int32_t compressed_size,int32_t capacity)`; rejects null pointers/negative sizes, tail-jumps to `0x0424593a`. Four arguments, no state/context/reset/free. Assembly confirms argument preservation. |
| `0x0429a402` | Compressor wrapper is absent as a defined function in the existing Ghidra analysis, so raw RV32 objdump is retained instead. It uses plugin state at `gp+0x79c`, lazily allocates compressor workspace through `0x0433c320` with selector `0x10000`, then jumps to `0x04244330`. This is LZ4 compression workspace, not a zlib decoder context. |
| `0x042a4c2a` | Image LZMA unwrap: reads advertised output length at+4, five properties at+8, compressed bytes at+13; allocates output via `0x0434e6da`, calls `0x042383e0` with properties length5/finish-mode1/status and allocator table `0x02011418`; frees output on mismatch/error. |
| `0x042a5300` | Memory image loader accepts `ILZ4`, calls `0x0424593a(src+8,dst,packed_size,declared_output)`, requires exact output size; separately routes LZMA. Holds mutex `0x02011e54` via `0x0200ec3a`/`0x0200ecb2`, allocates/frees with generic heap wrappers. |
| `0x042383e0` | LZMA one-shot wrapper: local stack state, allocation/properties `0x042382e2`, init `0x04237d12`, decode `0x04237d34`, then cleanup `0x042381c2` with the supplied allocator. It does not retain state for a later record. |
| `0x042a4ae8` | Custom image byte run-length decoder: literal runs for controls0–127, repeated byte for negative controls except0x80. No Huffman/DEFLATE state. |
| `0x042a4f0e` | File image loader follows LZMA/custom image paths and explicitly rejects PNG (`0x0438311c` error string). It is not a usable PNG/zlib decoding shortcut. |
| `0x042ae264` | JBD image path also calls LZMA with explicit properties/status and checks decoded size. |

`string-references.txt`, `native/functions.json`, `native-core/functions.json`, matching `.c/.asm` exports,
`lz4-extension-table.json`, and `lz4-compress-wrapper.asm` retain exact call-site
and incoming-reference evidence. The decompiler sometimes omits preserved
register arguments at tail calls; wrapper signatures above use the SDK and
assembly, not an inferred `void` signature. No LZ4 or LZMA live call was executed.

There is therefore no native RFC1950 reset/end address to report. Reusing an OTA
LZMA context or the plugin LZ4 compressor workspace would change the algorithm,
ownership and task contract and does not satisfy G2 transport compatibility.

## Existing local source option

The verified local Ghidra12.2 distribution already includes zlib **1.3.1** at:

`.tools/ghidra/ghidra_12.2_PUBLIC/Ghidra/Features/Decompiler/src/decompile/zlib`

Its `README.txt` says the subset is copied unchanged except provenance comments.
The existing installation archive provenance is in
`analysis/evidence/ghidra-installation.json`. Per-file local SHA-256 hashes are
recorded in `zlib-rv32/report.json`; no dependency was downloaded in this task.
This version is a concrete available candidate, not a claim of latest version or
a completed security/production review.

Inflate-only candidate inputs are `inflate.c`, `inffast.c`, `inftrees.c`,
`adler32.c`, `zutil.c` plus `zlib.h`, `zconf.h`, `zutil.h`, `inflate.h`,
`inffast.h`, `inftrees.h`, `inffixed.h`. Compile with `Z_SOLO` and `NO_GZIP` to
require caller allocators and omit gzip/CRC dependencies. Default fixed decode
tables are read-only. Do not enable `BUILDFIXED`, which builds shared tables.

The zlib license is present at the top of `zlib.h` and in
`.tools/ghidra/ghidra_12.2_PUBLIC/licenses/zlib_License.txt`. It permits use and
redistribution with origin preserved, altered versions marked, and the notice
retained. A later vendoring step must retain those notices and source pins.

### Exact local C state/cleanup contract

- Initialize a stable `z_stream`, set `zalloc`, `zfree`, `opaque`, and call
  `inflateInit2_(stream,15,ZLIB_VERSION,sizeof(z_stream))` (the macro
  `inflateInit2` supplies the last two parameters). Positive15 selects RFC1950
  with the full32KiB history; negative15 would be raw DEFLATE and is unsuitable.
- Decode with `inflate(stream,Z_NO_FLUSH)`, retaining the same stream across
  successive SYNC_FLUSH records. Consume every input byte, bound output and
  require progress. The existing adapter rejects every result other than
  `Z_OK`, including `Z_STREAM_END`; finalized streams are not accepted.
- `inflateReset` clears `wsize`, `whave`, `wnext` and parser/checksum state while
  retaining allocated window storage. `inflateResetKeep` is not equivalent:
  it keeps history fields. `inflateReset2` additionally frees the window if its
  size changes. These are source ABIs, not native firmware addresses.
- `inflateEnd` frees the optional window and internal state with the stream's
  allocator, then nulls `stream->state`. The owner must separately free the
  `z_stream` object and clear the transport's opaque pointer. `inflateEnd` is
  valid after an ordinary failed decode, including window-allocation failure.
- The existing transport's RESET_CONTEXT/end path currently disposes the state;
  a source-backed adapter can preserve that exact behavior by end/free and fresh
  init. Do not silently substitute ResetKeep. Clear borrowed `next_in/next_out`
  and available counts before returning to the caller.

Analysis-only ASan/UBSan smoke testing compiled those local sources and reused
the existing `tests/transport/host_zlib.h` callback adapter. A 32,768-byte first
record produced a 32,785-byte SYNC_FLUSH wire record; a dependent4,096-byte second
record compressed to45 bytes. Two independent contexts decoded interleaved
records exactly. Fresh-context decoding of the dependent record failed, finished
streams failed, all three allocation failure positions cleaned up, borrowed
pointers cleared and zero allocations remained. Peak host allocations80,080B
reflect host structure sizes, not RV32 sizes. Commands, fixtures and outputs are
retained as `zlib-smoke-*` and `zlib-local-smoke.c`; this is a focused source
compatibility smoke test, not the entire G2 suite or device execution.

### RV32 size and capacity implications

Pinned xPack GCC15.2.0 compiled the unmodified subset with `rv32imafc/ilp32f`,
freestanding/no-builtins and function/data sections. Relocatable linked output
has no unresolved symbols or writable globals. It contains7,530 bytes of text
and3,309 bytes of rodata before unused-API garbage collection. Largest individual
function stack frame is128 bytes; cumulative adapter/native stack is additional.

| RV32 allocation | Bytes |
| --- | ---: |
| Caller `z_stream` | 56 |
| Internal `inflate_state` | 7,120 |
| Persistent maximum window | 32,768 |
| Total per logical origin | **39,944** |
| Both independent origins | **79,888** |

A lower message bound does not shrink the stream's32KiB history. Reducing
`windowBits` would reject ordinary larger-window zlib headers and lose parity.
With the current `transport.c` full-wire-record buffer plus `max_record+1` decoded
buffer, peak arithmetic is:

| Bound | One origin | Two retained origins, one synchronous decode |
| --- | ---: | ---: |
| 8,192 | 56,329B | 104,465B |
| 65,535 | 171,015B | 276,494B |

These exclude transport context, native receive/envelope/queue buffers, allocator
metadata, canvas, retained scene/asset store, timers and stack. They are not an
allocation admission guarantee. In particular, raising max message to65,535 and
store from64KiB cannot be justified by inflater availability alone. Incremental
wire consumption and explicit aggregate budget/lifetime design need separate
work; the current raw scene8192-byte admission remains in force.

## Task and allocator constraints

A prospective appended source adapter should use the already-reviewed ordinary
no-fit allocator `0x0433c294(size,0)` and matching owned free `0x020099a0`, with
checked multiplication for `items*size` and an explicit total budget. Those
functions are documented in `analysis/ghidra/display-adapter/report.md:416`.
The generic allocator `0x0434e6da`/`0x02009904` may invoke the stock OOM assertion
policy; it is not an appropriate recoverable-failure substitute.

Allocate/decode/end only under the transport's existing serialized ownership.
Do not inflate inside the native observer/interrupt callback or while holding an
additional interrupt-disabled/display critical section. Short allocator critical
sections do not justify a long decompression critical section. Source compilation
and host smoke tests do not establish native task timing, largest free block,
stack headroom, cross-core safety or safe persistence alongside the scene cache.

## Remaining proof boundary

A native inflater could still exist in unmapped ROM, differently encoded code or
other firmware variants. No callable native zlib ABI was established here.
The local source option needs a deliberate vendoring/build review, full original
transport suite against that source, actual RV32 execution tests, allocator OOM
and concurrent-origin lifecycle tests, and a native scheduling/memory budget
before firmware integration. Runtime and device state were unchanged.
