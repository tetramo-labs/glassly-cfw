# Working instructions

Read docs/findings.md and docs/plan.md first. This repository targets the IINE Mini Retro Ananke Gen 2, not the six-button Gamebrick Mini. Current status and public commands are in README.md.

Experimental V0900 CFW has been flashed and fully read back on one unit. All 16 physical controls were mapped over macOS BLE after correcting Bluetooth-task wake. Normal HID coexistence, standby/wake and real iPhone background/locked delivery remain unverified. Mac BLE tests do not establish iOS support.

The selected Purple/Gray/Cream Yellow group uses the supplied official IG05_V0900.ufw, pinned in sources.lock.json. V0901 is a different variant. No OEM firmware, complete application image, device dump, calibration, pairing data or key belongs in Git. The bundled payload is only our compiled patch. Keep original full reads immutable and ignored; require two identical complete reads and verify backups against metadata. Retain partial/failing captures as incomplete.

Hardware operations require an explicit target, bounded timeouts and a command allowlist. Normal USB is 4353:800c / ig05; update mode is 4c4a:2342 / BR23 UBOOT1.00. Enter it by powering off and holding Capture + Home while connecting USB. The pinned 11,264-byte BR23 RAM loader at 0x12000 is the only reviewed loader. Stop on identity, checksum, USB status or readback mismatch. Keep platform transport in research/usb_transport.py and research/native-usb.m. Backup transport must never gain flash-write or fuse commands.

Privileged USB commands run in the user's interactive terminal. Do not automate terminal applications, send passwords or launch background administrators. Public Windows/Linux libusb paths are implemented but not hardware validated; preserve all BR23 gates.

The public installer is research/flash_ananke.py. It derives a per-unit plan from fresh reads, rejects unknown applications/configuration/layouts, preserves everything except application bytes and necessary CRCs, and only writes the reviewed application sectors. No whole-flash erase, protection unlock, fuse command or automatic reset. Application-independent recovery remains unproven and every public installation requires explicit --accept-unrecoverable-risk. The user accepted that risk for the recorded experimental installations; this does not establish recoverability.

Review execution limits, direct branches, startup relocation and state allocation before changing the patch. Keep the compiled payload, manifest and final application hash synchronized. Historical one-unit research scripts are not portable public installers. New public workflows must work without a sibling checkout or private dumps.

The user requested publication to tetramo-labs/glassly-ananke-cfw and Glassly integration on tetramo-labs/glassly dev. Keep firmware protocol changes and both native app decoders consistent; pairing is Pair + Right in Glassly, not system Pro Controller pairing.
