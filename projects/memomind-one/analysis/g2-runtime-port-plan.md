# G2 runtime → MemoMind: probe first, bounded drawing next

The first useful port is an **opt-in firmware command that returns a fixed build
identity**, followed by a small geometry renderer on the display task. Importing
the whole G2 runtime would bring two heaps, full-screen storage, transaction
snapshots, compression, timers, lens routing and many G2 firmware addresses into
an unmeasured MemoMind RAM environment. The text patch has now been visually
confirmed by the user; it establishes that the selected modified application
boots and displays changed text, not that new executable hooks or heap ownership
have been validated.

This is a read-only source assessment of `/Users/fosse/dev/g2flash`, clean commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. The G2 checkout, live device, flasher,
transport and shared Ghidra project were not changed. Exact inspected-file hashes,
source sizes, compiler identity and measured RV32 layouts are preserved in
[g2-port-evidence/source-and-layout.json](g2-port-evidence/source-and-layout.json).
Source byte counts are **not** estimates of compiled flash usage.

## 1. Concrete first executable hook

The parent investigation is constructing a fixed-profile wrapper for normal
RFCOMM service `0x0f`, **command `0x7e`**. The selected initializer change is the
8-byte a5 LUI/ADDI pair at `0x042e82e0`; the appended wrapper begins at the
16-byte-aligned application address `0x0439bea0`. These are parent-derived
MemoMind profile addresses, not G2 addresses. The wrapper returns one immutable
JSON reply for the explicit probe and forwards every other command to the
original service handler. No startup allocation, display takeover, installation
operation or background task is needed.

The existing native evidence supports this shape:

- `analysis/ghidra/dispatch/function-042e8114.c` installs the service handler;
  `service/function-042e70a4.c` dispatches through the service table and sends,
  then frees, the returned response list.
- `admission/function-041fa9cc.c` admits commands outside the installer ranges;
  `0x7e` is outside those ranges and the dispatcher's special `0x30/0x31` path.
- The original service handler `0x042e4680` and response builders `0x042ef9f6`,
  `0x042ef924`, `0x042efe44`, `0x042eff8e` provide the ownership pattern to follow.
  Assembly must settle argument registers where decompiler prototypes omit them.

Keep the reply a capability/identity **probe**, not an assertion that drawing,
free RAM, recovery or G2 protocol support already exists. Prefer no private
persistent RAM and no writable global data in this first blob; use stock reply
construction with its established caller-owned cleanup. Bound any accepted
request shape, preserve register/stack/`gp` behavior, audit every outgoing call
and relocation, and retain exact displaced instructions in the manifest. A
response allocation failure should yield the stock failure behavior, never a
reboot or allocation retry loop.

Acceptance: offline instruction/append/container checks; unchanged handler
behavior for existing commands; probe response correlated over UUID7033;
repeated query without accumulating memory; reconnect and stock UI still work.
A missing reply is an ambiguous probe failure, not a reason to enter the private
plugin installer or send arbitrary memory operations. The next firmware should
still do nothing custom until this command is explicitly sent.

## 2. What G2 code can actually be reused

All paths below are within the pinned G2 checkout. Its
`patches/patches_main.c:23–46` includes the entire feature set into one translation
unit. That aggregation is not a suitable MemoMind port boundary.

| Source | Portable part | Dependency to replace or defer |
|---|---|---|
| `patches/draw.c:115–196`, `draw.h` | Clipped packed-GRAY4 pixels, 6×12 ASCII glyphs, overlapping rectangle copy | Make string length bounded; pass actual stride rather than assuming tight packing. The font is 95×12 = 1,140 read-only bytes. |
| `patches/shapes.c`, `shapes.h` | Integer rasterizer; geometry types 1–13, 20-byte LE records; signed/clipped coordinates | Extract the geometry subset from context/texture/cache includes. Asset and built-in font types 14–17 need separate adapters. |
| `patches/vector.c`, `vector.h` | Checked compiled contours, winding/even-odd fill, transform/rotation math | Workspace, compiled-edge ownership and display scheduling; paths are retained-only in current G2 protocol, not immediate mode36. |
| `patches/rle.c`, `rle.h` | Incremental run decoder with output bounds | Caller validates complete input/output before visible mutation; strip/rectangle ownership and full-frame semantics must be supplied. |
| `patches/utils.c` | Byte-wise LE reads, bounded string utilities | Audit edge cases and freestanding compiler runtime calls; do not depend on stock G2 symbols. |
| `patches/texture_cache.c` | Region-bounded RLE images and cached bitmap-font representation | Stock 20px font wrappers at lines23–54 contain absolute Thumb functions/private LVGL layouts. Mode15 is not portable text as-is. |
| `patches/message_transport.c/.h` | Ideas: bounded records, ordinals, CRC, application reply distinct from delivery ACK | Replace SIDf0 `aa` packets, dual ingress lenses, peer bridge, stock BLE callbacks and inflater. Use MemoMind GM/RFCOMM. |
| `patches/scene.c/.h` | Versioned IDs, validation, explicit SHOW/HIDE, eviction and transaction semantics | Large descriptor/undo/store allocations, timers, locks, text/asset adapters and replies. Port after memory ownership is measured. |
| `patches/cfw_context.c/.h`, `malloc.c/.h` | Lazy initialization and allocation-failure reporting as design patterns | Replace the singleton slot, whole context, two heap coordinators and TLSF introspection. None is a MemoMind allocator ABI. |

G2 primitives and MemoMind SDK GRAY4 both use even x in the high nibble, which
makes the pixel algorithms promising. The live capability query reports one
logical 600×350 display at30Hz. It does not prove the live framebuffer address,
stride, permitted draw task or synchronization API. The stock native-plugin
interface describes synchronized framebuffer slices; those semantics are useful
reference material, not proof that a raw firmware hook can call the same entries
without the host lifecycle.

Source limits: `shapes.c:22–28` clamps coordinates to -1024..1023, dimensions to
2047, with up to8 polygon vertices,16 Bézier segments and72 arc segments.
`vector.h:6–9` limits one path to512 edges,8192 command bytes and1024 commands,
with4096 active-scene edges. `vector.c:33–50` recursively subdivides curves to at
most8 levels; measure cumulative RV32 stack before enabling it. It avoids a
64-bit division helper explicitly, but every RV32 object still needs an undefined
symbol/relocation audit. Vector input is compiled M/L/Q/C/Z geometry, not SVG XML;
`demos/vector-protocol.ts` is the reusable phone-side compiler.

## 3. Measured memory costs and proposed budgets

The checked-in measurement source includes unchanged G2 headers and emits LLVM
constants for RV32IMAFC/ILP32F. Reproduce from this repository:

```sh
clang --target=riscv32-unknown-elf -march=rv32imafc -mabi=ilp32f \
  -ffreestanding -I /Users/fosse/dev/g2flash/patches -S -emit-llvm \
  analysis/g2-port-evidence/measure_layout.c \
  -o analysis/g2-port-evidence/layout-rv32.ll
```

This compiles type layout only; it neither builds executable firmware nor calls
G2 functions. It measures pointer/alignment costs on RV32 rather than incorrectly
using 64-bit host `sizeof` results.

| Allocation/type | RV32 bytes | Evidence/qualification |
|---|---:|---|
| Full MemoMind tightly packed GRAY4 shadow | 105,000 | 600×350÷2; actual stride can make this larger |
| Full G2 shadow | 153,600 | `image_buffers.c:3`, 640×480÷2 |
| Full `customCfwContext` | 2,772 | Includes unrelated peripherals and two message streams; do not import wholesale |
| One `cfw_message_stream` | 304 | Buffer/inflater allocations are additional |
| `cfw_cache` | 43,416 | 256 objects +256 assets +bitmap/journal/staging; includes `cfw_txn`1,636B |
| One object / asset | 116 /32 | `scene.h`; pointer-independent wire IDs still use local descriptors |
| Undo base | 45,464 | Full cache snapshot plus2048-byte bitmap, `scene.c:352–355` |
| Undo saved granule | 20 | 4-byte offset +16 old bytes;64 saved granules add1,280B |
| Asset store | 65,536..262,144 | Tries256/192/128/96/64KiB in `scene.c:260`; not a fixed mandatory256KiB |
| Vector workspace | 10,752 | 512×16-byte edges +512×4-byte x +512 winds |
| Compiled path | 4 +16×edges | Maximum8,196B per path, allocated within asset store |
| Dirty rectangle list | 136 | 16 rectangles; no pixel storage |
| One G2 message buffer | Up to65,535 | `message_transport.h:15`, allocation at `message_transport.c:271` |
| Inflated output | 65,536 extra | `message_transport.c:199`; zlib state/window extra and target-dependent |

For illustration, a600×350 shadow, unchanged context/cache, undo base with64
saved granules, minimum64KiB asset store and vector workspace already total
**274,220B (267.8KiB)**. One maximum uncompressed input record raises that to
**339,755B**. With256KiB store the same totals are470,828B /536,363B. These are
illustrative configurations, **not peak bounds**: undo capacity may grow to16,384
granules (+327,680B), compressed records add a decoded buffer and zlib state,
two ingress streams can coexist, and allocator/task/display overhead is extra.
G2's two stock heap arenas cannot be assumed to exist on MemoMind.

Proposed incremental caps, subject to measuring actual owned memory:

| Milestone | Proposed additional RAM cap | Included / excluded |
|---|---:|---|
| Fixed reply probe | 0 private persistent bytes; aim ≤256B stack | Immutable reply in appended flash; stock response allocation is still real but must follow existing ownership |
| One fixed display marker | ≤1KiB own state/command/stack scratch | No shadow/cache; only after proving display-task and buffer ownership |
| Geometry command renderer | 12KiB envelope | 4096B command +4800B optional600×16 strip +512B state +256B reply +136B dirty list =9800B, remainder for bounded scratch; font is flash |
| Full raster compatibility | ≥113,192B before platform overhead | 105,000B shadow +8KiB command/state envelope; needs measured contiguous allocation and lifetime |
| Retained vectors/animation | Budget after profiling, not first release | Descriptor/undo/store costs above; smaller limits must be advertised as a new profile |

Zero-copy drawing into a synchronized stock slice can remove the4800B strip,
but only if its ownership is proven. A whole-frame GRAY4 rewrite at30Hz moves
3,150,000 pixel bytes/s; an extra shadow-to-display copy adds at least6,300,000B/s
of read+write memory traffic. These arithmetic rates are not measured sustainable
SPI/RFCOMM throughput. RAM-free totals, largest contiguous block, task-stack high
water and display contention remain unknown. Plugin static-RAM/package limits
are not the available firmware heap and must not be used as a free-space budget.

## 4. Smallest useful transport + display port

Keep the proven UUID7033 GM framing, logical reassembly and command correlation.
Do not place G2 SIDf0 or lens-routing packets directly on MemoMind RFCOMM. Extend
the new opt-in service hook only after the probe is proven. Allocate selectors
explicitly and version the extension; `0x7e` remains its identity probe. Use one
bounded command in flight, a maximum4096-byte drawing request and a small explicit
status reply. Advertise unsupported modes; do not report G2 parity prematurely.

Separate four adapters: message receive/reply, allocator/lifetime, display
queue/present, and monotonic tick/lease. The receive callback validates and copies
bounded data, then posts a command to the proven display task. It must not render
or wait on a display lock from the Bluetooth dispatch thread. The display worker
owns the command until completion, returns status, and releases it exactly once.
No caller-controlled pointers or arbitrary memory access are needed.

First rendering commands should be clear/a fixed test pattern, and the pure
geometry subset of **mode36 types1–13**. Validate the whole record list before
mutating pixels. At20 bytes/shape, a4096B budget holds at most204 geometric records
including mode/count; initially cap this lower (e.g.32) to bound render time and
measure latency. Drawing clipped to a host-selected slice needs a real raster
origin/clip adapter: shifting a framebuffer pointer outside its object is not a
valid substitute for offset-aware clipping. Audit `cfw_raster_clear`, which uses
word stores and assumes aligned, word-sized storage.

The marker/geometry session is opt-in and short-lived. A new MemoMind-specific
lease should restore stock ownership when it expires, disconnects or is released;
copy the fail-open policy from G2, not its timer addresses. Start with explicit
single presentations and low measured cadence, then consider bounded animation.
Measure scheduler and interrupt stack depth before timers or vector recursion.

| G2 mode | MemoMind order / constraint |
|---|---|
| 7 diagnostics,11 cleanup | Reimplement a small target-specific equivalent early; no G2 peripheral cleanup calls |
| 36 geometry1–13 | First portable renderer after fixed marker; no retained cache or stock font requirement |
| 9 rectangle copy | Later, once persistent framebuffer/shadow semantics are established; source/destination must be owned and bounded |
| 3 deltas,6 full RLE frame | After shadow allocation or a defined tile protocol; a worst-case full210,000-pixel RLE stream exceeds even G2's65,535-byte record limit |
| 8 bundles | After whole-batch validation/staging; G2 presents once but a later invalid submessage can leave earlier shadow mutations, so do not claim rollback atomicity |
| 15 stock text /17 inline shape text | Replace G2 private font ABI, or use separately versioned6×12 ASCII first; not drop-in G2 text metrics |
| 19/20 cached images/fonts | After bounded asset storage; cached font table itself is384B plus glyph assets |
| 37–41 cache/paths/rotation | Last display milestone: state/replies, rollback budget, eviction and display-thread timing all required |
| 5 buzzer,10 compass,16 ALS,17 ring battery; keyboard/mic/ANCS | Separate hardware investigations; not part of first display/runtime port |

## 5. Excluded ARM and fixed-address assumptions

`patches/build.py:134` targets Thumbv7E-M and resolves ARM relocation families;
`cfw_context.h` has a Thumb PC-relative function-address assembly macro. Neither
is a RISC-V builder/trampoline. `debug.c:17–20` accesses ARM DWT/CoreSight MMIO
at0xe000xxxx; replace timing with a verified MemoMind API. The new wrapper must use
the actual MemoMind ISA/calling convention, including stock `gp`, stack alignment
and any `tp` assumptions. Header sizing with ILP32F does not prove the ABI of every
stock function.

Reject all G2 absolute firmware/RAM imports, particularly:

- `malloc.h`: `0x0045855f`, `0x004585a3`, heap descriptor`0x20000358`, heap13
  arena`0x2013519c`/size`0xcd000` and EvenHub arena`0x2020219c`/size`0x70800`.
- `cfw_context.h:331`: singleton`0x2029f59c` and diagnostic`0x2029f5a0`;
  `cfw_context.c:4–5` assumes pointers in the G2 `0x20000000` RAM region.
- `message_transport.c:8–14`: original BLE receive/send, lens identity and
  inter-temple bridge; `transport_compression.c:21–23`: stock zlib functions.
- `zlib_glue.c:196–226`: framebuffer`0x200008b8`, display semaphore/queue/copy,
  timers, buzzer and compass functions. `texture_cache.c:33–53`: G2 font functions,
  font root and private glyph layouts.

`memory.c` is C with Clang-specific inline-copy/no-builtin constructs, rather than
an assembly blob; it may be portable after RV32 codegen and alignment testing.
Do not import the G2 TLSF metadata walker merely to discover free RAM. RAM must be
identified through the new target's allocator/task ownership, not guessed from
zero-filled BSS or flash padding. Appended flash capacity and OTA staging capacity
are separate limits from runtime RAM.

## 6. Deliverable order and validation

1. Finish the fixed `0x0f/0x7e` probe wrapper and narrowly verified runtime-image
   manifest; no unrelated hooks. Confirm identity reply and stock forwarding.
2. Derive display queue/framebuffer ownership, allocator pair, task context and
   cleanup from MemoMind code. Record exact byte witnesses and source hashes in
   a versioned platform profile. Do not adopt the private plugin installer.
3. Build a standalone host geometry adapter at600×350 with stride/clip variations.
   Adapt G2 `patches/host/shapes_host_test.c`, `vector_host_test.c`, and transport
   malformed-input fixtures into this repository; do not run the aggregate G2
   test script that invokes its build/TypeScript outputs inside its checkout.
4. Run bounded pixel golden tests for every initial primitive, odd/even nibble
   boundaries, offscreen coordinates, truncation and invalid trailing records.
   Cross-compile and inspect undefined symbols, relocations, stack frames and
   actual code size; source line counts are not an instruction-size budget.
5. Add the fixed marker, then geometry requests with lease expiry and measured
   latency/heap lifetime. Keep cached assets, compression, paths and animation
   out until each resource bound is demonstrated.

The first target is an independently queried runtime hook plus a small visible
geometry scene, with stock Bluetooth/update/UI behavior intact. That makes later
G2 drawing semantics testable without committing to the full G2 memory model.
