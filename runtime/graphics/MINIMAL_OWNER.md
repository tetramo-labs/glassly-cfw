# Minimal launcher and native flash scenes

The `--minimal-launcher --flash-scene` profile advertises `GLASSLYCFW/1`, a
256 KiB logical asset store and 65,535-byte raw commands. Construction alone is
not installation or hardware proof. The selected candidate and validation are
recorded in `analysis/minimal-owner-flash-20261102`.

The launcher keeps its descriptor identity and the shared active LVGL screen.
Initialization restores the stock zero background on that screen through
`042c8fe2(screen,0,0)`, the call previously made by `042a5f24`. This also covers
the exposed screen after a frame is released or expires, without allocating a
replacement dashboard. The setter's actual RV32 wrapper is covered by the
native-caller test; physical background appearance still requires hardware.
Its five callbacks replace dashboard construction, listeners, timers and message
handling. Destroy releases the CFW graphics, input and diagnostic owners without
deleting the shared screen. Incoming app payloads remain borrowed. The original
go-home entry forwards only the welcome continuation; the calibration suspend
entry no longer operates on removed dashboard objects. Native zero-state flag
getters remain intact. This is a cold-boot replacement; no old launcher code or
static RAM is reused.

The display task remains the sole owner of scene metadata, timers, native font
calls and pixels. A persistent ordinary worker owns the native flash adapter.
Two one-slot queues implement synchronous I/O: the display task lends a buffer
until the worker returns its status. The native constructor is
`0200ee6a(owner, depth, itemBytes)`: owner `0xe6`, depth one, and 16/4 bytes
for request/completion. Its actual RV32 wrapper is tested independently of the
queue mock, including failed task creation and queue cleanup. The worker never accesses LVGL or the
scene. No IRQ critical section covers a queue operation or driver call. A stalled
native operation remains in flight; host timeout does not cancel it or free its
buffer. This initial design pauses display processing during flash I/O. It does
not establish animation throughput or uninterrupted presentation.

A separate registry at offset64 in the existing boot-zeroed256-byte carve keeps
the worker alive independently of screen/lease deletion. Admission claims the
canary registry too, preventing concurrent diagnostic writes to the same pool.
One worker persists per boot, including an initialization failure; there is no
retrying task creation or live task/queue deletion. The current native task and
queue constructors retain the firmware's generic OOM policy. Checked heap
headroom is not a proof of a contiguous native stack allocation.

The worker acquires the real native badmap; absent status7 and a validated
present record have distinct provenance. The original bounded native callbacks
still restrict access to device1 `[0x700000,0x800000)`. The COW core uses this
1 MiB physical pool for 256 KiB logical assets with transaction overhead and bad
sectors accounted separately. A reboot or new scene begins an empty logical
map; this is not a persistent filesystem. The six existing plugin-owner gates
remain installed. No native badmap is forged or rewritten.

The image is hidden and its source detached on the display task before scene
execution. Flash/render failure leaves it detached; invalid pixels are never
presented. Successful operations and timer callbacks reattach a valid raster.
The worker cannot race a display reader because it never renders into that
raster. Native fonts also stay on their established display task.

## Raw large-message carrier

Service15/command0x7d still accepts at most8192 bytes per native request. A
private carrier uses mode127 and at most1032 bytes per packet:

| Operation | Bytes after mode127 |
| --- | --- |
| Begin | `0, token:LE32, total:LE16` |
| Chunk | `1, token:LE32, offset:LE16, data:1..1024` |
| Commit | `2, token:LE32, CRC32:LE32` |
| Abort | `3, token:LE32` |

Tokens are nonzero. Length is1..65535. Chunks must be contiguous; exact duplicate
chunks are idempotent, gaps and conflicting duplicates fail. Commit verifies
IEEE CRC32 across the complete command and consumes the token before executing
it through the existing parser. It cannot execute again after an ambiguous
reply. Nested carriers are refused. Other mutating commands are refused while
assembly is incomplete; heartbeat and cleanup remain available. Lease expiry,
launcher destruction or explicit cleanup frees the incomplete record. The new
profile's lease is30 seconds; completed large commands use the ordinary scene
reply and settled notifications. Accepted chunks do not mean command execution.

The assembler allocates one at-most65535-byte RAM buffer. Moving the64KiB asset
store out of RAM makes room for it; core allocations retain the170KiB budget and
48KiB headroom. The RV32 model also reserves9KiB for worker/queues against the
previous353656-byte idle sample. These are admission/model results, not new
hardware RAM measurements. Two compressed transport histories and flash-spooled
command readers remain separate work; raw-command capacity does not claim them.

Swift `LargeMessage` creates packets and `GMSession.sendLargeGraphicsMessage`
checks advertised capabilities, waits for every chunk acknowledgment and returns
the real commit reply. It performs no automatic mutation retries. Raster and
bundle builders accept an explicit `maximumCommandBytes: 65535`; their historical
default remains8192 so the retained tests and old admitted profiles remain exact.

## Validation

The optional `--wake-control` profile adds GM service15/command`0x79`. Its
BYTES payload is `FC,1,op,nonce:LE16`: query0, wake acquire1/release2,
claim3/ready4, frame acquire5/release6. Wake and frame leases each last90 seconds;
frame renewal preserves the scene, while fresh acquisition, release and expiry
discard it. Incomplete message assembly still expires after30 seconds without
graphics traffic. Mode11 and launcher destruction release both owners.

Cooked double-press requests a wake with a400ms fallback. CLAIM extends it to5s;
matching READY completes it. A repeated double-press or timeout clears the
custom frame and returns to the blank minimal owner. Single press, long press
and release emit events2/3/4 while the wake lease is active. Native power-button
routing remains intact. The existing passive observer remains available.

Replies use JSON `glassly:"ownership",abi:1,result:"ok",stateHex`. The nine
snapshot bytes are wake lease, frame lease, pending, nonceLE16, screen on,
native power block, frame presented since acquisition, and event. Boolean
fields are0/1. Unsolicited messages have GM event0, result`event`, and event1–4;
event1 carries the pending nonce. Ordinary replies have event byte0. Query and
notifications do not renew leases. The frame-presented bit records presentation
through the raster path, not physical visibility.

Frame acquisition and a pending button wake call the reviewed native SDK wake
path at`042a88a8`; screen-state and power-block getters are`0425f99e` and
`0425f9f8`. They retain native guards and driver scheduling. The adapter does
not modify native power globals or promise to override a hardware power block.
All owner operations run on the display task using the existing queue and
hidden-child lifetime conventions.

`runtime/graphics/tests/run_minimal_owner_flash_tests.py` rebuilds the runtime and
candidate, runs sanitizer tests for the carrier and threaded broker, and executes
actual RV32 scene/COW/lifecycle code plus patched stock manager/calibration
callers. The threaded test writes/reads all262144 logical bytes, tests65535-byte
operations and rollback faults. RV32 tests upload a full-size asset through the
bounded carrier, read it back, inject storage failure, expire incomplete records
and tear down the launcher. Stock callers execute with poisoned old object
pointers. Physical hardware, scheduler timing and flash wear are not emulated.
The separate retained-command suite checks raster/copy/text/bundle/animation and
diagnostic teardown on the same runtime. The original portable fixture and
transaction-failure suites remain required. Full applicable G2 parity is not
claimed by this profile.
Pass `--wake-control` to include the ownership state tests, actual RV32 lifecycle
and all retained gate cases, native wake ABI checks, and retained command tests.
