# Zero 2 development history

Work toward exposing Zero 2 button presses and releases through a vendor BLE
GATT notification stream for the Glassly App, following the Gamebrick and Ananke
projects.

**Status: custom flashing, BLE notifications and a bounded battery idle test
are verified on hardware.** Our native macOS flasher verifies the entire
73,216-byte application before reboot. The installed notification/idle image
returned four test bytes over FF13 and remained connected on battery for
188.448 seconds with no keepalive writes, then delivered four echoes after
reconnect. The earlier BLE-only image had timed out after about 61 seconds.

The [button-streaming image](docs/buttons-probe.md) is now flashed and fully
read back. All 12 buttons delivered press/release notifications, and A+B worked
as a combined held state. The ordered test had 27 consecutive packets with no
sequence gaps or overflow flags. It uses a separate
compact implementation with explicit start/stop commands, 16 queued snapshots
and reserved state. The original C objects remain unbound. Physical labels are recorded in the protocol audit; Glassly background delivery
is still untested.
ARM ROM bytes and original device data are saved locally; separate radio ROM
remains unavailable.
`python3 tools/inspect_usb.py` reads the macOS USB registry and
saves target descriptors under ignored `build/hardware/`. It sends no device
commands. Shared bootloader IDs are candidates, not sufficient device identity.

`tools/read_boot_version.c` implements fixed read-only queries for the observed
bootloader. Its header documents compilation and invocation. It requires the
observed USB location and checks the exact descriptor; successful memory reads
validate status, command, echoed address/length and CRC. Captures belong under
ignored `build/hardware/`. See [live findings](docs/findings.md) before using it.

## Verified minimal flashing experiment

The script supports only pinned stock v1.08, name-probe, BLE-probe, notification-probe and buttons-probe packages on the
observed YC3121 Zero 2. It checks boot product `0x9018`, USB location and report
descriptor, saves application/metadata backups, writes the encrypted Yichip
section, verifies plaintext readback, commits the version and reboots.
Close the vendor updater first and enter update mode. Use the USB location
observed for your device; `0x02100000` below belongs to the tested connection.

```sh
python3 tools/build_name_probe.py
python3 scripts/flash.py name-probe                 # offline plan only
python3 scripts/flash.py name-probe --location 0x02100000 --apply
python3 tools/inspect_usb.py                       # expect Glassly Zero 2 test01
```

Use `stock` instead of `name-probe` to reinstall the pinned stock image from a
recognized stock/name-probe/BLE-probe/notification-probe/buttons-probe baseline. The current script rejects unknown or
partially written baselines; it is not a general recovery tool. Raw binaries and
transaction logs remain ignored under `build/hardware/`. The 21-byte shared model
name may also affect Bluetooth naming; the live test verified USB enumeration.
See [flashing evidence](docs/evidence/name-probe-flash.json).

## BLE visibility experiment (flashed and verified)

Startup uses a separate BLE-name command containing `80EL`, while its visibility
wrapper forces bit 2 off. Related Yichip protocols identify this as BLE
advertising enable. `ble-probe` changes one instruction to set that bit, on top
of the verified name-only image. It adds no RAM or button-stream code. Offline
execution verifies the changed command bytes. Hardware readback matches all
73,216 bytes; the 4,096-byte metadata page is unchanged and runtime USB boots.
`80EL` now advertises and its FF10 service / FF13 characteristic / CCC 2902 are
discoverable; enabling notifications succeeds with USB connected.
The flag is forced for every visibility call, so sleep/power behavior is also
experimental. See [binding details](docs/radio-binding.md#visibility-experiment).

```sh
python3 tools/build_ble_probe.py
.venv/bin/python tools/inspect_ble_setup.py
python3 scripts/flash.py ble-probe                 # offline plan
python3 scripts/flash.py ble-probe --location 0x02100000 --apply
```

The macOS diagnostic saves source snapshots, hashes and JSON event logs under
ignored `build/hardware/`. Scan records Zero 2 / `80EL` / FF10 candidates without
connecting; names alone are not proof of identity. Select an observed peripheral
UUID for discovery or an FF13 notification subscription:

```sh
python3 scripts/ble_probe.py scan --seconds 60
python3 scripts/ble_probe.py inspect --identifier OBSERVED_UUID
python3 scripts/ble_probe.py subscribe --identifier OBSERVED_UUID --seconds 90
python3 scripts/ble_probe.py cycle --identifier OBSERVED_UUID --seconds 30
python3 scripts/ble_probe.py keepalive --identifier OBSERVED_UUID --seconds 120
```

The subscription mode enables FF10/FF13 notifications without writing vendor
characteristic values. It logs subscription completion, disconnection timing
and any notifications separately; successful subscription does not prove data
delivery. `cycle` toggles subscription off and back on. `keepalive` additionally
writes one zero byte to FF13 every 20 seconds after acknowledgement to exercise
the stock idle/watchdog reset handler. This kept a battery connection up for
188 seconds with nine acknowledged writes; a subsequent reconnect and
subscription cycle succeeded. This historical BLE-only image sent no custom notifications.
See [hardware flash evidence](docs/evidence/ble-probe-flash.json),
[battery baseline](docs/evidence/ble-battery-baseline.json), and
[keepalive comparison](docs/evidence/ble-battery-keepalive.json).

## Build and inspect

The [notification/idle probe](docs/notification-probe.md) is now **flashed and
verified on hardware**: all four test writes produced matching FF13 notifications
with USB connected. It echoes one-byte FF13 writes and is designed to keep
the controller awake while BLE-connected, using no persistent RAM and no button
stream component. Its connected-idle policy is deliberately experimental and
passed a 188.448-second battery test without host keepalives. Four echoes also
succeeded after reconnect on battery; this is not a long-term power measurement.

```sh
python3 tools/build_notify_probe.py
.venv/bin/python tools/inspect_notify_probe.py
python3 scripts/flash.py notify-probe                 # offline plan
python3 scripts/flash.py notify-probe --location 0x02100000 --apply
python3 scripts/ble_probe.py echo --identifier OBSERVED_UUID --seconds 30
```

`buttons-probe` is now flashed; baseline, all 12 button press/release pairs and
A+B delivery are verified on the tested controller. Read its
[placement and protocol audit](docs/buttons-probe.md) before flashing. The
receiver enables notifications, sends A1 once, logs v4 button snapshots, and
sends A0 before intentional disconnect. No periodic keepalive is required.

```sh
python3 tools/build_buttons_probe.py
.venv/bin/python tools/inspect_buttons_probe.py
python3 scripts/flash.py buttons-probe                 # offline plan
python3 scripts/flash.py buttons-probe --location 0x02100000 --apply
python3 scripts/ble_probe.py buttons --identifier OBSERVED_UUID --seconds 180
```

Python 3 and Clang are required. The default checks use only Python's standard
library and the vendored MIT-licensed [8cryptdo](https://github.com/aeromodes/8cryptdo).
On macOS, Clang comes with Xcode Command Line Tools.

```sh
python3 scripts/fetch_stock.py
python3 tools/inspect_stock.py
python3 scripts/check.py
```

Outputs (local and ignored):

- `build/stock/section0.bin`, `section1.bin`: unmodified decrypted v1.08 payloads.
- `build/stock/inspection.json`: reproducible container, radio-table, memory-constraint and code-anchor evidence.
- `build/button_stream.arm.o`, `build/button_input.arm.o`: unbound Cortex-M0/Thumb
  relocatable components, **not firmware images**.
- `build/component.json`: compiler, source/output hashes, stack-frame estimates and explicit build limits.

The stock downloader checks exact size and SHA256, and refuses changed downloads.
The vendor API's MD5 does not match the downloaded package; this discrepancy is
recorded in [findings](docs/findings.md), not treated as a successful vendor
checksum verification. Downloaded OEM images are not included in source control.

For bounded disassembly:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-analysis.txt
.venv/bin/python tools/disasm.py build/stock/section1.bin 0x6ece 0x6ee0
python3 tools/radio_disasm.py build/stock/section1.bin 0x530 0x53d
.venv/bin/python tools/emulate_stock.py
```

The Thumb disassembler accepts **section-relative offsets** and defaults to the
Yichip section's load address. It does not infer code/data boundaries. The radio
decoder instead takes **radio instruction indices**, and preserves unknown
encodings. The emulator checks stock startup, GPIO mapping, raw input wrapper,
task congestion gates, timer arithmetic, static memory pools and IPC in virtual memory. Preamble stubs
used for isolated task tests are recorded explicitly. It needs JIT memory permission on macOS. Its results
are written to `build/stock/emulation.json`. It does not emulate BLE delivery.

Optional updater research uses the exact ZIP pinned at `sources.lock.json`'s
`updater_research.path`: `.venv/bin/python tools/inspect_updater.py`. It executes
isolated header comparisons, a protocol gate and read/query packet constructors
in synthetic memory, never the updater
application or its device APIs. Results go to `build/stock/updater-selection.json`.
The PID `0x9018` path selects v1.08 section 1; the connected unit's product query
and application-prefix readback agree with that selection. The GD32 hardware
selection path remains unresolved.

Optional startup-ROM audit uses the locally captured, hash-pinned 32,672-byte
ARM ROM prefix: `.venv/bin/python tools/inspect_arm_rom.py PATH_TO_PREFIX`.
It executes the startup OTP calls and their delay loops using synthetic
peripheral inputs, checks RAM write boundaries and reports isolated stack use.
It never opens hardware. The captured prefix has been independently reread and
matches byte-for-byte; it still lacks the final 96 bytes of the documented ARM
ROM region. The separate Bluetooth ROM is not part of this capture.

Additional offline audits:

- `.venv/bin/python tools/inspect_yichip_debug.py` checks the pinned vendor
  utility's code-memory read setup with every device operation stubbed. Its
  selector sequence remains an unverified Zero 2 lead.
- `.venv/bin/python tools/inspect_systick.py` checks 176 stock timer
  configurations and three interrupt cases with synthetic registers. The stock
  setup routine cannot provide 1 ms ticks by passing argument one.

Optional YC3121 printer comparison uses the D110/B1 files pinned in
`docs/evidence/references.json`, placed under ignored
`research/downloads/niimbot-reference/`:
`.venv/bin/python tools/inspect_printer_reference.py`. It verifies shared radio
patch bytes and emulates D110's packet builder with registration, IPC and time
stubs. Results go to `build/references/niimbot.json`. Printer addresses and limits
are comparison evidence only; this does not validate Zero 2 notification delivery.

The [binding investigation](docs/radio-binding.md) records the confirmed `0x09`
dispatch, reconstructed runtime service, input path and IPC exact-fill issue.
Its immediate blocker is matching radio ROM/SDK evidence for notification
acceptance and CCC lifecycle; those routines are outside the update image.

Read [findings](docs/findings.md), [the proposed protocol](docs/protocol.md), and
[remaining firmware work](docs/plan.md) before binding or packaging a patch.
