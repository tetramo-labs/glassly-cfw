# Glassly 8BitDo Zero 2 firmware

Custom firmware for the **8BitDo Zero 2 (YC3121)** that streams all twelve buttons
and simultaneous presses over BLE GATT for the Glassly App.

## Flash and pair

Follow the **[macOS flashing guide](docs/flashing.md)** to build the pinned image,
enter USB update mode, flash with automatic backup/readback, and pair in Glassly.
The installable image is `buttons-probe`; the standalone C objects are research
components, not firmware images. OEM firmware and generated binaries stay local.

After flashing, turn on the controller and hold **Select for three seconds**.
In a Glassly build with Zero 2 support, choose **Controllers → 8BitDo Zero 2** and
select your unit. The radio advertises `80EL`; Glassly displays `Zero 2` with a
short per-unit suffix. Pair inside Glassly, leaving it unpaired in phone settings.

## Verified status

- Custom flash, full 73,216-byte application readback, and normal USB reboot.
- All twelve button press/release pairs and A+B over FF10 / FF13.
- Battery A press/release and 187.95 seconds connected without keepalive writes,
  including 166.26 seconds idle after release.

The current build also keeps the LED steady while a BLE host is connected, as
stock does for a connected host. That change is checked in emulation only and has
not yet been flashed.

This is experimental firmware tested on one YC3121 unit. Flashing can brick a
controller. iPhone background/locked delivery and long-term battery life still
need hardware validation; the earlier macOS captures do not establish them.

## Development

- [Flashing and returning to stock](docs/flashing.md)
- [Button protocol, placement and hardware evidence](docs/buttons-probe.md)
- [Findings](docs/findings.md) and [remaining work](docs/plan.md)
- [Earlier probes and analysis commands](DEVELOPMENT.md)
- [Pinned sources](sources.lock.json) and vendored MIT-licensed
  [8cryptdo](third_party/8cryptdo/README.md)

The stock package includes GD32 and Yichip sections; this port patches the
validated Yichip path and preserves the GD32 section. The catalog MD5 mismatch is
recorded in the source lock: SHA256 pinning ensures reproducibility, not vendor
authentication. Backups, ROM dumps and downloaded OEM files are never published.
