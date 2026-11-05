# Zero 2 firmware findings

Updated 2026-11-05. The user has now authorized experimental firmware flashing,
accepting the risk of bricking controllers, starting with stock or a minimal change.
USB identification and bounded application /
ARM ROM readback have succeeded. Stock reflash and a name-only custom flash have
now also succeeded, with complete application readback and runtime USB checks.
Earlier emulation work below remains offline evidence; no protection change was made.

## Verified stock and custom flashing (2026-11-05)

The official macOS updater 2.5.2 build 5 passed codesign and notarization checks
outside the sandbox and reflashed v1.08. It showed `Update complete`, and runtime
USB returned as `2dc8:9018`. Independent subsequent readback matched the entire
73,216-byte pinned Yichip section, SHA256
`e661156ba9871167ab0ab7e40d05ee573a07581e5c5157c6e195ff3a5c4823b0`.
The official updater overwrote the original nonzero 508-byte tail with stock
zeros. The original tail remains in the earlier local backups. This observation
does not establish its purpose or that overwriting it preserves all settings.

At the user's request, the local REA checkout at revision
`d48e472fa6a664cacbb400560e673533005795ce` inspected the macOS updater's Objective-C
metadata. Evidence `ev_321378fbae9caf40aa718dd27cb1788391f22ca1da7fb93f7014dd92087b93b0`
provides the method anchors. No deep provider was configured; native `otool`
disassembly and isolated Unicorn execution supplied the protocol details.
This is not a claim that REA decompiled or observed the updater's execution.

For product `0x9018`, the native PID dispatcher selects boot type 20. The
`SHIDBootPro2` methods establish this sequence:

| Operation | Command | Address/extent | ARM64 anchor |
| --- | --- | --- | --- |
| Erase application | 4 | `0x01018000`, 73,216 bytes from selected header | `0x100008224` |
| Erase version record | 4 | `0x01017040`, 32 bytes | `0x10000870c` |
| Write ciphertext | 3 | `0x01018000 + offset`, up to 46 bytes per request | `0x100008924` |
| Write version | 2 | `0x01017040`, LE32 108 | `0x1000093dc` |
| Reset | 7 | zero address/length | `0x100009688` |

Packet constructor `0x100006d74` places command/parameters/length/CRC/total/address
at byte offsets 1/3/5/7/9/13, payload at 17, leading byte 5. CRC is MODBUS
initial `ffff`, polynomial `a001`; this macOS constructor includes the zero-filled
requested bytes when computing CRC for reads. Earlier Windows-derived reads
used `ffff`; both forms succeeded on this unit. `0x100022c38` sends 64-byte HID
output reports with report ID zero. Response validation at `0x100006f60` checks
`00 05`, status zero and matching command. The native writer advances its file
offset only after that acknowledgement. `tools/inspect_macos_updater.py` verifies
eight native packet cases and four erase/version/reset argument cases offline.

`tools/build_name_probe.py` replaces only the 21-byte string at Yichip offset
`0x117cc`: `8BitDo Zero 2 gamepad` becomes `Glassly Zero 2 test01`. The initialized
pointer at `0x206a0` references this string, and USB callback `0x010221c0` converts
it through `0x01021320`. Twenty actual stock/patched callback cases verify USB
descriptors offline. It is shared model data; Bluetooth naming may also change.
No instructions, RAM layout, stream component, radio table, package header or
GD32 section change. The independently decoded package is pinned by SHA256
`f0938c2b6a6bb0186d948a6ac9655153111927267188fb1ec32a08ee739b2f20`.

Our `scripts/flash.py` / `tools/flash_zero2.c` successfully flashed that package
after backing up the application and `[0x01017000, 0x01018000)` metadata page.
It verified all 73,216 plaintext bytes before committing version 108, read the
version back, and reset. Readback SHA256 is
`8a1725b90710223d073754583de314552c6dce8a468cc09633a156c23a079050`.
The application differs from the immediately preceding stock image only at
`0x117cc` through `0x117e0`; all 4,096 metadata bytes match before/after.
macOS then enumerated product **`Glassly Zero 2 test01`**, VID/PID `2dc8:9018`,
with the stock HID descriptor. This proves boot and the minimal patch, not button
functionality, BLE notification delivery or Glassly background behavior.

Exact source hashes, local transaction path and verification metadata are in
`evidence/name-probe-flash.json`; updater identity, REA provenance and emulated
packets are in `evidence/macos-updater.json` and `evidence/macos-updater-protocol.json`.
The flasher admits only pinned stock/name-probe input pairs and installed
baselines. It has no arbitrary address mode or automatic retry; unexpected
responses stop the operation without committing/resetting. Failed or unknown
baselines need a separate recovery workflow.

## Button streaming image: flashed and baseline received

The user requested button streaming in the next flash. `buttons-probe` replaces
four complete calls and reduces the first OEM pool from three to two 600-byte
blocks, reserving 48 bytes of state in the removed block. Its 364-byte tail code
samples before OEM reporting gates, qualifies whole masks on two consecutive
polls, queues 16 snapshots and waits for command-09 acknowledgement between sends.
An explicit A1 start after subscription / A0 stop before unsubscribe supplies
host subscription intent; reconnect and disconnected sampling reset the stream.
This does not claim the radio's CCC callback has been recovered.

All 4,096 GPIO combinations, 2,048 capacity/IRQ cases and 12,000 independent-model
polls pass offline, as do the 29 Python checks, sanitized suites and Swift packet
parser checks. Package/header extents, GD32 and startup contents are unchanged.
The packet uses version 4 to distinguish this sample-based experiment from the
unbound version-3 C components. At 21:23 UTC the native flasher installed the
image, verified all 73,216 bytes and reset. All 4,096 metadata bytes are unchanged;
348 bytes differ from the notification probe, restricted to reviewed hooks, pool
count and tail. Runtime USB returned normally. See `evidence/buttons-probe-flash.json`.

At 21:24 UTC BLE discovery/subscription succeeded, A1 was acknowledged and FF13
delivered baseline `4704000200000000`: version 4, sequence zero, baseline flag,
all buttons released. This proves the eight-byte sender and polling wrapper
execute on hardware. The session stayed connected for 187.590 seconds with USB
connected and ended intentionally after A0 was acknowledged. Only that baseline
arrived; the user had not yet confirmed performing the requested tap sequence.
A subsequent reconnect produced another sequence-zero baseline and acknowledged
A1/A0 across a 30.989-second hold. Both captures have ended; no physical button
transition was recorded. See `evidence/buttons-probe-gatt.json`.
See `buttons-probe.md`, `evidence/buttons-probe.json` and
`evidence/buttons-probe-emulation.json` for placement, lifecycle, limits and hashes.

### Physical press/release stream verified

At 21:46 UTC the user repeated A, B, X, Y, Up, Down, Left, Right, L, R and
Select in the requested order. The receiver captured a baseline and all eleven
press/release pairs, sequence 0 through 22. A subsequent brief Start tap produced
`0x0001` then zero, sequences 23–24. Holding A+B produced `0x3000` then zero,
sequences 25–26. The user confirmed both test sequences. All 27 packets have
consecutive sequence numbers, no gaps and no overflow flags. This demonstrates
GPIO sampling, queued transitions, acknowledgement-gated progress and actual
BLE delivery on this controller, not merely the baseline or IPC insertion.

The resulting twelve-button mapping is in `buttons-probe.md` and
`evidence/buttons-probe-mapping.json`. The diagnostic now decodes labels from
this evidence and retains raw masks. Its decoder checks and all 29 Python checks
plus sanitized suites pass. This host change does not alter the flashed image.

The capture later recorded extra button activity outside the ordered test and
ended with a connection timeout during the requested unplug/restart transition.
The user confirmed restarting on battery; the exact disconnect cause is not
isolated. A fresh battery connection is being tested separately. No iPhone or
Glassly background result, long-term battery-life measurement or radio-overflow
stress result is claimed.

## Initial hardware identification

### BLE visibility experiment (flashed and verified)

The new `tools/inspect_ble_setup.py` audit captures a separate startup command
04 name: `80EL` plus ten zero bytes, length 14. It is unchanged in the stock,
name-only and BLE-probe images. The visibility wrapper at `0x0101a304` overwrites
its third argument with zero at `0x0101a310`, forcing command-02 bit 2 clear.
Related YC1021 and YC1121 sources identify bit 2 as BLE advertising enable;
the matching Zero 2 ROM implementation is still unavailable.

`tools/build_ble_probe.py` builds a complete experimental image that changes
`movs r6,#0` to `movs r6,#1` at that address, on top of the verified name-only
image. Only section byte `0x2310` differs from that image. Both headers, the
GD32 section, startup copies, RAM layout, instruction sizes and stack frame
remain unchanged. Package SHA256:
`c51e350561aa51130b552efbaa64b3b5c2547731947001a0255ac36e60f43e59`;
Yichip plaintext SHA256:
`2c86e745cfadb4df8692c58bb1747bd9e957ecfc999f6501cd6450cd2b83fe22`.
It forces the flag on every wrapper call, including stop-visibility requests;
radio acceptance, power, sleep, coexistence and reconnect need hardware testing.
It contains no custom button stream. The native flasher now pins this exact
package/plaintext pair and accepts it as a baseline for restoration too.

Nine startup-name cases and sixteen stock/probe visibility cases execute the
actual Thumb builders in Unicorn, stopping before IPC insertion. The startup
hardware initializer is stubbed and NVIC registers are synthetic RAM. These
checks establish command construction only. Reports and source hashes are in
`evidence/ble-probe.json` and `evidence/ble-setup-emulation.json`.

`scripts/ble_probe.py` builds a macOS CoreBluetooth diagnostic for candidate
scanning, exact-UUID GATT discovery and FF10/FF13 subscription. It preserves
sources and raw events locally; subscription success and notification delivery
are separate outcomes. The first two bounded scans found no candidate while
the latest USB observation still showed the name-only runtime. The first scan
only matched Zero 2 names; the second added `80EL` and advertised FF10. This is
not evidence that BLE is absent in wireless mode. At that stage, no GATT
connection or subscription had been observed; the visibility-probe flash below
was the subsequent experiment.

At 20:03:56 UTC the user reported normal wireless pairing mode with rapid LED
blinking; concurrent registry inspection found no target USB device. A scan
requested for 45 seconds ended after 47.25 seconds with zero matching BLE
candidates. CoreBluetooth reported powered-on state and allowed authorization.
No connection, subscription or firmware operation was attempted. This is a
wireless baseline for the name-only image, not proof of the cause or absence
of differently named advertisements. Evidence: `evidence/ble-wireless-baseline.json`.

`python3 scripts/check.py` now also compiles the Swift diagnostic without
opening Bluetooth; the image checks pin the one-byte delta and exact package.

At 20:06 UTC our native flasher installed the BLE visibility probe. All 73,216
plaintext bytes matched the expected image before version commit/reset. Comparison
with the transaction backup finds exactly one changed byte, section offset
`0x2310`; all 4,096 metadata bytes are identical. Source snapshots match the
transaction's recorded hashes. Runtime USB returned at 20:07:05 as
`Glassly Zero 2 test01`, `2dc8:9018`, with the stock HID descriptor. See
`evidence/ble-probe-flash.json` for the exact hashes and local backup path.

With USB still connected, the next scan immediately found connectable `80EL`.
A targeted connection discovered service `0000FF10-0000-1000-8000-00805F9B34FB`,
characteristic `0000FF13-0000-1000-8000-00805F9B34FB` with properties `0x18`
(write/notify), and descriptor `2902`. A subsequent connection successfully
enabled notifications. This matches the static startup analysis and supports
the bit-2 advertising interpretation on this unit. CoreBluetooth does not expose
ATT handles, so no numeric runtime handle is claimed. This image does not send
custom button packets; subscription success is separate from data delivery.
At that stage, battery-powered operation, CCC reset ordering and reconnect
remained unverified; the battery test below adds an observed failure boundary.
The bounded subscription capture remained connected/subscribed for 94.24 seconds
and received zero notifications before our diagnostic disconnected intentionally.
No vendor characteristic value was written. Raw captures remain local; reviewed
events with the peripheral identifier omitted are in `evidence/ble-probe-gatt.json`.

### Battery test: subscription succeeds, then connection times out

At 20:23 UTC the user confirmed USB unplugged and rapid pairing LED blinking;
registry capture found no target USB device. The same `80EL` identifier advertised,
connected, exposed FF10/FF13/2902 and accepted notification subscription. After
61.097 seconds connected, CoreBluetooth reported `The connection has timed out
unexpectedly.` No notifications were received. A subsequent 30-second requested
scan for that exact identifier found nothing, so reconnect and subscription
cycling were not exercised. See `evidence/ble-battery-baseline.json`.
The user subsequently reported the LED was **off**, before any requested button
presses. This supports shutdown rather than just a host-side disconnect, but
does not identify the firmware path or rule out another power-related cause.

The cause is not established. The stock sampler increments idle counter
`0x20198` through `0x0101ee50` when its report task returns zero, then calls
`0x0101db3c`. That function compares the counter with `0x20194`; its guards use
HID state `0x20182`, `0x201b8` and the mode predicate `0x0101f0a0`, without
reading BLE state directly. A separate threshold setter `0x01022938` does
consider BLE state, and another startup path writes threshold 6000. These are
code observations, not proof that this exact timeout is idle shutdown; neither
the active threshold nor physical shutdown has been measured.

The diagnostic now has `cycle` mode (subscribe, unsubscribe, resubscribe) and
`keepalive` mode (one zero byte written with response to FF13 after subscribing,
then 20 seconds after each acknowledgement). Existing `subscribe` mode still
sends no vendor value. The unmodified event-08 handler with the concrete
handle-plus-zero payload was executed offline: it consumes the event, cancels
the BLE watchdog and clears the idle counter. Exact substitutions and source
hash are in `evidence/ble-keepalive-emulation.json`. This is a diagnostic,
not a firmware fix or Glassly integration. All 27 Python checks, native sanitized
suites and Swift compilation pass.

### Battery keepalive and reconnect results

After the user made the controller available again, the first connection lost
the link after 1.225 seconds, before subscription completion and before any
vendor value write. Its cause is unknown. A fresh targeted connection then
completed discovery/subscription and remained connected for **188.395 seconds**
with **nine acknowledged single-zero-byte FF13 writes**. USB registry again
showed no target device. The diagnostic ended that connection intentionally.
No notification was received; no button sender is present in this image.

The following connection rediscovered the same profile and completed an
acknowledged **enabled → disabled → enabled** notification subscription cycle,
holding the final state for five seconds before intentional disconnect. This
establishes reconnect and host-visible CCC toggling for that bounded test; it
does not establish radio callback ordering, stored CCC reset behavior or
notification delivery. Source snapshots, raw captures and reviewed events are
linked in `evidence/ble-battery-keepalive.json`.

Periodic writes prevented the earlier roughly 61-second shutdown in this run.
Because the stock handler both cancels the BLE watchdog and resets the idle
counter, the comparison does not isolate either mechanism. The next firmware
integration must handle idle/watchdog ownership alongside notification sending;
host keepalives are a diagnostic, not the intended Glassly protocol.

An additional offline audit executes 48 idle-guard and 24 threshold-setter cases,
without instruction substitutions, stopping before power-related I/O. It confirms
that the guard itself ignores BLE state while the threshold setter recognizes
BLE state 2. See `evidence/idle-emulation.json` and `radio-binding.md` for exact
inputs, addresses and limits. No live threshold, mode or shutdown path was read.

### Notification/idle probe: flashed and four notifications verified

`tools/build_notify_probe.py` builds a complete experimental image on top of the
verified BLE probe. It replaces the matched FF13 write handler's idle-reset call
at `0x01019918` with a bounded one-byte echo wrapper, and the sampler's idle
increment call at `0x0101be36` with a BLE-state-aware idle wrapper. The echo still
performs the original idle reset. The existing vendor-handle check and watchdog
cancellation remain intact. Any BLE connection suppresses idle counting and
cancels the watchdog in this experiment, regardless of subscription state;
disconnect restores the stock increment path. This is not final CCC ownership.

The wrappers use 220 bytes in the now-stock-cleared tail, no persistent RAM,
and 48/8-byte local frames. No unbound stream/input object is linked. The
placement audit, original-tail backup distinction and remaining hardware risks
are in `notification-probe.md`. Actual patched startup reconstructs exactly the
stock RAM without reading tail data. Full dispatcher and IPC execution passes
2,098 synthetic event cases, including dynamic handles, wrap, capacity rejection,
sleep skips and IRQ-mask restoration; four idle states pass too. No instruction
stubs or radio execution are used. Observed dispatcher-plus-callees stack is
904 bytes; this excludes main and exception nesting and is not a whole-device
worst-case bound. All 28 Python checks and native sanitized suites pass.

Package SHA256 is
`3a92dd60565e136a810fd0dc0148418c7b13cdb678eae66a5d5a8e2634369ed3`;
plaintext SHA256 is
`940d562d4552a35d70fa25538ef452708cd1fbed6e930eeb43d8eae720373aa5`.
The native flasher pins this pair and can restore known earlier images from it.
Metadata is in `evidence/notification-probe.json` and
`evidence/notification-probe-emulation.json`. `scripts/ble_probe.py echo` waits
for matching notifications and write acknowledgements for `31`, `a5`, `00`,
`ff`.

At 20:54 UTC the native flasher installed this exact package. All 73,216 bytes
matched readback; 104 bytes differ from the preceding BLE probe, all within the
two hooks and audited tail interval. All 4,096 metadata bytes match before/after.
The controller rebooted as `Glassly Zero 2 test01`, `2dc8:9018`, with the stock
HID descriptor. Exact source snapshots, input/output hashes and transaction
path are in `evidence/notification-probe-flash.json`.

With USB connected, the host subscribed to FF13, wrote `31`, `a5`, `00`, `ff`
one at a time, and received **four matching BLE notifications** as well as four
write acknowledgements. This establishes actual custom tail execution and the
tested command-09 dynamic LE16-handle plus one-byte data format on this unit.
Raw events and source hashes are preserved in `evidence/notification-probe-gatt.json`.
This is notification delivery, not merely IPC insertion. No button sender is
present, and larger payloads, FIFO pressure, CCC reset ordering and Glassly
background behavior remain untested. On battery at 21:01 UTC, USB registry showed no target. A subscribe-only session
remained connected for **188.448 seconds** with **zero vendor keepalive writes**,
then ended intentionally. A fresh battery connection received all four matching
echoes. The earlier roughly 61-second timeout did not recur in this bounded run.
Evidence: `evidence/notification-probe-battery.json`. Long-term power behavior
and button streaming remain untested.

### Original USB observation

The connected runtime device identifies as `2dc8:9018`, product `8BitDo Zero 2
gamepad`, with one HID interface (class 3, interface 0, two endpoints). Its HID
descriptor declares 9-byte input reports, 8-byte output reports, and no feature
reports. No DFU, serial or separate debug interface is exposed in the observed
runtime configuration. This does not exclude undocumented protocols.

The runtime PID matches the vendor updater's previously traced section-1
selection path. Its USB device revision field is `0x0200`, matching the Yichip
section descriptor at offset `0xf9ca`; section 0's descriptor at `0xc3d4` instead
uses `0x0001`. The HID report descriptor occurs identically in both sections
(`0xfa3b` and `0xc40f`), so it alone does not distinguish variants. USB revision
`0x0200` is **not** an observed firmware version of 2.00.

These initial observations supported targeting the Yichip variant; the later
readback below establishes the matching application prefix. User-provided PCB
photos show the chip marking `YC3121-L`; the radio ROM revision remains
unverified. Photo hashes and visual observations are recorded in
`evidence/pcb-identification.json`. No electrical pad mapping has been verified,
and the user has no multimeter or debug probe available. Raw
registry evidence, including unique identifiers, is local under ignored
`build/hardware/`. `tools/inspect_usb.py` reproduces registry capture without
opening devices or sending commands; shared bootloader IDs are only candidates.

The user entered the documented update mode after powering fully off. The
controller then re-enumerated at the same USB location as `2dc8:3208`, product
`8BitDo Boot`. Its HID descriptor has 64-byte input/output reports and no report
IDs. Earlier attempts had returned to the ordinary gamepad interface. The
updater had not been launched during this initial read-only investigation;
the later macOS stock reflash is recorded above.

### Verified read-only bootloader transport

The pinned Windows vendor DLL has a protocol gate at `0x10004f4e` that selects
its newer protocol for USB PID `0x3208`. Its address-read routine is at
`0x10009290`, packet constructor at `0x100091c0`, and product-code query at
`0x1000bef0`. The public fwupd legacy protocol is not used for these reads.
`tools/inspect_updater.py` executes the gate and packet construction in virtual
memory, with transport captured rather than executed. The resulting requests
are reproduced by the narrowly scoped macOS `tools/read_boot_version.c`.

The live helper requires the observed USB location, exact bootloader VID/PID,
product name, USB transport and report descriptor. It opens without seizing the
device. It has only fixed read/query modes; there is no arbitrary command,
memory write, erase, reset, protection modification or retry loop. Output HID
reports carry read requests; they are not flash writes. Standard checks now
include sanitized response-parser tests that never open hardware.

- Command 8 returned product code `0x9018` with successful status. This joins the
  runtime identity, bootloader identity and updater section-selection evidence.
- The vendor's generic four-byte version read at `0x08014034` returned status 1,
  which fails its success check. No version was inferred from those bytes.
- Command 5 at the pinned section entry `0x01018000` returned 32 bytes identical
  to v1.08. A subsequent 73,216-byte read saved the whole package-section extent
  in 32-byte chunks, validating command, status, echoed address/length and CRC.
- The first **72,708 bytes** (`0x11c04`) match the pinned v1.08 Yichip section
  exactly. The final **508 bytes** do not: 499 differ from the package's zero
  padding. Therefore the live whole-extent hash differs from the package hash;
  the executable/data prefix matches, not the entire flashed region.
- The known ARM ROM `INIT_OTP` entry at `0x442c` was readable. A bounded dump of
  `[0x4000, 0x6000)` recovered 8,192 bytes containing the SDK API routines.
  `READ_CHIPID` at `0x45d8` requests six bytes from OTP offset 2 through
  `READ_OTP` at `0x449c`. Its loop writes six destination bytes; the delay call
  at `0xc6` lies outside this initial dump; a later capture and offline audit
  now cover that callee, as described below.
- Independent second reads reproduced both dumps byte-for-byte. No firmware
  writes occurred. This is a backup of the specified application extent and
  ARM ROM window, **not a full-flash/recovery backup**.

Original reads, transport logs and hashes are under ignored `build/hardware/`.
The independently verified copies and exact reader source are in
`build/hardware/20261105T083257.692381Z-readback-verification/`. Raw device data
remains local. The separately executing Bluetooth radio ROM has **not** been
captured; locating its readable mapping is the next binding task. Do not
confuse ARM addresses `0x4xxx` with radio instruction indices `0x4xxx`.

### Extended ARM ROM capture and startup audit

The public YC3121 (BT) V1.7 datasheet, page 12, documents ARM ROM at
`[0, 0x8000)` and RAM at `[0x20000, 0x30000)`. Its repository revision and PDF
hash are pinned in `evidence/references.json`. The diagrams were inspected
visually because this PDF is scanned. That map does not document a direct
mapping for the separate radio ROM.

A bounded read of the documented ARM ROM recovered **32,672 bytes** through
`0x7f9f`, each response checked for address, length, status and CRC. The request
at `0x7fa0` received no reply, and the subsequent registry capture showed the
normal `2dc8:9018` gamepad again. The cause of this mode exit is unknown; it is
not evidence that the address is protected or invalid. No reset/write command
was sent, and no automatic retry occurred. The final 96 bytes are missing.

The incomplete capture is local at
`build/hardware/20261105T180539.340691Z-arm-rom-full/arm-rom-full.bin`, SHA256
`cd416afad292582d97a74cfc07bae1009fbcc637de44955873e479cd0b65222a`.
Despite the original attempted-capture filename, this is **not a full ROM dump**.
Its `[0x4000, 0x6000)` bytes match the previously double-read API window.
After the user re-entered update mode, an independent read of all 32,672 bytes
succeeded and matched exactly, with the same SHA256. The controller remained
in bootloader mode afterward. Verification data, transport log and exact reader
source are local under
`build/hardware/20261105T183845.230541Z-arm-rom-prefix-verification/`.
The helper now offers only
`arm-rom-prefix` for this expansion, bounded to the successfully observed range;
the attempted full-range mode was removed pending investigation.

The recovered `0xc6` routine decrements R0, loops until zero and returns without
memory access. `tools/inspect_arm_rom.py` executes `INIT_OTP`, `READ_CHIPID` and
`DEINIT_OTP`, including their actual delay loops, in virtual memory. Across
64 cases (16 clock-selector values, two synthetic OTP patterns and two RAM
destinations), only the six destination bytes and stack scratch change in RAM.
Maximum isolated stack use is 24, 32 and zero bytes respectively. Peripheral
access is explicitly modeled; this does not read real OTP or execute these
routines on the controller. Reviewed metadata is in `evidence/arm-rom-startup.json`.

This closes the isolated startup chip-ID call's transitive RAM-write audit for
the captured bytes. It does not establish spare RAM, interrupt stack headroom,
peripheral timing, or notification/CCC behavior. The Bluetooth ROM remains
uncaptured, and no undocumented radio selectors or ROM-switch registers were
changed on hardware.

### Radio access and flash boot-entry investigation

The stock radio loader at `0x010233b8` enables the Bluetooth clock, sets the
`BT_UCODE_LO`/`HI` selectors (`0xc8024`/`0xc8022`) to zero and writes `0x80` to
`BT_UCODE_CTRL` (`0xc8023`). It uses DMA channel 6 to transfer the 6,010-byte
patch to `BT_UCODE_DATA` (`0xc8025`), then clears the control register. This
proves a patch-programming path, not a radio-ROM read mode. Neither a read
selector value nor a directly mapped ROM address is established. No such
register writes were attempted on hardware.

The independently captured ARM ROM contains branches at `0x78c4` and `0x7904`
to flash address `0x01000200`. A single bounded 32-byte read at that exact entry
returned protocol status **1**, with zero bytes accepted. The rejected response
is not flash contents and does not establish why access failed. No retries,
alternate guessed addresses or protection changes were attempted. The helper's
`boot-entry` mode reproduces only this fixed read. Local evidence is under
`build/hardware/20261105T183956.760166Z-boot-entry/`.

Shared metadata and source anchors for these observations are retained in
`evidence/readback-verification.json`; raw device captures remain ignored.

### Vendor code-memory read lead and peripheral-access limits

The public [Yichip 16xx SDK](https://github.com/Yichip-Microelectronics/16xx/tree/68ce48a6171de86ec6b3e4b8f60b35a1f40d6e06)
includes an unstripped Linux debug utility `SDK/util/tool/e`. Its bytes and
source revision are pinned in `evidence/references.json`. The utility was
inspected statically and its isolated `readcoderam2` function was emulated;
it was never launched against hardware. The SDK targets another chip family.

The function at ELF VA `0x5b0c` reads debug control `0x8203`, writes that value
OR one, programs selectors `0x8022`–`0x8024`, and reads the data port `0x8025`.
For input instruction index `p`, the selector bytes are:

```
HI   = (p >> 12) & 255
CTRL = ((p >> 6) & 63) | (0x80 if p < 0x800 else 0x40 if p < 0x8000 else 0)
LO   = (p * 4) & 255
```

It then clears all three selector bytes. This isolated function does not resume
the processor or restore the selectors' previous values. The addresses match
the relative register names in the YC3121 header, but that correspondence does
not prove ROM bank selection, access permissions or safe stop/resume behavior
on Zero 2. The vendor's debug-adapter protocol is not the 8BitDo boot protocol.
`tools/inspect_yichip_debug.py` reproduces 40 actual x86-64 traces with device
I/O, time and printing stubbed. Results are in `evidence/yichip-debug.json`.
No halt/selector writes were sent to the controller.

Two narrowly bounded bootloader reads returned successful transport status but
all-ones data: `0xc8000`/two bytes (`ffff`, nominal SDK BT_REV/BT_STEP) and
`0xf856c`/four bytes (`ffffffff`, nominal SYSCTRL_CLK_CLS). These are **not a valid
radio identity or a verified clock-register value**. In particular, do not
interpret bit 13 of that response as proof that the Bluetooth clock is off.
The bootloader's peripheral-address handling and access width remain unproven.
A separate 32-byte read at documented RAM base `0x20000` returned nonuniform
data different from the already captured flash bytes at `0x01020000`. That
rules out a simple flash-offset alias for this tested pair only; it does not
validate peripheral reads. Raw logs are in ignored timestamped directories
under `build/hardware/`; shared metadata is in `evidence/radio-access.json`.

### Nominal input-clock audit

The stock SysTick configuration is now instruction-tested across 176 cases.
It rounds the requested period down in five-unit steps and stores the original
argument as the run-loop scale. Startup's argument ten corresponds to nominal
10 ms under the stock 192 MHz/divider clock model. Passing one produces a
zero-cycle request and underflows LOAD, not a 1 ms sampling period. Runtime
reconfiguration resets the SDK counter but preserves the run-loop tick count;
the interrupt also advances another accumulator by a fixed ten regardless of
period. Therefore neither shared counter is accepted as the custom component's
millisecond source. Three emulated interrupt-chain cases verify registration,
increment and wrap behavior, with one unrelated side helper stubbed.
See `radio-binding.md` and `evidence/systick-v108.json` for formulas and limits.

## Base image and encryption

[8BitDo's support page](https://support.8bitdo.com/) lists Zero 2 v1.08.
The public download API identifies it as type 30, catalog ID 1986, dated
2025-06-09. The exact URL, headers, sizes and hashes are in
[`sources.lock.json`](../sources.lock.json).

The downloaded package is 124,472 bytes, SHA256
`43a313564ac1125df1de9c5b47c393fb5ebfc4d9ff70790e519fb72e609da808`.
The vendor catalog advertises MD5 `77F76375A4C041EBE9C2D774A065EEBC`, while
the actual download is `4dfe36e1a45180393e0b22edb1d3f2e5`. The discrepancy is
unresolved. This work pins the observed SHA256 for reproducible offline analysis;
it does not claim the vendor MD5 passed or that these bytes are authenticated.
The older v1.06 API download also differs from its catalog MD5.

| Section | Container offset | Header load address | Size | PID field | Cipher |
| --- | --- | --- | --- | --- | --- |
| 0 | `0x0` | `0x08003400` | 51,200 | `0x0` | GD32 |
| 1 | `0xc81c` | `0x01018000` | 73,216 | `0x9018` | Yichip |

Both headers carry version 108. Every payload decrypts fully with the explicit
cipher and re-encrypts to identical original bytes, preserving section order,
length, load address and PID. This checks format consistency, not hardware
compatibility or authenticity. Strict parsing rejects partial sections, trailing
bytes, non-block sizes, unsupported header fields and GD32 key-schedule overrun.

The older official v1.04 ZIP contains a single 50,688-byte GD32 section. Combined
with the two different address spaces in v1.08, this raises a hardware-variant
question. **Do not assume the sections describe two chips in the connected
controller, or apply a Yichip patch to an earlier GD32 device.** A newly traced
updater path selects the section whose header PID matches `0x9018`; this selects
section 1 in v1.08. The connected unit's product query and application-prefix
readback now agree with that selection. The GD32 hardware selection path remains
unestablished; both sections are retained faithfully.

[8cryptdo](https://github.com/aeromodes/8cryptdo) is pinned at
`aaffcebafa481631de9c1d722a5693d02234e43a`, retained with its MIT license.
Its documentation reports a recent Zero 2 teardown using YC3121. The Yichip
payload independently contains SDK paths such as `Librarier/sdk/yc_gpio.c` and
Thumb code using low-mapped RAM and peripheral addresses.

## Recovered Yichip paths

All addresses below refer only to the pinned v1.08 **section 1**. Evidence hashes
are generated by `tools/inspect_stock.py` and retained in
[`evidence/stock-v108.json`](evidence/stock-v108.json).

- Entry at `0x01018000` loads the Thumb startup address `0x01018201`.
  Startup sets SP to `0x0002ff00` and calls the C runtime initializer.
- `0x0101eece` loads a pointer to `0x01025a6e`, then calls `0x010233b8`.
  That loader reads the `00 02 / aa 55` radio configuration script. Its first
  record contains 6,010 bytes of radio microcode. The remaining 69 records copy
  data to `0x000c0000 + record_address`, with two special-case writes in the loader.
- The script includes an attribute-table record at section offset `0xf2f2`:
  202 payload bytes at `0xf2f8`, written to `0x000c4975`. The static decoder
  finds 18 attributes: GATT/GAP/Device Information fields, a vendor service and
  characteristic, and CCC at handle `0x12`. The vendor characteristic declaration
  has property byte `0x14` (notify plus write without response).
- The format is proprietary, unlike BTstack's independent table format. In
  particular, the raw 128-bit fields need further interpretation; do not assign
  a custom service UUID by assuming the embedded `FF10`/`FF13` bytes are ordinary
  Bluetooth-base UUIDs. Runtime commands may also modify the initial profile.
- A separate BTstack-style `SPP+LE Counter` sample table appears at section offset
  `0x106a4`, with FF10/FF11 UUIDs. No active registration path was established.
  Finding that table does **not** establish that FF11 is the controller's service.
- The report router at `0x0101f1d4` takes button/report inputs, normalizes sentinel
  values and dispatches mode-specific reports. It checks state at `0x00020182`
  at `0x0101f240`. A hook only after this gate could repeat the Gamebrick's original
  HID-readiness problem. The scan owner and additional upstream gates are now
  traced below; no polling hook has been selected.
- IPC submission at `0x010202c8` checks available space against payload length
  plus three bytes, then calls `0x0101eb50`. The latter copies the header and
  payload synchronously into the radio ring and advances its write cursor. It
  includes a conditional radio wake/sleep handshake. A second submit path at
  `0x01020316` uses four header bytes and `0x0101ec38`.
- The HID wrapper at `0x01019db8` constructs opcode `0xb0`, calls the second
  submit path, then returns success without checking the result. It is not a
  suitable notification transport merely because it accepts a pointer/length.

The next binding pass confirmed the **stock command `0x09` dispatch**, but its
payload reader, complete guard and notification submission continue into code
outside the update image. CCC/connection lifecycle remains unresolved. No
guessed function signature is used by the compiled component.

### Public protocol references

Two additional public Yichip sources provide a specific lead:

- [YC1021 `YC_HCI_CMD_SEND_BLE_DATA`](https://github.com/oushaojun/yc1021_bluetooth/blob/46db146cabec9384f2b30a53888f779d8f55fc09/bt_protocol.c#L360)
  sends command `0x09` with a two-byte little-endian attribute handle followed by
  up to 20 data bytes. Its fixed handle `0x002a` belongs to that example, not Zero 2.
- [YC1121 `module_hci_cmd_receive_le_data`](https://github.com/WuSJ1001/YC1121_Stack/blob/c9e8ada633cf35299f0083caa50eafcc4f827224/program/app_module.prog#L312)
  handles the same opcode, checks BLE connection/encryption and the preceding
  characteristic declaration, and queues notifications/indications with FIFO
  backpressure. Its attribute walker uses two length-prefixed fields after each
  handle, consistent with the static Zero 2 table decoder.

Several other command numbers match Zero 2 ARM wrappers, including `0x76`–`0x78`
for deleting/adding custom services and characteristics. This is evidence of
protocol ancestry, not proof that CCC behavior, acknowledgement ordering or
radio memory addresses are identical on YC3121. The reference sources are
downloaded under ignored `research/downloads/`; no code from them is linked into
the component.

### Same-family printer comparison

The [NIIMBOT hardware inventory](https://github.com/MultiMote/niimbot-wiki/tree/47af7952fcd07cab9bf55e6cca2f1916e043d42e/docs/hardware)
identifies YC3121 variants in D110 and B1 printers. D110 6.10 and B1 2.03 images
from the [firmware archive](https://fw.niim.blue/) are now pinned with their
archive URLs, vendor URLs reported by the archive notes, sizes and SHA256 hashes
in `evidence/references.json`. These are comparison inputs, not authenticated
vendor downloads or Zero 2 firmware. All binaries remain ignored and local.

Both printer images have an inferred ARM load address of `0x01010000` and an
identical 4,062-byte radio patch. That patch differs from Zero 2's 6,010 bytes.
The printer patch contains the same handle-minus-one / lookup sequence and
notification continuation `0x4f01`, but this does not establish ROM identity.

D110's ARM sender at `0x0101a4a8` prefixes data with the LE16 handle saved from
characteristic registration, then calls its command `0x09` wrapper at
`0x0101922e`. The wrapper clears stale acknowledgement bit 6, submits the
descriptor and waits for bit 6 or a timeout. `tools/inspect_printer_reference.py`
executes these unmodified instructions in virtual memory with explicit stubs
for registration results, IPC submission and time. It checks 18 handle/length
combinations, null rejection, delayed acknowledgement, wrong-bit rejection,
timeout and rejected-submission behavior. The packet builder and copy routines
are not stubbed. Reviewed results are in `evidence/niimbot-reference.json`.

This supplies same-family evidence for the handle prefix and acknowledgement
bit. It does **not** prove Zero 2's missing ROM payload reader, CCC lifecycle,
FIFO acceptance or delivery. The printer accepts up to 253 data bytes and uses
timeout argument 500; neither is imported as a Zero 2 limit or time interval.
The printer wrapper also ignores the submission return before waiting, so it
is not suitable to transplant as a nonblocking transport.

### Second offline binding pass

Detailed traces, addresses, limits and the twelve GPIO-to-stock-mask assignments
are recorded in [`radio-binding.md`](radio-binding.md).

- Added a partial radio instruction decoder. Stock radio PC `0x1c4` dispatches
  command `0x09` to `0x530`, checks state bit 9 at radio RAM `0x4652`, and branches
  to external continuation `0x4eda`. Related code at `0x277` checks notification
  properties using a handle field at `0x467b`. The missing continuation and guard
  prevent a complete transport contract from being established offline.
- Traced the ARM completion switch: command `0x09` with zero status sets
  acknowledgement **bit 6**, not bit 9. Local IPC insertion is not that completion.
- Reconstructed compressed C-runtime data and independently checked it by
  executing stock Thumb initialization in virtual RAM. The startup call sites
  delete custom attributes and register an FF10 service / FF13 write-and-notify
  characteristic. Their returned handle is stored at `0x00020648`. Initial table
  handles `0x11`/`0x12` must not be treated as runtime bindings.
- Recovered GPIO reading at `0x0101f64c` and wrapper `0x0101f718`. A subsequent
  audit corrected the earlier filtering interpretation: `0x0101f09c` always
  returns one, bypassing the delay/resample branch. The earlier five cases forced
  that predicate to zero and were counterfactual. Current emulation runs all
  4,096 combinations through both actual reader and wrapper without stubbing
  either; it confirms raw snapshots and no delay/retained-state update.
- Traced timer callback `0x0101be14` and registration at `0x010202a4`. Two
  congestion checks in `0x0101ca40` can skip GPIO sampling before the report
  router is reached. Six isolated mode-5 cases reproduce those gates. Actual
  timer registration and 36 synthetic deadline cases establish arithmetic, but
  do not establish wall-clock units, firing cadence or sleep behavior. Physical
  button labels and an independent polling hook remain unresolved.
- Executed 1,024 IPC cursor cases. **Exact fill is unsafe for a custom producer:**
  stock accepts it and leaves equal read/write cursors, which its capacity
  function interprets as empty. Reserve one byte and serialize check/submission.
  Radio wake and actual notification delivery were not emulated.
- Traced the application BLE state at `0x00020682` (event `0x02` stores 2,
  event `0x05` stores 3), distinct from HID readiness at `0x00020182`. Queued
  event emulation verifies those routes, the dynamic vendor-handle comparison,
  watchdog cancellation and four restart guards. The stock watchdog uses timer
  `0x00021ebc` and delay argument 5999; matching vendor writes remove it, while
  unrelated writes leave it active. The custom subscription lifecycle must own
  this behavior too. Radio event generation, CCC commit/reset and wall-clock
  timing remain unproven; restart I/O was not executed.

Offline emulation results are in `build/stock/emulation.json`, with the reviewed
metadata retained in `docs/evidence/emulation-v108.json`. It uses simulated
memory only. No USB or Bluetooth interaction occurred. The current offline
blocker is revision-matched radio ROM/SDK evidence for notification acceptance
and CCC commit/reset semantics; the related-chip source cannot establish those.

## Reference projects and component

The user's local reference projects are `../glassly-mini-gamepad` (Gamebrick)
and `../glassly-mini-gamepad-plus` (Ananke). Their current findings, plans and
firmware sources were read; neither project was changed. Source revisions and
relevant file hashes are in [`evidence/references.json`](evidence/references.json).

The new component follows their queued full-state design: press and release
snapshots, subscriber baseline, explicit backpressure, sequence numbers and
overflow recovery. Its protocol tag is 3 to avoid reusing Ananke's raw mapping.
It also accepts connection handle zero explicitly, and collapses an overflowing
queue to the newest state. The single-owner/lifecycle contract is documented in
[`protocol.md`](protocol.md).

An unbound input stage now adds independent per-button debounce over the recovered
`0x3ff9` mask. Its proposed 8 ms window is not electrically validated; the clock
and regular polling hook remain to be bound. It needs 52 bytes of state, bringing
the combined input/stream state requirement to 132 bytes before integration.

`python3 scripts/check.py` passed 26 Python tests and both sanitized C suites,
including 100,000 model-comparison steps, session resets, handle reuse, pending
release delivery, overflow, retry and sequence wrapping. The input suite covers
all 4,096 masks, independent bounce, release, clock wrap, reset and integration
with queued press/release delivery under backpressure. Apple Clang 21 produced
a 230-byte Thumb `.text` section, with 80 bytes of caller-owned RAM required;
the input object's `.text` is 100 bytes. Neither object has undefined symbols.
Both sources cross-compile into separate relocatable ARM objects. These are component checks, not a linked
firmware test. Compiler/source/output hashes are in `build/component.json`.

The proposed target is Cortex-M0/Thumb, consistent with the observed instruction
set and public YC3121 references. The initial memory audit now records eight
BSS-backed pools (26 blocks, 2,628 bytes), top-of-RAM boot markers, 848 bytes of
combined main/dispatcher frames, and 508 zero bytes at the image tail. Actual
stock pool initialization passes argument, free-list and write-boundary checks
in emulation; its isolated stack use is 72 bytes. Compiler stack estimates are
also retained in `build/component.json` (24 bytes for stream poll, 20 for input
poll, excluding callers/callbacks and exception nesting).

Startup initialization ends at `0x00022b18`, but that does not establish unused
RAM. The public [YC3121 ROM API header](https://github.com/RT-Thread/rt-thread/blob/b1cd917f9a4a10182773f2a22f6a07041eeeaacc/bsp/yichip/yc3121-pos/libraries/core/rom_api.h)
names the startup targets `0x442d`, `0x45d9` and `0x4481` as `INIT_OTP`,
`READ_CHIPID` and `DEINIT_OTP`. Thus the call passing `0x20000` is a chip-ID read,
not an unidentified general RAM initializer. Live readback now supplies these
ARM ROM implementations and shows the six-byte OTP read described above.
The extended-ROM audit above covers these calls' isolated memory writes;
other runtime owners still require auditing before reserving custom state.
The live image tail differs from the package zeros and
must be preserved; no location has been approved for code
or custom state. Worst-case stack headroom and branch trampolines remain unproven.
The name-only `.dat` probe above is now built and flashed; the GATT components
remain unbound. No claim of GATT or iOS background operation is made.
See [`plan.md`](plan.md) for the remaining work.

## Vendor updater selection evidence

Downloaded the Windows archive linked by the [official updater page](https://support.8bitdo.com/firmware-updater.html)
for offline inspection only. ZIP and member hashes are pinned under
`updater_research` in `sources.lock.json`; all binaries and bundled logs remain
ignored. This Windows updater was never launched. Bundled logs are vendor archive content,
not observations of the user's controller.

The native DLL at preferred image base `0x10000000` compares its PID global with
`0x9018` at `0x1000795f`, then calls a header scanner at `0x10007050`. The scanner
reads 28 bytes and compares the DWORD at header offset 12 against the requested
PID. On mismatch it advances by header length plus the DWORD payload length at
offset 8. The selected offset is then used to read the chosen header.

`tools/inspect_updater.py` executes the actual x86 comparison/advance block,
protocol gate and read/query packet constructors in synthetic memory, with
transport calls captured rather than executed. Five header comparisons cover PID zero
(offset zero), PID `0x9018` (offset `0xc81c`), and no match. The zero case verifies
scanner arithmetic; it does **not** prove which hardware takes a GD32 path.
No file API, updater initialization, device enumeration or flash operation is
executed. Reproducible anchors and limits are in
[`evidence/updater-selection.json`](evidence/updater-selection.json).

Battery validation at 21:48 UTC: USB registry was empty. A fresh session received
a baseline plus A press/release, remained connected for **187.951 seconds** with
no keepalive writes, and acknowledged A0 before intentional disconnect. Idle time
after the release was **166.260 seconds**. Evidence: `evidence/buttons-probe-battery.json`.
This does not establish long-term power consumption or iPhone background behavior.
