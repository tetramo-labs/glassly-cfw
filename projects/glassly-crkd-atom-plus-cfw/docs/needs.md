# Inputs needed

## Needed for the first hardware session

| Input | Purpose | Current state |
| --- | --- | --- |
| Physical CRKD ATOM+ | Confirm exact variant and observe real input/update behavior | Availability not yet established |
| Model/FCC label and edition | Match the unit to CK26AP / 2BAXLCK26AP or discover a different revision | Filing lead only |
| Installed firmware version | Choose the correct baseline and avoid losing factory evidence | Unknown |
| USB-C data cable and this Mac | Check whether USB exposes data/recovery, not just charging | ATOM+ USB support unverified |
| Phone with official CRKD app | Observe CTRL pairing, app version, available firmware and configuration | Connected Android; APK 1.0.365 extracted 2026-11-09; root reported by user, not needed for extraction |
| Short guided button/stick session | Map physical controls to captured packets | Pending stock interface inventory |

Start with a charged controller and record versions before accepting an update.
No teardown is needed initially: try the public internal photos first.

## Useful if public downloads are insufficient

- Android phone: convenient for a user-controlled Bluetooth HCI snoop capture
  of the official app session and access to legitimately installed app packages.
  An iPhone can still establish app behavior; do not assume it provides the same
  capture/export options. No root requirement has been established.
- Exact OEM firmware image or app-downloaded update and its catalog metadata.
  Keep originals unchanged under `research/downloads/` and record hashes.
- Clear board/chip photos only if FCC images cannot identify this hardware.
  Record board revision and component markings before choosing debug tools.

## Conditional, not required purchases

A spare unit, logic analyzer, USB capture setup or debugger/programmer may help
later. Do not choose a voltage, pinout, probe or programmer until the actual chip
and electrical interface are identified. No soldering requirement is established.

## Evidence to save

For each session record date, model/revision, stock/app version, mode, USB versus
battery power, exact tool revision and test sequence. Keep raw BLE/USB captures,
firmware and device backups in ignored local folders; write sanitized summaries
under docs/. Keep identifiers, account tokens and pairing material out of docs.

The Android phone and installed app are now available. APK extraction, native
decompilation, Hermes decoding and public firmware downloads are complete.
The next useful input is an ATOM+ in the official app's controller/test screen
for a live capture. A controller connection and installed controller firmware
version have not yet been established. See android-app-analysis.md.
