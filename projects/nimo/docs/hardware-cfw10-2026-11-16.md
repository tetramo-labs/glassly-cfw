# GLASSLYCFW/10 hardware record

Nimo-4026 was flashed on 2026-11-16 UTC (November 15 Pacific) with the existing
revision 10 image built from source commit
`5befb880ea72ea79e6f0196feebf2ab7a8b63b09`. No firmware source changed.

## Image and transfer

- Image: `captures/firmware/ota-1.1.5.1-glasslycfw-10.bin`, 1,959,223 bytes.
- Image SHA-256: `b548f100dec940b7ad809446f5698a54ead6c82bd6ec0608cd87c273ff90b602`.
- Runtime SHA-256: `8ff359137d5d75969772409c9390f230ce1bc229d5da80fdbc5b0aa2cdb1415c`.
- Offline verification: `analysis/relay-20261114/regression-10-01/NOTES.md`
  records the original stages and successful stage 04 rerun against the pinned
  reference. The flashed image matches that run's output hash.
- Harness: Glassly repo `mobile/modules/bluetooth-sdk/tools/nimo-mac`, rebuilt
  with `swift build -c release` before use; OTA over GATT service 7033.
- Precheck: batteries `[100, 100]`, can-update `3`.
- Transfer: 479 blocks, 4,305 chunks, 1,959,223 bytes, two second-arm sync polls.
- Reboot acknowledged at 00:21:44 UTC after 72 seconds; flasher exited 0.

## Boot and hardware checks

The first reconnect attempt was too early and failed. A subsequent classic
connection succeeded. At 00:22:34 UTC the data channel independently returned
`FW-VERSION-v1.1.5.1-GLASSLYCFW/10`; the CFW identity command also returned
revision 10, master/right arm, 540 × 280 canvas.

An automated subset of `tests/hardware/steps-10.json` ran with `--auto`:
steps 1–13 and 20–35, **29 passed, zero failed**, completed at 00:24:10 UTC.
Manual touch cues and waits (14–19) were excluded without changing the tracked
suite or its remaining expectations.

Checks covered echo, a 1,200-byte transfer in three chunks, relay query/enable/
disable, display acquire/release, brightness, geometry, retained animation,
per-eye scene commands and right-eye canvas CRCs matching the emulator.
The retained scene CRC remained exact after the 40-second hold, and a settled
event arrived for tag 3.

The final status reported boot 1, `last_crash: null`, no flush errors,
rejections, repins or allocation failures, and no active display session.
Heap free was 69,016 bytes with the retained scene and 194,384 after release.
Test brightness was 12; release restored the starting panel brightness 16.
The notification relay was disabled at the end, with zero sent/drop counters.

## Limits and local evidence

The master replies for the pair; the left arm's version was not independently
queried. The OTA second-arm synchronization completed, but no wearer visual
assessment of either panel was collected. Manual touch gestures, live iPhone
ANCS delivery, the arm hosting the ANCS client, phone driver integration and
Android OTA remain unverified by this run. Step 20 checks status only; it does
not establish touch forwarding when steps 14–19 are excluded.

Raw logs, the derived subset, the structured flash record and the per-step
report remain local under `captures/hardware/2026-11-16-cfw10/`.

## Full hardware suite follow-up

At 00:56:26–00:58:39 UTC the unchanged `tests/hardware/steps-10.json` ran with
`--auto`: **35 passed, zero failed**, with no exclusions and no additional
flash. The harness waited for physical input at steps 15, 17 and 19; the wearer
performed each gesture when prompted:

- Right single tap: `88080001100002000000` (reply data, excluding status 0).
- Left single tap: `88080101100001000000`.
- Right long press: `8b080001100004000000`.

The wearer also confirmed, "Both eyes look correct," while watching the display
tests. This provides visual confirmation in addition to the canvas CRC checks;
it is not a separate per-step visual assessment.

The retained scene checksum passed after the 40-second hold, and the animation
settled event arrived. Final status remained boot 1 with `last_crash: null`,
zero flush errors, repins, rejections and allocation failures, and 194,428 free
heap bytes. The display lease/session and relay were released. The starting
panel brightness was 4; after release the stock auto-brightness reported 3.

This follow-up verifies the previously excluded touch gestures. Live iPhone
ANCS delivery, the ANCS client's arm, independent left-arm version querying,
phone integration and phone OTA checks remain outside this run.

Full raw log and per-step report:
`captures/hardware/cfw10-full-OE6MCn/{suite.log,report.json}` (local only).
