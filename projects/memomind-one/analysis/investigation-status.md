# Current status

Stock update to **1.0.3.127 completed and verified**. ADB permissions were
subsequently enabled, collectors ran successfully, and all requested OTA blocks
were captured and verified byte for byte. See [README](../README.md),
[protocol](protocol.md) and [firmware format](firmware-format.md) for current
results. The earlier blocked-state notes below are retained as acquisition
history, not current blockers. Host and phone collectors have now stopped;
Android full HCI logging remains enabled. On2026-10-31, the first same-length
English disconnect-toast patch was transferred and accepted; the glasses
reconnected after reboot. The user visually confirmed the patched text. See
[first text patch](first-text-patch.md).

---

# MemoMind One capture status

Observed 2026-10-30, approximately 20:13 America/Los_Angeles.

## Confirmed from the connected phone

- Pixel 9 Pro, Android 16; Magisk `su` returned uid 0.
- MemoMind Android package: `com.memomind.ai.aphrodite`, app 1.3.81,
  versionCode 120. Flutter app; native ABI split is installed.
- Glasses: MemoMind One, model H001Y, hardware 2.1.2 from app OTA logs.
- Installed glasses firmware: 1.0.2.151, front version 1.3.
- Offered update: 1.0.3.127, UI size 2.08 MB. App logs indicate an OTA URL
  and MD5 are present, but redact their values. Those values are not recovered.
- Glasses battery was 99%. The app was already paired when this investigation
  reached the main screen; the original pairing exchange was not captured.
- Full HCI logging was enabled using root, followed by Bluetooth disable/enable.
  Root `getprop persist.bluetooth.btsnooplogmode` subsequently returned `full`.
- `/data/misc/bluetooth/logs/btsnoop_hci.log` was created and grew from 9,135
  bytes to 71,165 bytes. This establishes recording activity, not complete
  packet coverage. No local packet decode has been performed.
- A 38,395-byte reconnect snapshot was preserved on the phone at
  `/data/local/tmp/memomind-20261030-2011/reconnect.btsnoop`.
- At approximately 20:14, another HCI snapshot and the app log were preserved
  beside it as `pre-update.btsnoop` (approximately 75 KiB) and
  `app-pre-update.log` (approximately 72 KiB). The pre-update HCI SHA-256 is
  `9f7dd6e4ac80f5d3b970ab24257277069777fddb181daa57bac515a9915da7ac`.
- The app logs show Bluetooth diagnostic events with UUIDs 0x7033, 0x2024,
  and 0x2026 and channel fields. These are log observations, not a decoded GATT
  service map. Include classic Bluetooth/RFCOMM in analysis, not only BLE ATT.

## Current screen and actions not performed

MemoMind is on Firmware Update with “Download and install” visible.
No OTA download/install was initiated. No unbind, factory reset, custom
firmware write, or modifications to `~/dev/g2flash` were performed.
Phone was already unlocked; no passcode entry was needed or saved.

## Blocking capture acquisition

Simple ADB inspection and UI commands succeeded. APK `adb pull` and the
continuous collector launch failed inside the host sandbox with inability to
access/start the ADB server (`Operation not permitted` on its socket).
An explicit escalation was rejected because session policy disallows sandbox
approval. Do not treat a generated script as a running collector, or retry
through a different transport to bypass the restriction.

The continuous collector was NOT started. Only the Android HCI logger is
known to be active. Its files can rotate; do not claim the entire session is
retained. Full capture/file access must be available before starting the OTA.

## Prepared artifacts and validation

- `scripts/capture_memomind.py`: host APK acquisition, periodic hashed app-file
  and HCI snapshots, app PID logcat, timestamped evidence and SHA-256 manifest.
- `scripts/mark_action.py`: timestamped action labels.
- `scripts/capture_on_phone.sh`: provisional phone-side collector, never
  successfully deployed or run. It includes a session-specific app PID and
  destination; refresh these before use. It captures network traffic as well.
- Python syntax compilation and shell `sh -n` passed. Live end-to-end capture
  has not passed. Polling can miss transient files, logcat's fixed PID can become
  stale, and copying live files is not atomic. Assess these gaps before OTA.
- `analysis/rea-workflow.md`: REA prerequisites and analysis workflow.
- `analysis/g2flash-port-assessment.md`: source-based portability assessment.
- `scripts/inspect_btsnoop.py`: streaming Android H4 file validation, digests,
  timestamp range, ACL handle inventory and explicit whole-session uncertainty.
  Six synthetic regression cases passed: intact ACL, filtered payload, partial
  copy, reported drops, mismatched ACL length and empty file. The host collector
  now requires an intact ACL snapshot before announcing capture readiness.
  No actual phone capture has yet been transferred for this validation.

## Remaining evidence

1. Verify local acquisition, full HCI packet payloads, rotation retention and
   continuous collectors, then capture controlled app actions with timestamps.
2. Capture stock OTA download, metadata, every transferred component and
   success/failure acknowledgments; confirm firmware version after reboot.
3. Correlate the package bytes with transport chunks and integrity fields.
4. Identify image architecture, container, checksum/signature enforcement,
   boot/recovery behavior and safe patch boundaries.
5. Assess and implement a separate MemoMind backend using applicable parts of
   `~/dev/g2flash`; existing G2 firmware offsets and patches are not portable
   without new evidence.

Full HCI mode behavior reference:
https://android.googlesource.com/platform/packages/modules/Bluetooth/+/refs/heads/main/system/gd/hal/snoop_logger.cc
