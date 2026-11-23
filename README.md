# Glassly Flash Tool

Glassly Flash Tool installs firmware that lets you use a supported controller or pair of smart glasses with the Glassly App on iOS and Android. You can also use it to restore the official firmware. The desktop download includes the firmware for each supported device.

## Supported devices

| Device | Connection | Compatible models and starting firmware |
| --- | --- | --- |
| 8BitDo Zero 2 | USB | YC3121 board with official firmware v1.08 |
| 8BitDo Micro | USB | Official firmware v1.05 |
| IINE Gamebrick Mini | USB | L1161 or L1162 from the supported 2025 production run, with factory firmware or the official IINE update. The tool checks your unit and offers backup and recovery for newer models. |
| IINE Mini Retro Ananke Gen 2 | USB | Purple, Gray or Cream Yellow (L1254, L1255 or L1277) with official firmware V0900 |
| MemoMind One | Bluetooth | H001Y or H001F glasses with official or Glassly firmware |

<a id="flash-a-controller"></a>

## Quickstart

1. **Download the tool for your computer.** On Mac, choose the Apple silicon or Intel disk image and drag the app into Applications. On Windows, run the 64-bit executable. On Linux x86_64, make the downloaded file executable and open it. [Download the latest release](https://github.com/tetramo-labs/glassly-cfw/releases/latest)
2. **Choose your device** and select **Install the Glassly firmware**. For a controller, use a USB data cable and follow the on-screen instructions for entering update mode. For MemoMind One, charge the glasses and follow the Bluetooth setup instructions in the tool.
3. **Acknowledge the flashing risk and select Start.** Keep the controller connected or the glasses near your computer until the tool confirms installation.
4. **Pair with the Glassly App.** For a controller, open **Controllers** in the Glassly App and select your model. For MemoMind One, pair the glasses in your phone’s Bluetooth settings first, then add them in the Glassly App.
