# Glassly Ananke CFW

Custom firmware and a USB flash tool for the **IINE Mini Retro Ananke Gen 2**, Purple / Gray / Cream Yellow group (L1254/L1255/L1277). Based on the matching official **IG05_V0900** release. It sends all 16 buttons over a vendor BLE notification stream for Glassly.

This is experimental firmware. Installation and full readback, normal BLE boot, and all 16 button mappings have been verified on one controller using macOS. Independent recovery after a broken application has **not** been demonstrated; a failed installation may leave the controller unusable. Normal HID coexistence, standby/wake, and real iPhone background/locked behavior remain unverified. The installer requires explicit acceptance of that risk.

The six-button Gamebrick Mini uses a different [firmware and tool](https://github.com/tetramo-labs/glassly-gamebrick-mini-cfw). Do not interchange images. V0901 is for another Ananke variant and is rejected.

## What is included

- Custom firmware source, a 562-byte compiled patch payload, pinned hashes, and the [observed button protocol](docs/button-protocol.md).
- `research/flash_ananke.py`: identify, back up, install, or restore the official V0900 application.
- A per-device image builder that checks the bootloader, configuration, installed application and complete measured partition layout. Different layouts or unknown firmware stop before erasure.
- Two complete matching backup reads before every installation, application-only sector writes, page/sector verification, and a final full-flash comparison. Calibration, pairing, settings, keys, bootloader and inactive partitions stay intact.

**OEM firmware, device dumps and device keys are not distributed.** Obtain the official `IG05_V0900.ufw` from IINE's [firmware support directory](https://u5tqxzj1yb.jiandaoyun.com/dash/645b138d99c8b800089e8fc5). Expected SHA256: `64f9dd8390ccfb5b63cba971f73f09228fbd0a3cdba13eab7dcdd502757e0fd3`. The installer verifies it before accessing USB. Do not run the OEM updater alongside this tool.

## Platform support

| Platform | Transport | Validation |
| --- | --- | --- |
| macOS | Native IOUSBHost helper | Live backup and both CFW installations verified |
| Windows | PyUSB / libusb with WinUSB | Implemented; offline transport gates tested; hardware untested |
| Linux | PyUSB / libusb | Implemented; offline transport gates tested; hardware untested |

Windows and Linux use the same strict USB status, pinned-loader, readback and write-range checks as macOS. The new public CLI reproduces the hardware-verified images offline; its Windows/Linux paths are not claimed as hardware validated.

## Setup

Install Git and Python 3.10 or newer. Clone this repository:

```sh
git clone https://github.com/tetramo-labs/glassly-ananke-cfw.git
cd glassly-ananke-cfw
```

### macOS

Install Apple's command-line tools (`xcode-select --install` if needed), then:

```sh
python3 scripts/setup.py
```

Setup creates `.venv`, fetches the exact dependency revisions in `sources.lock.json`, verifies the BR23 RAM loader, and compiles the native USB helper. It does not access a controller.

### Windows

Use PowerShell with Python and Git available:

```powershell
py -3 scripts/setup.py
```

Install a matching-architecture `libusb-1.0.dll` from the [official libusb releases](https://github.com/libusb/libusb/releases) in a directory on your `PATH`. Put the controller in update mode as described below. Use [Zadig](https://zadig.akeo.ie/) to assign **WinUSB only to the update-mode `4C4A:2342` controller**. Check its USB ID before replacing a driver; leave the normal `4353:800C` HID device alone. See libusb's [Windows driver documentation](https://github.com/libusb/libusb/wiki/Windows#driver-installation).

### Linux

Install Python, venv support, Git and libusb (Debian/Ubuntu: `sudo apt install python3 python3-venv git libusb-1.0-0`), then:

```sh
python3 scripts/setup.py
```

The tool claims only the selected controller interface and temporarily detaches its kernel driver when needed. Run the USB commands below with sudo, or configure a narrowly scoped device permission rule yourself.

## Enter update mode and identify the target

1. Power off the controller and unplug USB.
2. Hold **Capture + Home** while connecting it with a USB data cable.
3. Release the buttons. Update USB must be `4c4a:2342` / `BR23UBOOT1.00`.

This is different from Bluetooth pairing. Never copy another computer's port identifier.

On macOS, run `system_profiler SPUSBDataType` and find the **Location ID of `4c4a:2342`**, then identify it. Replace the example location with yours:

```sh
sudo .venv/bin/python research/flash_ananke.py identify --location 0x02100000 --wait 3
```

On Windows, list the available update devices, then use the displayed decimal `BUS:ADDRESS`:

```powershell
.\.venv\Scripts\python.exe research/flash_ananke.py --list
.\.venv\Scripts\python.exe research/flash_ananke.py identify --device 1:2 --wait 3
```

On Linux:

```sh
sudo .venv/bin/python research/flash_ananke.py --list
sudo .venv/bin/python research/flash_ananke.py identify --device 1:2 --wait 3
```

`identify` sends only SCSI INQUIRY; it does not upload a loader or write flash. Recheck the target after reconnecting, especially on Windows/Linux where the address can change. If enumeration lacks a usable bus/address, stop; no automatic target fallback is provided.

## Install

Run the command for your platform **in your interactive terminal**, with your explicit target and the path to your official file. Close other software using the controller and keep USB connected until verification finishes.

macOS:

```sh
sudo .venv/bin/python -u research/flash_ananke.py install --location 0x02100000 --wait 3 --ufw /path/to/IG05_V0900.ufw --accept-unrecoverable-risk
```

Windows:

```powershell
.\.venv\Scripts\python.exe -u research/flash_ananke.py install --device 1:2 --wait 3 --ufw "C:\path\to\IG05_V0900.ufw" --accept-unrecoverable-risk
```

Linux:

```sh
sudo .venv/bin/python -u research/flash_ananke.py install --device 1:2 --wait 3 --ufw /path/to/IG05_V0900.ufw --accept-unrecoverable-risk
```

The tool uploads only the pinned 11,264-byte BR23 loader to RAM and verifies all 22 blocks before running it. It requires the observed 1 MiB `856014` flash identity, saves two matching full reads, validates a per-device plan, and writes only changed 4 KiB application sectors, with the header sector last. It never erases the whole flash or programs fuses. Every transfer has a 10-second timeout and the session has a bounded watchdog.

Success ends with **FLASH VERIFIED**. Disconnect USB and power-cycle normally. No reset command is sent. If a checksum, identity, status or readback check fails, stop and retain the output directory; incomplete captures are kept and marked incomplete. Do not repeatedly erase or try another controller's image.

## Pair with Glassly

1. Hold **Pair + D-pad Right** to enter HID BLE pairing; LEDs 2 and 3 flash. Pair is on the bottom edge near the lanyard hole.
2. In Glassly, add **IINE Ananke Gen 2**, continue, and select your Ananke. Its BLE name is `IG05 Gamepad(BLE)`.
3. If you used the previous Pro Controller / system-gamepad integration, forget the old controller in Glassly and add it again. The app now identifies the actual BLE peripheral.

A taps/holds, B goes back, and the D-pad navigates. All 16 buttons expose indexed press/release/hold events to miniapps. The phone driver must understand the eight-byte v2 protocol; Gamebrick's four-byte decoder is incompatible. iPhone background/locked tests are still required; Mac notification captures are not proof of iOS behavior.

## Backups and restoring stock

Use `backup` instead of `install`, omit `--ufw` and the risk flag, and keep the same platform target arguments. It makes two full immutable reads without modifying flash. Each output folder is private and Git-ignored under `research/flash-attempt-*`.

Verify either a new CLI backup or an original research backup offline:

```sh
python3 scripts/verify_backup.py research/flash-attempt-YOUR-RUN
```

On Windows use `py -3` instead of `python3`. Copy verified backups to another safe local location; they contain device keys and settings. Keep both reads and `backup.json` together. `metadata.json` describes the complete session, including any later installation failure.

To restore the **official V0900 application**, re-enter update mode, identify the current target, and replace `install` with `restore` in the installation command, retaining `--ufw` and the risk flag. This keeps current settings and partition layout. It does not restore the entire original 0x0601 dump or demonstrate recovery from a controller that cannot enter update mode.

## Development and evidence

```sh
.venv/bin/python -m unittest discover -s research -p 'test_*.py'
```

Use `.\.venv\Scripts\python.exe` on Windows. Tests requiring private OEM files or original dumps skip when those fixtures are absent. Pure protocol, USB-status and sector-writer tests do not access hardware. `scripts/build-candidate.sh` rebuilds the patch using the pinned Jieli pi32v2/r3 toolchain and Docker; its historical analysis inputs are described in [custom firmware notes](docs/custom-firmware.md).

The earlier `research/flash_controller.py` remains a historical one-unit installer, not the public entry point. See [findings](docs/findings.md), [current plan](docs/plan.md), [protocol](docs/button-protocol.md), and [latest flash evidence](docs/evidence/flash-wakeup-fix-20261104.json).
