Installs the Glassly firmware on the 8BitDo Zero 2, 8BitDo Micro, IINE Gamebrick Mini, IINE Ananke Gen 2 and MemoMind One glasses, or puts the official firmware back where that has been verified. The firmware is built in; nothing is downloaded while flashing.

| Computer | Download |
| --- | --- |
| Mac with Apple silicon | `Glassly-CFW-Flasher-macOS-AppleSilicon.dmg` |
| Mac with Intel | `Glassly-CFW-Flasher-macOS-Intel.dmg` |
| Windows 10/11, 64-bit | `Glassly-CFW-Flasher-Windows-x64.exe` |
| Linux, x86_64 | `Glassly-CFW-Flasher-Linux-x86_64` (`chmod +x` it, then run it) |

First launch: on macOS use **System Settings > Privacy & Security > Open Anyway**; on Windows choose **More info > Run anyway**. Neither build is code-signed yet.

Experimental firmware: a failed flash can leave a controller unusable. Windows and Linux have not been tried against a real controller yet. The MemoMind One image, Glassly revision 27, has passed the firmware's offline regression and emulator suites and has not yet been flashed on glasses. MemoMind One glasses are accepted on any official or Glassly firmware version. See the [README](https://github.com/tetramo-labs/glassly-cfw-flasher#flash-a-controller) for the steps for each controller.
