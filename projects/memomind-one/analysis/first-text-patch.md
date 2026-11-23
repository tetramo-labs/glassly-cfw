# First visible firmware patch

User-selected scope: a minimal visible text change, followed by the user's
visual confirmation before allocating flash or pursuing G2 feature parity.

The English system toast **Bluetooth disconnected** becomes **Glassly firmware
ready**. Both strings occupy22 ASCII bytes; the original NUL and adjacent bytes
remain untouched. The actual byte difference is21 bytes because one character
is shared. No executable instructions, pointers, partition layout, component
lengths or version fields change.

## Exact artifact

- Stock OTA: `captures/firmware/ota-1.0.3.127-jhv3_release.bin`, SHA-256
  `08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`.
- Candidate: `captures/firmware/ota-1.0.3.127-glassly-text.bin`, 2,185,415 bytes,
  SHA-256 `941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876`.
- Component3 body offset `0x17d710`, XIP address `0x04368730`, English resource
  ID `0x50`. Firmware still identifies as1.0.3.127 by design.
- Reproducible manifest: `patches/visible-text-1.0.3.127/patch.json`.
- Construction proof: `patches/visible-text-1.0.3.127/verification.json`.

[Native UI proof](ghidra/ui-proof/report.md) follows locale selection, the
disconnect event and actual LVGL label rendering. Baseline live status reports
language2, which native code maps to English table1. Merely closing MemoMind
produces a separate **App disconnected** message and is not the intended test.

[Independent container audit](first-text-patch-container-audit.json) reproduces
the exact candidate hash, checks all integrity layers and confirms that the
metadata and all other compressed streams are byte-identical. The patched
payload and its4096-byte-rounded span fit the existing type4 staging allocation.

## Transfer and verification

Full HCI and Android logcat collection started before any candidate transfer in
`captures/text-patch-20261031/`. The baseline heartbeat/device information and
status show H001Y, hardware2.1.2, font/front1.3, firmware1.0.3.127, battery100%
and charging. The status reply uses repeated-FA continuation frames even on
this firmware, so it was decoded using that explicitly supported compatibility
mode.

The rebuilt bridge keeps the normal control and OTA RFCOMM connections open
simultaneously, matching the stock application's captured behavior. The stock
eligibility handshake passed on this two-connection implementation. All53 tests
passed before the candidate transfer.

The first candidate transfer started2026-10-31T16:36:53Z. The live sender
reproduces the image from its stock source and manifest, verifies the exact hash,
and checks device identity and staging bounds before connection. It requires
e2/result3, then e3/offset18 before sending any modified data. A timeout or
unexpected reply stops without automatic retransmission.

Current outcome: **transfer accepted; device reconnected; user visually confirmed**. The glasses returned e2/result3, requested offset18, acknowledged
all534 blocks/3,735 chunks, returned e6/success and acknowledged reboot at
2026-10-31T16:40:15Z. The first three read-only reconnection attempts encountered
Bluetooth page timeouts during the first~36 seconds after reboot. The glasses
initiated a link at16:40:59Z, and MemoMind's newly opened control connection
received a fresh device-info response at16:41:03.552Z (HCI frame25969), about48
seconds after the reboot acknowledgment. This is post-update runtime evidence;
the unchanged version string alone does not prove the edited text is active.

The frozen capture `ota-transfer-frozen.btsnoop` has SHA-256
`261e7e52ca258335438a0e3b2cb5e51fd50e20719c71634a780455fd9ebaa151`.
[Selected-session decoding](protocol/first-text-patch/summary.json) confirms
all3,735 chunks match this modified image, all CRCs pass, every requested block
precedes its matching ACK, and no requested range is missing.
[Whole-image proof](protocol/first-text-patch/whole-image-proof.json) combines
the first18 header bytes sent in e2 with the complete e5 range18..2185415 and
reconstructs the exact candidate SHA-256. The decoder's historical `*_stock`
field names refer to its explicitly supplied modified image in this report.

The capture has no truncated records. Its one546-microsecond timestamp
regression predates this experiment and is retained unchanged; record order and
session selection preserve the OTA proof. The raw session-tagged transcript,
command arguments, final result and post-reboot app response are retained in the
session directory. The research bridge was stopped and its port forward removed;
MemoMind was reopened and successfully connected.

## User visual check

After a successful update and reconnection, wear the glasses, wake the normal
idle display, and turn Bluetooth off on the phone. The expected message is
**Glassly firmware ready**. Turn Bluetooth back on afterward. This must be a
Bluetooth disconnection, not simply closing the app. Other active UI modes can
suppress the toast; perform the check from the normal idle display.

The user confirmed seeing **Glassly firmware ready** on2026-10-31. This
establishes execution of the edited UI text on the glasses. Work on the flash
allocation and G2 runtime port can now proceed. A bootable text patch would establish this image's acceptance; it
would not establish arbitrary code-patch correctness or an unbrick procedure.
