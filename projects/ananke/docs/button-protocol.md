# Ananke custom GATT button protocol

Live captures on this IINE Ananke Gen 2 confirm the custom stream on service **AE40**, notify characteristic **AE42**. This protocol is specific to this firmware; it is not the stock protocol or Gamebrick packet format.

Each notification is exactly eight bytes: `47 02 sequence flags keys32LE`. Bytes 4–7 contain the complete raw button-state mask in little-endian order. Sequence increments modulo 256. Flag bit 0 means queue overflow; bit 1 marks a fresh subscription/session snapshot. A zero mask means all buttons released. Treat baseline/overflow packets as state synchronization rather than inventing missed transitions.

| Button | Raw mask |
| --- | --- |
| A | `0x00000001` |
| B | `0x00000002` |
| X | `0x00000008` |
| Y | `0x00000010` |
| Up | `0x00010000` |
| Down | `0x00020000` |
| Left | `0x00040000` |
| Right | `0x00080000` |
| L | `0x00000040` |
| ZL | `0x00000100` |
| R | `0x00000080` |
| ZR | `0x00000200` |
| Capture | `0x00008000` |
| Home | `0x01001000` |
| Minus | `0x00000400` |
| Plus | `0x00000800` |

Home drives two raw bits together; decode them as one logical Home button, not two events. Other mapped buttons use one bit. For a normal packet, compare the logical current state with the previous state to derive presses/releases. Preserve unknown raw bits for diagnostics.

All 16 mappings were established through user-confirmed button sequences. The corrected firmware produced separate arrivals for all ten A/B/shoulder/system taps, with no sequence gaps. This fixes the observed long batching in that test; precise physical-to-host latency has not been measured.

Machine-readable masks and capture references are in [button-map evidence](evidence/ananke-button-map.json). The first image omitted the OEM Bluetooth-task wake after queue insertion; the corrected `574f6542…` candidate includes it and is installed with current settings preserved.

Normal HID coexistence, standby/wake and actual iPhone background/locked operation require separate validation.
