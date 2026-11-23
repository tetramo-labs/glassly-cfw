# MemoMind graphics runtime

This is the display-worker adapter for the existing G2 geometry port. The first
implementation accepts all255 original mode36 records, types1–13, on a600×350
packed GRAY4 canvas. Mode11 removes the current owned image. It does not yet
integrate retained scenes, paths, assets, RLE, fonts or input. Those remain part
of the full CFW parity goal; host-only ports are not advertised as device features.

The service15 gate retains stock commands and adds command0x7d for one BYTES TLV
containing the raw G2 message. Command0x7e returns identity and native free-memory
snapshots. The display gate recognizes only queueclass63/event0x474c and otherwise
tail-calls the original dispatcher. Both gates preserve ordinary stack/register
contracts and use the pinned two-hook construction profile.

Commands are validated before allocation. The Bluetooth handler copies the
event and message, releases the original TLVs, queues a synchronous copy, and
releases its temporary allocation. It returns no immediate success response.
The stock display queue can reject admission silently; that remains a client
timeout. The display worker validates again and sends a correlated JSON result
only after changing LVGL state. `presentation:"scheduled"` is not confirmation
that a panel physically refreshed. The stock worker still frees the envelope.

Rendering uses a native indexed4 image descriptor,16 opaque BGRA palette entries
and105,000 pixel bytes. A small owner allocation and a separate105,064-byte
palette/pixel allocation remain alive while LVGL borrows them. An owned DELETE
callback invalidates the descriptor, removes its timer and frees both allocations.
No writable global or guessed RAM slot is required. The callback address tags the
owned object; other objects' arbitrary user data is never dereferenced.

The1000ms lease refreshes on valid drawing/empty geometry. A20ms native timer
removes the image on expiry, launcher/overlay changes or active-screen changes.
Timer checks are cooperative and can be delayed if the worker stalls. Deleting
the parent also triggers cleanup. Explicit mode11 finds the current screen's
image; a hidden previous-screen image is reclaimed by its timer. This is not yet
a global multi-screen session registry or an atomic compositor exclusion rule.

Own allocations use the existing locked `try_alloc(size,0)` at0x0433c294, which
returns NULL on ordinary exhaustion. Generic free is compatible. Stock LVGL and
JSON/TLV allocation may still assert. The adapter requires64KiB reported free
headroom before metadata construction and again beyond pixel bytes before the
large allocation, which happens last. These snapshots are a conservative
admission policy, not a contiguous-block or concurrency guarantee. Free/low-water
diagnostics are observations, not leak proofs. Native evidence and source audit
are in `analysis/ghidra/display-adapter/`.

## Verification

```sh
python3 runtime/graphics/tests/run_tests.py --output /tmp/memo-graphics-host
python3 scripts/compile_memomind_graphics.py /tmp/memo-graphics-build
.tools/rv32-tests-venv/bin/python tests/rv32/graphics_gate_emulator_test.py \
  --build /tmp/memo-graphics-build --report /tmp/memo-graphics-gates.json
```

Host ASan/UBSan tests exercise actual adapter C with mocked native operations:
copied request lifetime, all255 geometry records, delayed completion, queue drops,
allocation failures,100 create/update/delete cycles, parent cleanup, expiry,
clock wrap and stock-UI yielding. Gate emulation executes the actual linked RV32
instructions and patched callsite; it mocks C entry bodies and does not replace
the host ownership tests or on-device verification.

The compiler rejects writable sections, unresolved imports, relocations, blobs
over64KiB and individual frames over512 bytes. That frame limit is not a total
stack proof. Native BT/display task allocations are4096/8192 bytes; complete
interrupt/callee headroom still needs measurement.

`scripts/probe_memomind_graphics.py` defaults to passive identity/stock checks.
Its explicit `--draw` mode sends the test pattern and exercises clear/expiry.
It records replies and heap snapshots without claiming visual confirmation.

## Hardware evidence, 2026-10-31

`captures/firmware/graphics-002/firmware.bin` contains the 7,808-byte compiled
`runtime/build/graphics-004/graphics.bin`. The OTA SHA-256 is
`72801c476329d650ec3847752344d12eb29154adca744f14ff8b0c464467630b`.
The capture reconstructs its entire 2,191,666 bytes: the 18-byte e2 header and
3,746 e5 chunks across 536 acknowledged blocks. The recording has one 1us
backwards timestamp after the OTA; the validator finding is retained unchanged.

Hardware checks passed four passive identity reads, three initial lifecycle
cycles, 62 renewals during a 30-second hold, 16 further lifecycle cycles, malformed
request rejection and all 255 records in one command. Native RFCOMM request
fragments require 642 payload bytes with correlated fragment ACKs; responses use
503. The earlier 503-byte request attempt was rejected without reboot and is
retained in the capture. Physical panel visibility remains unconfirmed.

See `analysis/graphics-hardware-verification.json`,
`analysis/protocol/graphics-runtime/whole-image-proof.json` and
`analysis/graphics-hci-timestamp-review.json`. The bridge was stopped, forwarding
removed, the MemoMind app restored and the capture collector finalized.


The optional `--scene-session` build now binds retained scenes, cache/assets,
vector animation and resource-backed native text. It has separate host, actual
RV32 and protocol suites; see [scene session](SCENE_SESSION.md). The default
build remains identical to graphics-004. Host/compile success alone does not
establish installation or visible display output.
