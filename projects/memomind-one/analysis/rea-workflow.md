# MemoMind OTA: REA analysis workflow

Prepared from the local `~/dev/rea` checkout (package version 6.8.0) on
2026-10-30. The commands below are a workflow; see the executed status here for
what has actually run.

## Executed status, 2026-10-30

The primary session completed `npm ci` and `npm run build:cached`. A portable
Node 24.22.1 runtime under `.tools/rea-runtime` was verified against the official
Node SHA-256 list; the official JADX MCP 0.7.1 JAR under `.tools/rea-jadx` was
verified against REA's pinned hash. `sh scripts/rea-local.sh ...` selects these
without global changes. The existing Homebrew JDK21 is available.

REA `inspect-artifact` succeeded on the captured base APK and ARM64 split.
`analysis/evidence/rea-base-apk.json` and `rea-arm64-apk.json` are full Evidence
bundles; adjacent `*-summary.json` files retain the returned summaries. Their
member counts, excluding the root occurrence, are 2,562 and 46. The selected
member list in `rea-selected-apk-members.json` derives from these records and
links their Evidence IDs. This proves archive inventory only, not app behavior.

JADX initially encountered a sandbox failure compiling its macOS process helper.
After permissions changed, the primary session completed the provider check and
REA `inspect-android-package`; the retained record is
`analysis/evidence/rea-android-package.json`, Evidence ID
`ev_5036250eaf36da52ea917942ca09abe1d7f11af84791ca50b7c6953aceaccb13`.
The exact Evidence ID should be taken from that JSON record. Plain JADX also
recovered the relevant Java RFCOMM connection implementation; its full decompile
ended with 212 errors, so that output is incomplete. Ghidra was initially absent
from the checked locations.
Official Ghidra 12.2 is now extracted under `.tools/ghidra/ghidra_12.2_PUBLIC`,
with its archive verified against the upstream release SHA-256. The included
C++ decompiler source was built for macOS arm64 and installed inside that local
tree. `sh scripts/ghidra-local.sh` successfully prints headless usage and stores
its settings/cache under `.tools/ghidra`. Installation/build provenance is in
`analysis/evidence/ghidra-installation.json`; no global settings changed.

The captured WuQi app body is inferred RV32C, with a header/partition-derived
load address. **REA 6.8.0 does not admit raw RISC-V**, and its RISC-V ELF lane
requires an actual little-endian ET_EXEC ELF declaring double-float ABI. Do not
fabricate ELF declarations to route the raw image through that lane. Standalone
Ghidra's explicit raw loader is the appropriate fallback, with separately
labeled evidence and the source-derived mapping kept explicit.

## Prerequisites and boundaries at initial inspection

- The connected phone observed by the primary investigation is a rooted Pixel
  9 Pro, serial `47011FDAP0083R`, with `com.memomind.ai.aphrodite` 1.3.81.
- REA has no built runtime or installed dependencies in the observed checkout.
  Its launcher is `scripts/rea.mjs`; `dist/` is required. Its `.nvmrc` selects
  Node 24.22.1 and `package.json` selects npm 11.16.0.
- Existing Homebrew JADX is not the REA JADX provider: REA requires a supplied
  headless JADX MCP 0.7.1 JAR and a full Java 17+ JDK.
- Firmware region inspection/extraction is Linux-only in
  `src/firmware/FirmwareCommand.ts`. It needs Binwalk 3.1.x / Unblob 26.6.x,
  respectively, and util-linux `prlimit`. Do not expect these operations to
  run on this macOS host.
- REA packet field inspection is also Linux-only. Its pcap summary integration
  supports Linux or Windows; macOS supports client/version probes only.
- At initial inspection, ADB transfer was blocked by the sandbox. The later
  permission change resolved it; captures and the stock update are complete.
  REA itself did not bypass the restriction.

## Build the supplied checkout when its directory is writable

Use the pinned runtime already installed, then run:

```sh
cd "$HOME/dev/rea"
npm ci
npm run build:cached
node scripts/rea.mjs --version --json
```

These build steps were executed successfully after the host permission change.
The task-local runtime wrapper avoids depending on the shell's default Node.
No MCP registration is needed to use the CLI. In subsequent examples define:

```sh
rea() { node "$HOME/dev/rea/scripts/rea.mjs" "$@"; }
project="$HOME/dev/glassly-memomind-one-cfw"
mkdir -p "$project/analysis/evidence"
```

## Acquire and identify the APK set

After ADB access is available, use a fresh acquisition destination:

```sh
rea inspect-adb-package 47011FDAP0083R com.memomind.ai.aphrodite --json \
  > "$project/analysis/evidence/android-package.json"
rea pull-adb-package 47011FDAP0083R com.memomind.ai.aphrodite \
  --output-directory "$project/captures/rea-apks" --json \
  > "$project/analysis/evidence/apk-acquisition.json"
```

The package acquisition includes every split returned by `pm path`, with
digests. Use its returned paths. Expected base path:
`captures/rea-apks/com.memomind.ai.aphrodite/base.apk`.

```sh
export REA_JADX_MCP_JAR=/absolute/path/to/the/supplied/jadx-mcp.jar
rea doctor --provider jadx --json
apk="$project/captures/rea-apks/com.memomind.ai.aphrodite/base.apk"
rea inspect-android-package "$apk" --json \
  > "$project/analysis/evidence/apk-inspection.json"
rea search-android-classes "$apk" ota --json \
  > "$project/analysis/evidence/apk-ota-classes.json"
rea search-android-classes "$apk" firmware --json \
  > "$project/analysis/evidence/apk-firmware-classes.json"
```

Then use observed exact names with `inspect-android-class APK CLASS`,
`inspect-android-method APK CLASS METHOD`, and
`trace-android-references APK CLASS --method-name METHOD`. Select an overload
from the class result. Search download, Bluetooth and updater SDK classes when
the initial terms produce no candidates. Flutter's Dart AOT implementation may
instead reside in `libapp.so` in the ABI split; DEX searches do not establish
absence of an updater there. Inspect APK archive members before selecting a
native library for deeper analysis.

## Capture responsibilities

REA's `read-adb-logcat` is a bounded snapshot (`logcat -d -t`), not a continuous
capture. `inspect-pcap-capture` and `inspect-packet-capture` analyze existing
recordings and do not start capture. Use the task's continuous phone capture
for the full update, preserving the downloaded payload, app logs, packet
recording and Bluetooth HCI recording with start/end times and SHA-256.

Optional Frida tracing requires installed compatible bindings/server and a
reviewed script tailored to actual updater code. REA's one-shot
`instrument-with-frida attach PID --device-id DEVICE --script-file PATH
--duration-ms 60000 --json` is capped at 60 seconds and 16 MiB of retained
messages. It cannot alone guarantee capture of a whole OTA. Persistent MCP
sessions use `start_frida_session`, `load_frida_script`, status/export, and
`close_frida_session`; scripts can change target behavior. Capture metadata
and selected events rather than assuming a bounded message buffer is suitable
for the entire firmware body.

## Inspect the captured firmware on a prepared Linux host

The paths below are placeholders for the actual captured package and supplied
tools. Transfer immutable copies to a selected Linux environment, retaining
their source digests; no environment has been provisioned by this workflow.

```sh
export REA_BINWALK_COMMAND=/absolute/path/to/binwalk
export REA_UNBLOB_COMMAND=/absolute/path/to/unblob
export REA_FIRMWARE_PRLIMIT_COMMAND=/usr/bin/prlimit
firmware=/absolute/path/to/captured-firmware.bin
rea inspect-firmware-regions "$firmware" --json > firmware-regions.json
rea extract-firmware "$firmware" /absolute/path/to/new-extraction --json \
  > firmware-extraction.json
```

The extraction directory must not exist; its parent must exist and be writable.
If the OTA is a recognized ZIP or another supported package, first use
`rea inspect-artifact PACKAGE --json` to establish its member inventory. A
signature match is not proof of a partition or architecture. Follow returned
file offsets and hashes; keep extraction gaps and unknown regions explicit.
Select extracted ELF files individually for an available Ghidra provider.
Raw MCU code needs a confirmed ISA, endianness and load address before meaningful
decompilation. A delta package also requires its matching base image to recover
the complete resulting firmware.

For recorded traffic on Linux:

```sh
export REA_TSHARK_COMMAND=/absolute/path/to/tshark
rea inspect-pcap-capture /absolute/path/to/network.pcap --json > network.json
rea inspect-packet-fields --kind fields --protocol btatt --all --json \
  > bluetooth-fields.json
```

Use fields actually returned by the installed TShark with
`inspect-packet-capture PATH --fields FIELD --display_filter FILTER --json`.
Its default output page is 50 matches; paging or `--all_matches` is necessary
before whole-recording conclusions. Verify Bluetooth recording encapsulation
support in the installed dissector rather than assuming a filename suffices.

## Evidence required before a patch can be called feasible

Record package/version/model selection; payload lengths and hashes; compression
or delta reconstruction; all component images; update framing, acknowledgments
and checksums; signature verification locations; device-side acceptance; boot
verification and rollback behavior. Static app checks do not prove the glasses
will accept altered firmware. Keep original captures immutable, build modified
images separately, and establish a recovery route before a flashing experiment.

Local sources: `~/dev/rea/AGENTS.md`,
`.agents/skills/reverse-engineer-anything/SKILL.md`,
`docs/adb-device-analysis.md`, `docs/android-analysis.md`,
`docs/firmware-analysis.md`, `docs/frida-instrumentation.md`,
`docs/packet-captures.md`, `docs/pcap-analysis.md`,
`src/cli/fridaCommands.ts`, and `src/firmware/FirmwareCommand.ts`.
