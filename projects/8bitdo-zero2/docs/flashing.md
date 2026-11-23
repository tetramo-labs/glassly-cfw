# Flashing the Zero 2

This guide uses the native **macOS** script and the tested **YC3121 Zero 2 / v1.08**
firmware path. Windows/Linux flashing and other board variants are not validated.
The experimental `buttons-probe` image can brick a controller. Keep the automatic
backups; the script is not a general recovery flasher.

## 1. Prepare the build

Install Python 3 and Xcode Command Line Tools (`xcode-select --install` if absent).
Clone the source, download the pinned stock image, and run the offline checks:

```sh
git clone https://github.com/tetramo-labs/glassly-8bitdo-zero2-cfw.git
cd glassly-8bitdo-zero2-cfw
python3 scripts/fetch_stock.py
python3 tools/inspect_stock.py
python3 scripts/check.py
python3 tools/build_buttons_probe.py
python3 -m venv .venv
.venv/bin/pip install -r requirements-analysis.txt
.venv/bin/python tools/inspect_buttons_probe.py
python3 scripts/flash.py buttons-probe
```

These commands do not open or write to the controller. The final command prints
an offline flash plan. The built package is
`build/buttons-probe/Zero2-v1.08-buttons-probe.dat`, SHA256:

```text
007ca4b94e765ba20bfeb7aaaf7728c14a741b6bac821d74932084b8536334a8
```

This revision adds the steady connected LED and has only been checked offline;
the hardware results so far are from the previous package `a64e0b6e…`, which the
flasher still accepts and recognizes as an installed baseline.

The downloader rejects changed size/SHA256. Its catalog-MD5 warning is expected
and documented in `sources.lock.json`; do not bypass a SHA256 failure.
`build/button_stream.arm.o` and `build/button_input.arm.o` are **not flash images**.

## 2. Enter update mode and identify the USB port

Close the 8BitDo updater and any other controller tools. Use a USB data cable.

1. Unplug USB and hold Start for three seconds to power off.
2. Hold both shoulder buttons **L + R**, then press **Start**.
3. When the update light blinks, release the buttons and reconnect USB.
4. Run `python3 tools/inspect_usb.py`.

The tested update interface is `2dc8:3208`. `2dc8:9018` is normal runtime mode;
retry the sequence if that is what the tool reports. A blinking LED alone is
not confirmation. The flasher also checks the report descriptor and queries boot
product `0x9018`; shared 8BitDo bootloader IDs alone are insufficient.

Read the USB location from the most recent local registry capture:

```sh
python3 - <<'PYCODE'
import json
from pathlib import Path
capture = sorted(Path('build/hardware').glob('*/target-registry.json'))[-1]
for device in json.loads(capture.read_text()):
    if (device.get('idVendor'), device.get('idProduct')) == (0x2dc8, 0x3208):
        print(device.get('USB Product Name'), hex(device['locationID']))
PYCODE
```

Use that hexadecimal value below. Do not copy another controller's location.
Keep the same cable/port between inspection and flashing; connect only the Zero 2
being flashed.

## 3. Flash and verify

Replace `USB_LOCATION` with the observed value, such as `0x02100000`:

```sh
python3 scripts/flash.py buttons-probe --location USB_LOCATION --apply
```

`--apply` performs the write. The script backs up the current application and
4,096-byte metadata page, accepts only known image hashes and version 108, erases
and writes the encrypted Yichip section, compares all 73,216 plaintext bytes,
then commits/verifies version 108 and reboots. Keep USB connected until it exits.

Success is **exit code 0**. The printed transaction directory under
`build/hardware/` contains `result.json`, `transport.log`, `before-application.bin`,
`before-metadata.bin`, and source/input snapshots. Preserve that directory locally.
Run `python3 tools/inspect_usb.py` again: the tested image returns in normal mode
as `Glassly Zero 2 test01`, `2dc8:9018`.

If it reports **Unexpected installed baseline**, it saved a backup and did not
erase. Factory units may have a different version or a nonzero application tail.
Preserve the backup, use the official 8BitDo Firmware Updater to install stock
Zero 2 **v1.08**, close it, re-enter update mode, and inspect again. This stock
reflash was required and verified on the development unit. Do not substitute
another version or change the script's hash checks. If v1.08 is unavailable or the
baseline still differs, stop and inspect the captured evidence.

If writing or readback fails, retain the entire transaction directory. There is
no automatic retry or forced recovery mode. An interrupted/unknown image will be
rejected by this script; availability of vendor recovery is not guaranteed.

## 4. Pair in Glassly

Unplug USB, turn on normally, and hold **Select for three seconds** until the LED
blinks rapidly. In a Glassly build containing Zero 2 support, open controller
pairing, choose **8BitDo Zero 2**, then select **Zero 2 …**. Do not pair through
phone Bluetooth settings. Close any Mac diagnostic first so it releases the BLE
connection.

The radio name is `80EL`. Glassly subscribes to FF13 under FF10 and sends `A1` to
start the v4 stream; notification subscription alone does not start buttons.
It waits for the start acknowledgement and baseline before reporting connected,
and sends `A0` when disconnecting. D-pad navigates, A taps/holds, B goes back;
other buttons send indexed taps/holds. Select and Start retain their stock
long-press power/pairing behavior.

Optional Mac check, without Glassly connected:

```sh
python3 scripts/ble_probe.py scan --seconds 30
python3 scripts/ble_probe.py buttons --identifier OBSERVED_UUID --seconds 180
```

Use the UUID observed in your scan. The Mac may request Bluetooth permission.
The diagnostic sends A1/A0 and records notifications under `build/hardware/`.
This is not an iPhone background-delivery test.

## Return to stock

Re-enter USB update mode and inspect the location again, then run:

```sh
python3 scripts/flash.py stock
python3 scripts/flash.py stock --location USB_LOCATION --apply
```

This reinstalls the pinned stock v1.08 package from a recognized baseline with
the same backup/readback checks. It removes the custom BLE stream; it does not
restore arbitrary historical metadata or promise recovery from a partial flash.
