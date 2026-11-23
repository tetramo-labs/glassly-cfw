# Working instructions

Read README.md, docs/findings.md, docs/plan.md and docs/needs.md before continuing.
This project targets CRKD ATOM+ (Atom Plus), not the original ATOM. The user
requested investigation and a folder with a plan and required inputs.
On 2026-11-09 the user connected a rooted Android phone and explicitly requested
decompiling the installed CRKD app. Read docs/android-app-analysis.md for the
resulting APK extraction, native/JavaScript analysis and public firmware files.
The phone was accessed only for installed package metadata and APK extraction;
no controller commands or firmware writes have been performed in this project.

Continue public research, offline analysis and local tooling within that scope.
Do not treat historical flashing authorization in sibling projects as ATOM+
hardware authorization. Do not run sibling flashers against an ATOM+.

Separate vendor claims, static deductions and observed hardware results. Chip,
ISA, USB IDs, memory maps, GATT UUIDs, button masks, checksums, updater commands
and recovery entry must be established for this target. No copied addresses or
guessed bootloader commands. Do not call unbound components flashable firmware.

Preserve original OEM files and device backups locally and immutably. Keep OEM
images, app packages, device identifiers, pairing data, keys, downloads and
generated binaries under ignored research/ or build/. Publish only original
source, hashes and sanitized findings; do not create a remote without a request.
sources.lock.json distinguishes downloaded/verified hashes from metadata-only
leads. Never invent a hash or claim a download from an exhibit listing alone.

Future device tooling must select an explicit target, have bounded timeouts and
stop on identity/checksum/readback mismatch. Before firmware writes, establish
the update protocol, backup coverage, retained calibration/settings and a
concrete restoration/recovery assessment. No routine full-chip erase, fuse
changes or protection unlocks. Review startup copies, execution placement,
RAM ownership, calling conventions and BLE lifecycle before custom code.

Verify stock HID, custom notifications, battery idle/wake and actual phone
foreground/background/locked behavior separately. A Mac BLE capture does not
prove iOS background delivery. Use checks appropriate to actual code changes;
planning documents alone do not require a firmware test suite.
