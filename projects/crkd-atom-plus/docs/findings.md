# Initial findings

Updated 2026-11-09. This is a feasibility investigation, not a working port.

## Android extraction: 2026-11-09

The connected Android phone provided the installed `com.crkd_app` version
1.0.365 (365), including all four APK splits. JADX produced 9,490 Java files;
the React Native bundle is Hermes bytecode v98 and was also disassembled and
decompiled to pseudocode. Tool warnings and limitations are recorded in the
[analysis report](android-app-analysis.md).

The `atomp` branch uses `com.host4.platform` for both configuration and OTA.
Its stock test-mode code enables mode 0x82 and decodes buttons, four stick axes
and both triggers from vendor notifications. The app-derived normal GATT
service/write/notify UUIDs are FF00 / FF01 / FF02; OTA uses FF10 / FF11 / FF12.
This is static evidence, not a live discovery or confirmation of the stock
controller's behavior. The reused FF10 short UUID does not establish any
compatibility with the 8BitDo protocol.

The JavaScript app requests `https://api.crkd.gg/device/firmware`. An
unauthenticated GET succeeded, and all three listed ATOM+ binaries were fetched
and SHA256-pinned: 20260723 public v1.0.0, 20260814 beta v1.1.0 and 20260912
beta v1.1.0. The host passes raw file bytes into an OTA path with CRC-16/XMODEM
and a 24-bit length. It does not establish firmware-side authentication rules.

The images have approximately 7.995 bits/byte entropy, partially shared headers,
and no convincing chip/SDK strings. Their encoding, executable layout and chip
remain unknown. No decryption or successful firmware disassembly is claimed.

The highest-value next step is a live stock input capture before committing
to custom firmware. The following sections retain the initial public research.

## Vendor documentation

CRKD's [ATOM+ product page](https://crkd.gg/pages/atom-plus-gaming-controller)
describes Bluetooth connectivity, two TMR thumbsticks, digital shoulder/trigger
inputs, motion control and vibration. It explicitly supports firmware updates
and input remapping through the CRKD Companion App / CTRL. That makes the app
and its update mechanism useful investigation targets. It does **not** identify
the SoC, GATT contract, firmware format, signature requirements or recovery path.

The [official firmware page](https://crkd.gg/pages/firmware) exposed Guitar and
Nitro Deck updater downloads when checked. No ATOM+ standalone download was
listed in the retrieved page. This does not prove there is no public image or
USB updater. The older `/pages/crkd-firmware` URL failed in the research browser;
the site's current Firmware navigation points to `/pages/firmware`.

The [quickstart page](https://crkd.gg/pages/quickstart) has an ATOM manual link,
but it was not established as the ATOM+ manual. Use the model-specific FCC
manual lead below rather than borrowing original-ATOM instructions.

## Regulatory document leads

The [FCC filing index](https://fccid.io/2BAXLCK26AP) lists **2BAXLCK26AP**, model
**CK26AP**, product **ATOM PLUS CONTROLLER**, applicant Red Octane Labs LLC,
application date 2026-07-31. These are filing metadata from a mirror, not a
physical match to the user's controller.

- [Internal photos, exhibit 9516807](https://fccid.io/2BAXLCK26AP/Internal-Photos/Internal-Photos-9516807):
  four pages listed; main lead for PCB markings, radio/MCU, external flash and pads.
- [User manual, exhibit 9516813](https://fccid.io/2BAXLCK26AP/User-Manual/Users-Manual-9516813):
  one page listed; lead for documented modes and app pairing.

Only the exhibit metadata pages were retrieved. The internal-photo PDF link
failed with a cache miss; the manual link returned another metadata page. No
PDF bytes or chip markings have been examined. The advertised PDF hashes are
kept separately in sources.lock.json and are **not locally verified hashes**.
Schematics/block diagram are listed as metadata only; do not assume availability.

## Relevant local reference projects

| Project | Established approach | What can transfer |
| --- | --- | --- |
| `../8bitdo-micro` | Yichip firmware package; boot type 17; FF10/FF13 stream; 16 buttons verified | Package provenance, minimal probe sequence, button/chord and battery capture methodology |
| `../8bitdo-zero2` | YC3121 path in a package with GD32/Yichip sections; boot type 20; 12 buttons verified | Section preservation, full readback, explicit stream start/stop and baseline handling |
| `../ananke` | Jieli BR23 update path; per-device partition-aware patches; 16 buttons verified | Two-read backup discipline, application-only writes, lifecycle and task-wakeup analysis |
| `../gamebrick-mini` | Jieli BD19 patch adding AE42 button notifications; six buttons observed | Vendor stream design and documented startup/placement failure lessons |

These are summaries of the sibling repositories' recorded results, not new
tests performed here. Their device identities, loaders, addresses, keys, masks,
UUIDs and update packets are not ATOM+ evidence. In particular, the two 8BitDo
controllers use different updater paths despite superficial similarities.

## Feasibility assessment

Promising investigation target: it has a vendor app and an official wireless
update feature. A Glassly port is not yet established. First check whether the
stock app interface already carries live controls. If it does, an app driver
could meet the input goal without custom firmware. Otherwise the path depends
on obtaining the image, identifying the architecture, and understanding update
validation and recovery. Signed-only updates may prevent a simple binary patch.

Still unknown after app analysis: actual SoC/ISA, installed controller version,
live GATT properties, test-mode support and lifecycle on this unit, USB data
support, normal/update USB IDs, boot entry, firmware authentication, flash layout,
backup availability, calibration storage and independent recovery.
