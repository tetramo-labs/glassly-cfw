# Porting G2 features to MemoMind's stock native plugin host

Inspected the official `memomind-open/plugin-open-platform` checkout at commit
`171098bff25934a534a49f95b88df58fbed404c7`, plus the existing `~/dev/g2flash`
source. This is a source/documentation assessment; no plugin was built, installed
or executed by this analysis. The main firmware/OTA reverse-engineering task
remains separate and incomplete.

Subsequent verification: direct Ghidra analysis recovered the read-only capability
handler, and an independent RFCOMM query on firmware1.0.3.127 returned package
format2, ABI256, display600×350 at30Hz, GRAY4, capabilities255, streamed/LZ4
installation and resume flags. See `evidence/native-plugin-caps-live.json` and
`ghidra/findings.md`. This confirms the host's advertised capabilities on the
actual glasses; no native plugin has been installed or executed by this work.

## What the official SDK establishes

The stock-plugin approach can host a new RV32 build of portable G2 feature
logic, with a documented graphics, messaging, input and allocation interface.
It cannot reuse the G2 Thumb binaries, fixed firmware addresses or native hook
patches. It also does not provide an official raw-flash or firmware-OTA Host
service. That preserves a real distinction between a custom application and a
replacement/patch of the glasses' system firmware.

The SDK matches the plugin strings recovered from the captured firmware: it
describes streamed LZ4 delivery, Flash XIP, bounded RAM and cached runtime
activation. The correspondence is evidence for a related implementation, not
proof that this exact SDK ABI and installation path are enabled in the current
production App/firmware pair.

## Exact compiler and entry contract

The actual example build uses:

```text
-march=rv32imafc -mabi=ilp32f -mcmodel=medany -mno-relax
-Os -ffunction-sections -fdata-sections -fvisibility=hidden
-fno-builtin -fno-common -fno-jump-tables
-fno-unwind-tables -fno-asynchronous-unwind-tables
-fno-stack-protector -nostdlib -std=gnu99
-fPIC -msmall-data-limit=0
```

The linker uses `elf32lriscv`, `--no-relax`, `--emit-relocs` and
`--gc-sections`. The precise compiler target is **RV32IMAFC with hard-float
ILP32F**, not the `rv32imac/ilp32` combination seen in some SDK tests.
Source: [CMakeLists.txt lines 27–50 and 105–109](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/build-host/tools/build/CMakeLists.txt#L27).

The SDK pins xPack `riscv-none-elf-gcc` **15.2.0-1**, with host-specific archive
SHA-256 checks. `GM_RISCV_TOOLCHAIN` can select an existing compiler directory;
otherwise the build installs its verified package into a per-user cache.
Source: [gm_build.py lines 26–51 and 121–147](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/build-host/tools/gm_build.py#L26).

Only `gm_plugin_entry` is exported. It receives a Host function-table pointer
and a Host-owned writable descriptor. The entry validates ABI, struct sizes,
required capabilities and function pointers, preserves descriptor capacity,
fills callbacks, and must not allocate resources. Current core ABI is `0x0100`.
The linker places entry at Flash-relative zero, Flash text/read-only data at
VMA zero and writable data/BSS at VMA `0x10000000`; package loading relocates
the latter through a slot/fixup scheme. These VMAs are plugin-link addresses,
not permission to access those physical addresses directly.
Sources: [gm_plugin.h lines 28–41 and 569–592](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/include/gm_plugin.h#L569),
[gm_plugin_xip.ld](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/build-host/tools/build/gm_plugin_xip.ld#L1).

Callbacks run serially on the display task and must not block or retain borrowed
event pointers. UI is created during `on_start`, not `on_load`. Only one plugin
is loaded at a time. Normal stop/replacement can end the application; this is
not an automatically persistent boot hook.

**Source inconsistency to resolve before implementing failure cleanup:**
`gm_plugin.h` lines 507–513 and 546–550 say failed `on_load` is followed by
`on_unload`; `docs/ABI.md` says the opposite. The repository declares the headers
canonical, but the real firmware behavior remains to be verified. Cleanup should
be idempotent and partial-state aware; do not double-free based on contradictory
prose. No SDK source was edited to conceal this discrepancy.

## Package, integrity and security

GMP v2 is a little-endian `GMPK` package. Its 120-byte header is described by
`<4sHH12I64s`: magic, format=2, ABI, total size, Flash size, initial-RAM size,
total static-RAM size, entry, slot/fixup/pointer counts, Flash offset, RAM offset,
CRC32, version, and a 64-byte name. Prefix relocation metadata is followed by
64-byte-aligned Flash code/constants and initial RAM bytes. BSS occupies runtime
RAM, not package bytes.

The packer validates ELF32 little-endian RISC-V executable format, separate
Flash/RAM loads, bounds/alignment, undefined symbols and supported relocations.
It serializes slot words, 8-byte fixups and 8-byte pointer records. CRC32 is at
offset 48 and is calculated over the canonical package with that field zero.
Source: [gmp_xip_pack.py lines 17–28, 44–169 and 172–198](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/build-host/tools/gmp_xip_pack.py#L172).

Limits: Flash code/constants at most **512,000 bytes**; static RAM below
**102,400 bytes**; at most 128 address slots and 4,096 fixups; package at most
**3 MiB minus 64 KiB**. The compiler launcher enforces per-function static stack
frames no larger than 1,024 bytes. This does not bound cumulative stack or
dynamic allocations. The display task has an 8 KiB shared stack.
Sources: [gm_plugin_xip.h lines 8–18](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/include/gm_plugin_xip.h#L8),
[ABI.md build/memory rules](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/docs/ABI.md).

The official security document explicitly says that the current native plugin
runtime has **no MPU isolation and no publisher-signature authentication**.
Whole-package CRC32 and canonical SHA-256 detect corruption/content differences;
they do not authenticate the publisher. The Host table is an ABI boundary rather
than a sandbox. These are SDK statements, not a completed audit of enforcement
in captured firmware 1.0.3.127. Source:
[SECURITY.md](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/docs/SECURITY.md).

Build outputs also include encrypted source-review sidecars. Their encryption
protects source confidentiality; it is not a GMP signature or proof of reviewer
approval. Only the GMP runs on the glasses, while the phone preserves the bundle.
Source: [REVIEW_PACKAGES.md lines 3–29 and 115–121](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/docs/REVIEW_PACKAGES.md#L3).

## Transport and practical developer access

Public application messages use Classic SPP service
`00007033-0000-1000-8000-00805f9b34fb` (iAP2 alternative
`ql.iap2.protocol02`), GM service `0x0f`, command `0x28` phone→plugin and
`0x29` plugin→phone. The messages carry a channel and opaque bytes. Delivery
acknowledgments and application replies are distinct; a G2 protocol adapter must
preserve its own request/response semantics above this transport. SPP UUIDs are
not BLE GATT characteristics. Source:
[PROTOCOL.md transports and application service](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/docs/PROTOCOL.md).

The public repository deliberately omits executable-package installation wire
transactions. Official installation is Studio→phone LAN bundle import, followed
by App-managed Bluetooth delivery/cache/start. This omission is a support
boundary, not proof of wire authentication or a substitute for the separate
requested OTA investigation.

The actual phone's Memo Lab did not expose Developer Workspace in the root
agent's observation. Official hardware setup says to obtain the **matching test
App and firmware from the toolkit provider** when that entry is absent; the
public SDK clone alone does not enable it. Source:
[official hardware setup](https://open-platform.memo-mind.com/docs/get-started/quickstart/hardware/?lang=en).

Installation additionally requires the signed-in developer account to own the
application. QR scans and manual IP:port imports use the same ownership and
authorization checks. A reachable LAN is insufficient, and the App has no local
ZIP picker. The precise process to grant this user's account developer access
was not established by the public material inspected. Source:
[official QR installation guide](https://open-platform.memo-mind.com/docs/get-started/quickstart/lan-install/?lang=en).

## G2 source reuse plan

| Existing G2 area | Stock-plugin adaptation | Work that remains firmware-specific |
|---|---|---|
| `vector.c`, `shapes.c`, scene/object logic | Recompile pure geometry/raster logic for RV32IMAFC; wrap the raster target around Host framebuffer slices | Replace dimensions, stride, pixel layout, synchronization and display-lifetime assumptions |
| `rle.c`, protobuf helpers, portable parsers | Reuse algorithm implementations after bounded-input tests and compiler warnings | Remove ARM assembly, unaligned-access assumptions and firmware dependencies if present |
| G2 message dispatch | Introduce a Host `on_event`/`bt_send` adapter; retain high-level command payload semantics where useful | G2 `aa21` envelope, BLE UUIDs, lens routing and bridge code do not transfer |
| `malloc.c`, context lifetime | Use tracked `host->alloc/free`; own state via descriptor context and lifecycle callbacks | Discard G2 heap addresses, TLSF introspection and absolute stock-function pointers |
| Keyboard/gesture handling | Map Host buttons, raw IMU and optional HOGP extension events into portable application actions | Re-derive thresholds and unavailable ring/compass/sensor capabilities; do not fake support |
| LVGL/text/UI | Use Host-provided LVGL API, fonts and events, or a pure per-pixel renderer | G2 native GUI pointers, patched text layout and stock scheduler hooks cannot be reused |
| Microphone/speaker features | Pair with authorized phone capture/native audio APIs where exposed | Raw microphone/speaker PCM, private audio hooks and always-on behavior are outside native plugin Host ABI |
| Flashing and boot modifications | Continue separate MemoMind OTA/container/backend development | Raw flash, firmware/font OTA, charging/power control, persistent boot hooks remain outside this plugin contract |

G2's `message_transport.c` lines 8–15 directly call Thumb-address firmware
functions and lines 58–72 embed lens/packet assumptions. None belongs in the
MemoMind plugin. Its useful high-level renderer/state machine needs a new
platform layer rather than copying those entrypoints.

For rendering, query `display_get_info`; do not turn Studio's 600×350 profile
into a fixed device constant. Direct framebuffer pixels are GRAY4, even x in
the high nibble. Lock/unlock Host-selected slices, keep LVGL calls outside the
lock, and yield drawing to phone-call UI while continuing message processing.
Sources: [GRAPHICS.md](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/docs/GRAPHICS.md),
[CAPABILITY_MATRIX.md lines 26–66](https://github.com/memomind-open/plugin-open-platform/blob/171098bff25934a534a49f95b88df58fbed404c7/GlassSDK/docs/CAPABILITY_MATRIX.md#L26).

A practical first port would be a separately named diagnostic renderer with a
phone-message echo, a small vector scene and bounded input handling. Build and
preview it, then install only after the matching App/account path is available
and verify stop/restart, reconnect, drawing and cleanup on hardware. This is a
useful custom-software milestone; it does not claim the requested system-patch
and independent-flasher goal is complete.
