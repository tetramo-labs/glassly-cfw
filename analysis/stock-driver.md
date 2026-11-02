# Captured-stock OTA transaction driver

`scripts/memomind_flasher.py` is the independent transaction foundation for a
MemoMind port. It does not modify `~/dev/g2flash`. The default workflow is offline
replay; the separate `live` subcommand requires an explicit mode and image hash.
The parent investigation subsequently verified the check-only handshake on
hardware. Full independent flashing remains untested.

## Replay proof

```sh
python3 scripts/memomind_flasher.py replay \
  --firmware captures/firmware/ota-1.0.3.127-jhv3_release.bin \
  --expected-sha256 08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712
python3 -m unittest discover -s scripts -p test_memomind_flasher.py -v
```

The recorded input is `analysis/protocol/ota-final/rfcomm.tsv`, extracted from
`captures/ota-complete.btsnoop`. The comparison uses actual raw RFCOMM bytes and
chronological directions, not the generated packet summaries. All 3,965 selected
records are consumed: 3,464 generated outgoing packets are byte-identical, and
501 incoming packets drive the transaction. This includes the normal pre-OTA
notification, OTA handshake, 3,457 data chunks, 494 block ACKs, status query, and
reboot. The outgoing byte-stream SHA-256 is
`f4acaa5ca1a8a02001328eebc88c52be4ab65216cf8f42c70e09e77dda294004`.
The machine-readable result is `analysis/protocol/stock-driver-replay.json`.

The original eleven focused tests cover complete raw replay, check-only termination,
unsupported can-update response, wrong image/identity, wrong ACK sequence,
nonzero delay, invalid entry bounds, timeout without resend, arbitrarily split
socket input, the command-specific notification status, and noncontiguous range
requests. That initial implementation had 45 passing repository tests; later additions
are described below.

## Supported profile and transaction

Image eligibility requires the explicit expected SHA-256, complete successful `memomind_ota.unpack_ota` validation, and either the exact
captured stock SHA above or the explicit manifest eligibility described below.
Fresh public heartbeat/device-info must identify H001Y, hardware 2.1.2, front 1.3,
and a matching target MAC. Source firmware is restricted to 1.0.2.151 (captured
update) or 1.0.3.127 (same-version stock eligibility investigation). Allowing the
latter does not establish that the device accepts same-version reflashing.
Modified images require the exact-source manifest reproduction path below;
checksums or a caller-supplied image hash alone cannot authorize them.

The driver sends normal service1/command1c with INT8=1 and requires the captured
command-specific STATUS=1 response. The current live implementation keeps control UUID7033 connected and opens
OTA UUID7034 through Android SDP on a second bridge session. The original
one-socket implementation switched services; that historical check-only
workflow remains part of the evidence below. OTA commands 02, e1, and e2 identify the device
and file. Attach type1 must match image bytes 0:4; other attach fields are retained
as raw hex. In particular, type2=`6464` is not treated as proven battery data or
used to invent a battery threshold. e1 must request the captured 18-byte file ID
at offset zero; e2 must return result3. Any other result stops before e3.

Write mode then sends e3, follows the device-requested starting offset and block
sizes, adds per-fragment CRC32, increments the base sequence once per block,
and requires each ACK to echo the final fragment sequence. The observed profile
supports blocks up to 4096 bytes, fragments up to 630 bytes, CRC mode1, contiguous
forward ranges, status0 and delay0. The final offset0/size0 ACK must occur at file
EOF, followed by e6/status0 and 03/reboot0. The captured requested range begins at
162757; the earlier prefix is not bulk-transferred. The driver does not invent a
reason for device component selection.

The live pacing is 45ms between fragments within a block, approximating the
captured app pacing. Replay checks byte order and ACK dependencies; it does not
prove scheduler timing or device flash behavior. Any timeout, socket loss,
unexpected response, unsupported retry/delay, repeated range, or checksum/parser
error ends the attempt. No retry or recovery command is sent. The result means
only that reboot was acknowledged; a new connection and version query are still
required to verify installation.

## Live operator entry points

Start the bridge and forward TCP as described in `android_bridge/README.md`.
Stop the competing MemoMind connection first. The bridge Activity must stay open.

**Check-only is not a read-only device query.** It sends the pre-OTA notification,
attach, file-ID request and file-ID eligibility command. These may change
transient updater state. It stops before e3, transfers no e5 firmware data, and
sends no reboot command. It closes the host connection when finished; restoring
the official app and checking device state are operator responsibilities.

```sh
python3 scripts/memomind_flasher.py live --check-only \
  --address 4C:3C:8F:90:CC:C3 \
  --firmware captures/firmware/ota-1.0.3.127-jhv3_release.bin \
  --expected-sha256 08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712 \
  --trace captures/ota-check-only.jsonl
```

Replacing `--check-only` with `--confirm-write` explicitly authorizes OTA entry,
stock data writes and reboot. Trace paths must be new; existing files are never
overwritten. Both modes parse and hash the image before connecting. The parent investigation verified this exact check-only command against H001Y
firmware1.0.3.127. The device returned e2/result3 and the driver stopped before
e3 with zero blocks/chunks. Evidence is in `captures/probe/ota-check-01/`:
`trace.jsonl`, `result.stdout`, `result.stderr`, before/after HCI captures,
`actions.json`, and `logcat.txt`. The bridge was stopped, the forward removed,
and MemoMind reopened afterward. This does not prove a same-version write would
complete or that modified images are accepted.

## Verified-manifest image eligibility

The live CLI accepts `--patch-manifest PATH --stock-source PATH` together. The
source SHA must equal the captured stock SHA above. It invokes
`apply_memomind_patch.apply_patch`, reproducing the exact same-length component
body edits, rebuilding the container and checking every manifest hash. The rebuilt
output must be byte-identical to `--firmware` and match `--expected-sha256`.
The payload length (`len(image)-18`) must also fit the observed type4 staging
partition capacity `0x25e000`, corroborated by native e2 handling at 0x043415b4.
There is no unsigned-image override or general checksum-only eligibility path.
The transaction constructor repeats this verification for direct Python callers.

Use the same live command with the selected modified image/output hash and these
two extra paths. `--check-only` still stops after e2; `--confirm-write` remains
required to enter OTA. A modified image must receive e3 starting offset **18**,
so every byte after the file-identification header is requested anew. A different
starting offset aborts before the first data chunk. Stock images retain the
captured device-selected-range workflow. The new CRC/length must not reuse a
partial stock transfer. This check does not establish custom-image acceptance,
correct execution, boot authentication, or recovery.

## Preserved control connection

The stock app kept normal control open alongside OTA, including two unsolicited
normal cmd013e events. The rebuilt bridge supports two simultaneous host sessions
(each owns one Bluetooth socket), advertised by `maxSessions:2` in its greeting.
The current live driver requires that capability before issuing any device query.
Install `android_bridge/build/memomind-bridge.apk` again before using it. The
current artifact SHA-256 is
`5133971b9ab4cf0639535823a7802d9ea493e19fc28ace632fe46cfffde93826`.

After the correlated pre-OTA notification reply, control remains connected.
A monitor consumes raw control input and records it in the same JSONL trace,
with `session:control` or `session:ota` labels. It does not parse or discard GM
fragments. The initial identity probe and pre-OTA response parser explicitly
accept repeated-FA continuation, which has now also been captured on 1.0.3.127
status replies (`captures/text-patch-20261031/baseline-probe.jsonl`). It sends no speculative heartbeat
or other control command during transfer. A detected control-link failure stops
subsequent OTA writes. Both host connections close on success/error. Full raw
stock replay also passes with separate control and OTA transports.

The earlier successful hardware check used the one-session service switch; it
does not validate this new concurrent bridge or a complete independent flash.
Nineteen driver tests now cover manifest reproduction/bypass rejection, modified
fresh-start enforcement, and retained control, in addition to the original
recorded-transcript and failure tests. No automatic app restart, generic downgrade,
recovery, rollback, power-loss safety, or resumable-flash behavior is implemented.

## Fixed runtime-probe image eligibility

The first executable extension has a separate, mutually exclusive live eligibility
mode: `--runtime-manifest PATH --runtime-blob PATH --stock-source PATH`.
Here `--stock-source` is the exact visually verified text-patch OTA
(SHA-256 `941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876`),
not the original unmodified stock. The flag name is retained for compatibility;
the runtime constructor pins the required source independently.

`scripts/build_memomind_runtime.py::verify_runtime` reconstructs the fixed
`memomind-runtime-probe-v1` profile: a bounded, aligned append at `0x0439bea0`
and the guarded8-byte callback initializer replacement at `0x042e82e0`.
Every manifest field and blob hash must match the reproduced result, which must
also be byte-identical to the supplied firmware and match `--expected-sha256`.
The driver invokes this validation before connecting and again in its transaction
constructor. `--patch-manifest` cannot be combined with runtime mode. Missing
source/blob/manifest combinations are rejected; there is no generic appended-image
or unsigned-image bypass.

The existing `--check-only` / `--confirm-write` gate, staging bound, identity check,
control-link preservation and modified-image starting offset18 requirement remain
in force. Runtime eligibility establishes construction provenance, not that the
new executable hook is correct. Five focused integration tests cover valid
reproduction, missing/mixed modes, wrong source/blob/output, check-only, and
refusal to resume the earlier stock transfer. The broader implementation plan
is `analysis/g2-runtime-port-plan.md`.

Separately, the text-only custom transfer has now completed and was visually
confirmed by the user; its evidence is in `analysis/first-text-patch.md` and
`analysis/protocol/first-text-patch/`. That success does not by itself validate
the new executable runtime probe.
