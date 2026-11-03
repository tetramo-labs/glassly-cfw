# Working instructions

Read docs/findings.md and docs/plan.md first. This repository is for the IINE Mini Retro Ananke Gen 2, not the six-button Gamebrick Mini.

Current scope: identify and back up the existing firmware for reverse engineering. Normal USB is 4353:800c; the vendor interface answers model ig05 / firmware 0x0601. Update entry is power off, hold Capture + Home while connecting USB. Observed USB is 4c4a:2342 / BR23UBOOT1.00; live SCSI INQUIRY confirmed BR23 / UBOOT1.00. Flash size and installed partition layout remain unconfirmed. Similarity to Gamebrick does not establish compatibility. Do not apply its firmware, patch offsets, partition map, flash size or installer here.

Keep original full reads immutable and ignored by Git. Require two identical complete reads and verify every backup against its metadata.json. Save partial/failing captures, labelled incomplete. Record source revisions and hashes; downloaded dependencies, OEM firmware and device dumps stay local. Do not create a remote or publish artifacts unless requested.

Hardware operations need an explicit target, command allowlist and bounded timeouts. Stop on identity, checksum, USB status or readback mismatch. The initial backup tool only supports macOS and 4c4a:2342 at an explicit physical USB location; identify must precede backup. BR23 / UBOOT1.00 is the only currently reviewed RAM-loader path (11,264-byte pinned br23loader.bin at RAM 0x12000). An unknown identity requires research, not weakening the gate. No flash erase/program or fuse commands belong in the backup transport.

Run privileged USB operations from the user's interactive terminal. Ask for a concrete command when credentials are needed; do not automate Ghostty or use background administrator launches. Keep platform transport in research/usb_transport.py and research/native-usb.m.

Before any later custom installation, derive the patch from this unit's installed application and actual partition map, review execution limits, branch targets, startup relocation and state allocation, and demonstrate recovery independent of the application. Preserve calibration, pairing, settings and keys. Do not erase the whole flash or burn fuses as a routine step.

After a future flash, validate normal HID, vendor BLE notifications and actual iOS background/locked behavior separately. Mac BLE results do not establish iOS support.

The user selected the Purple/Gray/Cream Yellow model group and requested CFW based on the latest official firmware for the variant. The supplied matching release is IG05_V0900.ufw, pinned in sources.lock.json; V0901 is for a different model group. Preserve the original installed firmware first. Do not run the OEM updater or its whole-flash erase as part of backup. Official release selection does not establish compatibility of its packaging with the installed layout.

User priority: first investigate stock Switch-mode input and an Ananke controller driver in ../glassly. Preserve the installed backup first. CFW is conditional on stock firmware failing the required app-accessible input/background behavior. Do not assume Switch mode uses BLE, that HID reports are exposed through CoreBluetooth, or that the Gamebrick AE42 packet format applies to Ananke. Require live protocol evidence and actual iPhone background/locked validation.
