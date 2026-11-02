# MemoMind native extension

The current installed runtime is the44,592-byte scene-004 build described in
[scene session](graphics/SCENE_SESSION.md) and
[hardware evidence](../analysis/scene-hardware-verification.json). The208-byte
probe below is a preserved earlier milestone, not the current device image.

The first executable extension is a fixed-profile diagnostic for H001Y firmware
1.0.3.127, based on the visually confirmed text-patched OTA. It uses208 bytes at
XIP `0x0439bea0`, preceded by eight alignment bytes, within the existing2MiB
application partition. No partition moves or writable static RAM are needed.

An eight-byte callback initializer is changed at `0x042e82e0`. `entry.S` compares
the command with `0x7e`: other commands tail-jump to the original service15 handler
with unchanged arguments, return address and stack. Only caller-saved `t0` is
modified. The diagnostic C path uses32 bytes of stack, frees the request TLV
list according to the stock ownership contract, and returns copied JSON through
the stock response builder. The dispatcher sends and frees that response.

The new request is GM service15/command126 with an empty body. Its reply is:

```json
{"glassly":"runtime-probe","abi":1,"profile":"H001Y-1.0.3.127","entry":"0439bea0","writableStaticBytes":0}
```

This is an executable-code milestone, not an implementation of G2 drawing or
other CFW features. The wider goal is recorded in
[G2 runtime port plan](../analysis/g2-runtime-port-plan.md).

## Build and reproduce

`scripts/compile_memomind_probe.py` uses the SDK-pinned xPack GCC15.2.0-1 under
`.tools/riscv-toolchain`, verified against archive SHA-256 recorded in
`analysis/evidence/riscv-toolchain.json`. It emits a real RV32IMAFC/ILP32F ELF,
raw binary, disassembly, map, section/relocation report and build hashes.
Linker assertions prohibit writable data/BSS, and compilation checks reject
undefined symbols and static stack frames larger than64 bytes.

Use new output directories:

```sh
python3 scripts/compile_memomind_probe.py /tmp/memomind-probe-build
python3 scripts/build_memomind_runtime.py \
  captures/firmware/ota-1.0.3.127-glassly-text.bin \
  /tmp/memomind-probe-build/probe.bin /tmp/memomind-probe-image
```

The fixed constructor verifies the exact source hash and original instructions,
appends the blob, updates lengths/metadata/checksums, replaces only the guarded
initializer, and generates a manifest that the live sender must reproduce
exactly. Historical probe candidate: `captures/firmware/runtime-probe-002/firmware.bin`,
SHA-256 `ae04bec4649b685bf2a73265aa468ff8431e76a1371d584f35349e7de071de78`.
Actual reviewed build: `runtime/build/probe-003`.

Evidence:

- [Native entry and ownership proof](../analysis/ghidra/append-hook/report.md)
- [Compiled binary review](../analysis/ghidra/append-hook/compiled-probe-003-review.md)
- [Independent container audit](../analysis/runtime-probe-002-container-audit.json)
- [Bounded append tooling](../analysis/append-container-tooling.md)

## Hardware verification

Before this image, the new command returned STATUS2 (invalid command), while
heartbeat and the native capability query succeeded. Baseline capture is under
`captures/runtime-probe-20261031/`.

Historical probe status: **flashed and verified, subsequently replaced by the scene runtime**. The sender transferred
all534 blocks/3,735 chunks from offset18; final validation and reboot succeeded.
After reboot, `scripts/probe_memomind_runtime.py` received the exact identity
reply16 times with empty requests and once with a valid nonempty TLV request.
A separate connection repeated two empty requests and one nonempty request.
The stock capability object remained identical to its pre-flash baseline and
both final heartbeat checks passed. The bridge was stopped, its forward removed,
and MemoMind reopened afterward.

`analysis/protocol/runtime-probe/whole-image-proof.json` independently reconstructs
the entire candidate from the HCI capture. Runtime test evidence is in
`captures/runtime-probe-20261031/runtime-test-01.json`, `runtime-reconnect.json`
and `hardware-verification.json`, with corresponding raw JSONL and HCI records.
This establishes this appended executable and callback hook on this image;
it does not claim a heap measurement, general recovery or full G2 parity.
