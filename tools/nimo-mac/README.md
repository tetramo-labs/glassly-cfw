# nimo (macOS probe)

CoreBluetooth command-line tool for the NIMO glasses. It speaks the stock 0xBF
protocol on service 0x7033 (write 0x2021, notify 0x2022) and records every
frame it sends or receives under `captures/` as JSON evidence.

```sh
swift build --package-path tools/nimo-mac -c release
tools/nimo-mac/.build/release/nimo scan 12
tools/nimo-mac/.build/release/nimo probe            # handshake, version, battery, screen info
tools/nimo-mac/.build/release/nimo layout --seconds 15   # also shows the golden Dynamic Layout frame
```

The glasses advertise only their `Nimo-XXXX_BLE` notification companion over
LE (one vendor service, no 0x7033). The data channel is GATT over the classic
link, so the Mac must be paired with `Nimo-XXXX` in System Settings first; the
tool then picks the system-connected peripheral up without scanning. The host
terminal needs Bluetooth permission.
