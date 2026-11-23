# Zero 2 v1.08 binding investigation

This is offline evidence for the **Yichip section only**. No custom image has
been produced. The GD32 section remains preserved and its variant selection is
still unresolved. All addresses below require the pinned section hash in
`docs/evidence/stock-v108.json`.

## Radio command 0x09 is present, but its continuation is missing

The radio configuration's first record contains 6,010 bytes. It decodes as
1,502 complete big-endian instruction words followed by `c1e6`. The trailing two
bytes are retained as uninterpreted data; their purpose is not established.
Radio PCs are **instruction indices**, not ARM addresses or section offsets.
For this record, `section_offset = 0xda74 + 4 * radio_pc`.

The partial decoder in `tools/radio_disasm.py` uses encoding information from
[YC1121 command.format](https://github.com/WuSJ1001/YC1121_Stack/blob/c9e8ada633cf35299f0083caa50eafcc4f827224/format/command.format).
The Zero 2 memory-transfer count is at bit 17, unlike bit 15 in that reference.
The actual Zero 2 attribute constructors independently establish 3-, 4- and
8-byte transfer sizes. Unknown/reserved encodings remain `.word`; register
names aid comparison and do not import other chips' ROM symbols or RAM maps.

| Radio PC | Stock behavior |
| --- | --- |
| `0x1bd` | Reads command byte at radio RAM `0x0aff`. |
| `0x1c4` | Dispatches command `0x09` to `0x530`. |
| `0x530`–`0x533` | Reads two bytes at `0x4652`; requires bit 9; calls guard `0x534`; branches to `0x4eda`. |
| `0x534`–`0x53c` | Guard references `0x4679`, `0x4498`, and `0x043b`, and external code `0x7dc1`/`0x7dbf`. |
| `0x277`–`0x28e` | Related notification patch uses pending length at `0x467a` and handle at `0x467b`, looks up handle minus one, checks declaration bytes `02 03 28 01`, and requires property bit 4 before continuing at `0x4f01`. |

The lengths/handle fields are supported by the corresponding reference source
and this stock property-check sequence. **The actual command payload reader,
complete authentication guard, and notification FIFO submission are outside
the supplied microcode.** PCs `0x4eda`, `0x4f01`, `0x501c`, and `0x7dc1` cannot
be decoded from this update package. They appear to be resident radio ROM.
The related YC1021/YC1121 LE16-handle prefix remains a supported hypothesis,
not a complete Zero 2 transport binding.

The ARM completion path is clearer: event `0x06` enters the command-completion
switch at `0x010190ca`. Its inline table routes command `0x09` through
`0x010192bc` to `0x01019336`. A zero status byte sets **acknowledgement bit 6**
in the bitmap at `0x00020010`; a nonzero status does not set it. Bit 9, mentioned
in earlier exploration, belongs to a different command. Ring insertion alone
must not consume the queued button snapshot: eventual command acceptance,
failure, disconnect and stale acknowledgements still need an owner.

## Runtime service replaces the initial table

### Visibility experiment

The startup path at `0x0101a570` copies a separate 16-byte constant from
`0x0102919c` and submits its first 14 bytes through `0x01019ff0`, command `04`:
`3830454c0000000000000000000000` (`80EL` plus ten NULs). It is independent
of the shared USB/classic model-name pointer. Related YC1021/YC1121 sources call
opcode 04 the BLE-name command; on-air naming remains to be observed.

The command-02 wrapper at `0x0101a304` initially copies its three arguments into
r4/r5/r6, then overwrites r6 with zero at `0x0101a310` and r5 with one. It builds
bits 0/1/2 from equality-to-one tests of those registers. Thus bit 2 is always
clear, including when startup passes a third argument of one. Both related
protocol sources identify bit 2 as BLE visibility. Zero 2's radio command-02
implementation falls through to external ROM `0x4e5c`; its semantics are still
a hypothesis for this revision.

`tools/build_ble_probe.py` changes `0026` (`movs r6,#0`) to `0126`
(`movs r6,#1`) at section offset `0x2310`, on top of the successfully flashed
name-only image. No additional RAM, stack, code placement or GATT stream is
introduced. All wrapper calls will request this bit, including calls that
otherwise stop visibility; sleep/power behavior must be measured.
`tools/inspect_ble_setup.py` executes the actual startup/name builder in nine
cases and the stock/probe visibility builder in sixteen cases, stopping before
IPC submission. Only the startup hardware initializer is stubbed; NVIC is
synthetic RAM. This proves command bytes, not radio acceptance or advertising.
See `evidence/ble-setup-emulation.json` and `evidence/ble-probe.json`.

The probe has now been flashed and fully read back. With USB connected, `80EL`
advertises; FF10/FF13 and descriptor 2902 are discoverable and notification
subscription succeeds. A bounded session remained connected and subscribed for
94.24 seconds without receiving notifications. No button sender is present.
This supports the bit-2 interpretation empirically, while the ROM implementation
remains missing. Subsequent battery tests completed discovery/subscription,
then demonstrated a roughly 61-second failure without vendor writes versus
188 seconds connected with nine acknowledged keepalives, followed by successful
reconnect and subscription toggling. See `evidence/ble-battery-keepalive.json`.
The diagnostic also scans for `80EL`; that generic name alone does not identify
a physical controller. The observed device is correlated by its appearance after
flash and its expected GATT profile, not by an independently mapped radio address.
See `evidence/ble-probe-gatt.json` and `evidence/ble-probe-flash.json`.

The startup scatter table at `0x0102982c` describes:

| Source | Destination | Output bytes | Initializer |
| --- | --- | --- | --- |
| `0x0102984c` | `0x00020000` | `0x78c` | Compressed-data decoder `0x010183ca` |
| `0x01029c04` | `0x0002078c` | `0x238c` | Zero initializer `0x01023342` |

`tools/startup.py` reconstructs the initialized bytes from the compressed
stream; execution of the original Thumb initializer independently reproduces
them. The compressed stream consumes 950 bytes. Initialized/zero regions end at
`0x00022b18`. **That boundary does not establish free RAM:** heap, stack, DMA,
runtime allocation and execution placement have not been audited.

At `0x0101a694`–`0x0101a6ac`, ARM startup invokes delete-custom (`0x76`),
add-service (`0x77`, 17-byte argument) and add-characteristic (`0x78`, 20-byte
argument), storing the returned handle at `0x00020648`.

The decompressed arguments are:

- Service at `0x0002065a`: UUID length 16 followed by
  `0000ff10-0000-1000-8000-00805f9b34fb` in little-endian Bluetooth order.
- Characteristic at `0x0002066b`: properties `0x18` (write and notify), UUID
  length 16, `0000ff13-0000-1000-8000-00805f9b34fb`, then length 1 and value zero.

The stock radio constructors at PCs `0x1fd`–`0x23b` write the length-prefixed
table format recovered earlier. A notify/indicate property causes a `0x2902`
CCC entry with a two-byte zero value to be created. Dynamic table allocation,
registration success and final numeric handles are not established offline.
The later live visibility probe confirms the expected on-air FF10/FF13/CCC
profile, but CoreBluetooth does not expose its numeric ATT handles.
In particular, **do not patch the initial table's handle `0x11` or CCC `0x12`
and assume they survive startup.** The ARM application already consumes event
`0x08` and compares its leading LE16 handle against `0x00020648` at
`0x010198e8`–`0x0101991c`; preserve that existing path when adding a new service.

The ATT write patch at radio PC `0x512` recognizes request opcode `0x12` and
calls an external callback helper at `0x5abe`. A callback candidate at `0x1b0`
records a data pointer/length and reads the written handle from `0x0474` before
continuing at `0x50bb`. The package does not expose enough of those routines to
prove CCC commit timing, rejection behavior, per-connection storage or reset.
Reading a nonzero initial-table CCC slot is therefore not a valid substitute
for the missing lifecycle binding.

## Application BLE lifecycle and watchdog

The application dispatcher `0x0101986c` uses opcode-plus-one in its switch at
`0x0101988a`. Event `0x02` reaches `0x01019ad2`, stores **2 at `0x00020682`**,
calls the power/indicator helper `0x0101c874(2)` and registers a timer through
`0x01023a5c`. Event `0x05` reaches `0x01019b2c`, stores **3 at `0x00020682`**,
then calls that helper with 3. Related YC1021/YC1121 sources name those events
BLE connect/disconnect; stock application execution independently establishes
the dispatch and stores. Radio event generation and connection identity remain
unverified. This BLE state is separate from the report-readiness state at
`0x00020182`; do not reuse the HID gate as GATT readiness.

The timer object is `0x00021ebc`, callback `0x01023a91`, with delay argument
**5999**. Its wall-clock duration is not asserted: the shared clock scale is
configurable. In callback `0x01023a90`, BLE state 2, mode byte `0x00020181 != 3`,
and a clear bit 6 of `0x000201dc` lead to `0x01023290`. That path performs cleanup
and reaches `0x010180b4`, which writes the system-control location referenced at
`0x010180ac`, then jumps back to the image entry. The offline test observes the
restart function entry and substitutes a return; it never executes reset I/O.

Event `0x08` reads a leading LE16 handle and compares it with the dynamic handle
stored at `0x00020648`. A match calls `0x01023ad0`, which **removes** the watchdog
timer if active, and `0x010232b0`, which clears the idle counter at `0x00020198`.
It does not merely refresh the timer. An unrelated handle leaves it active.
Disconnect changes BLE state to 3; the timer can remain listed, but its guard
then skips restart and rearms. A subsequent connect removes/replaces an active
timer before adding it again.

Emulation feeds events into the actual software ring and executes its dequeue,
application switch, handle comparison and timer/list operations. Only IRQ
enable/disable wrappers, the power/indicator helper and restart entry are stubbed.
Checks cover connect, disconnect, matching/unrelated writes, cancellation and four
watchdog guard cases; exact substitutions are retained in the emulation report.
The handle is synthetic (`0x2345`), not an assigned firmware handle.

The custom service must integrate with this watchdog and idle ownership. Merely
adding a notification characteristic does not do so. In particular, do not treat
an arbitrary write event or the BLE-connected byte as a committed subscription.
CCC handle assignment, successful commit, reset ordering, command acceptance and
serialization still need proof before a runtime adapter can be bound.

### Separate idle path

The stock sample timer `0x0101be14` increments `0x20198` through `0x0101ee50`
when its report task returns zero, then calls `0x0101db3c`. That guard returns
below threshold `0x20194`. At/above threshold it clears the counter when either
`0x201b8 != 0 && HID state 0x20182 == 2`, or mode `0x20181` is 2/3. Otherwise it
reaches `0x01020350(10)` and subsequent power-related operations. This guard
does not itself read BLE state. `tools/inspect_idle.py` executes 48 synthetic
combinations, stopping before that first side-effect call; no power I/O runs.

The threshold setter `0x01022938` does consider BLE: it clears the counter and
sets threshold 90000 if either BLE `0x20682` or HID `0x20182` equals 2, else
18000. For mode `0x201b4 == 0` it scales that value by `10 / scale[0x2058d]`
using integer division. Twenty-four actual-code cases verify those results.
The BLE indicator/helper `0x0101c874` calls this setter; another startup path
at `0x0102431e` writes threshold 6000. These counters are not asserted to be
milliseconds. Active live thresholds and which path caused the observed
battery timeout remain unknown. See `evidence/idle-emulation.json`.

The battery subscription-only test lost connection after 61.097 seconds, and
the user subsequently reported the LED off. Thus power/idle handling needs a
hardware test independently of subscription acceptance. The bounded host
keepalive experiment writes one zero byte to the existing FF13 value; the
stock event-08 handler clears both the idle counter and watchdog, so success
with that experiment alone cannot distinguish those two mechanisms.

## Input path and offline execution checks

`0x0101f64c` reads three GPIO banks via `0x0101bb78`. The latter reads halfwords
at `0x000f873c + bank * 2`. Inputs are active-low. These are **stock mask bits**;
physical labels were later established by the ordered user tap capture in
`evidence/buttons-probe-mapping.json` (see `buttons-probe.md`).

| GPIO bank | Pin bit | Stock mask bit |
| --- | --- | --- |
| 0 | 1 | 5 |
| 0 | 0 | 4 |
| 0 | 9 | 13 |
| 0 | 10 | 12 |
| 0 | 5 | 11 |
| 1 | 14 | 9 |
| 1 | 10 | 8 |
| 1 | 13 | 7 |
| 1 | 12 | 6 |
| 1 | 11 | 0 |
| 2 | 4 | 3 |
| 2 | 1 | 10 |

The wrapper at `0x0101f718` samples this reader, then calls `0x0101f09c`.
That predicate is exactly `movs r0, #1; bx lr`. The wrapper consequently returns
the **raw sample**, bypassing its retained-state, delay and resample branch.
Earlier evidence called five tests of that lower branch normal filtering; those
tests forced the predicate to zero and did not represent this stock build.
They have been replaced with execution of the actual wrapper over all 4,096
combinations, with no instruction substitutions. No delay is called and retained
state at `0x00020150` remains untouched. Subsequent remapping/repeat logic may
still produce the `0xffffffff` sentinel; it must never enter a raw-mask stream.

The caller `0x0101ca40` contains gates **before** the read at `0x0101cbee`:

- At `0x0101cb28`, IPC capacity below 800 returns early when state byte
  `0x00020182` equals 2.
- `0x0101ef84(50)` checks software-ring occupancy at `0x00020f8c`:
  `used + 50 < capacity`. It is a capacity predicate, not a timer.
  In state 2, a false result routes `0x0101cbdc` through `0x01020544`, skipping
  the GPIO wrapper. Other mode-specific report checks also precede sampling.

The emulator checks six mode-5 boundary cases using the stock capacity routines
and branches. It stubs unrelated preamble calls and stops at the selected input
routine; exact substitutions are in `evidence/emulation-v108.json`. This proves
those gates for the constructed states, not that mode 5 is the eventual BLE mode.
A custom sampler must run independently of them, before report remapping.

## Input timer ownership

`0x010202a4` installs callback `0x0101be15` in timer object `0x000219dc` and
schedules it with argument 9. The callback calls `0x0101ca40` and rearms itself
with argument 0, 9 or 29 according to mode/state. Startup selects the run-loop
vtable at `0x01029158`; its timeout implementation at `0x01023f7c` computes:

```
deadline = tick_counter + 1 + floor(delay_argument / scale), modulo 2^32
```

The tick counter is at `0x00020640`; the scale byte is at `0x0002058d`.
`0x01023f9c` increments the counter. Timer configuration at `0x0101c830` writes
the scale and configures hardware; call sites include argument 10 and a computed
value. A subsequent instruction-level audit now establishes its nominal timing
calculation, but not a monotonic millisecond source across sleep.
The emulator executes actual registration/list insertion and 36 deadline cases
using synthetic nonzero scales, including wrap. It does not simulate interrupts,
wall-clock timing, timer firing, or low-power behavior. The existing callback's
period cannot be assumed to meet a proposed 1 ms sampling cadence.

### SysTick configuration audit

`tools/inspect_systick.py` executes the unmodified configuration routine,
integer division helpers and SysTick register setup at `0x01020b14`. The
clock-control register is synthetic input; the core clock model in stock is
`floor(192000000 / (HCLK_SEL + 2))` Hz. Configuration writes:

```
cycles = floor(core_clock / 200) * (floor(argument / 5) & 255)
SysTick.LOAD = cycles - 1              # 32-bit write
scale_byte = argument & 255
```

The low control bits become 7 (enabled, interrupt enabled, core-clock source).
At nominal 48 MHz, arguments 5/9 produce 5 ms, 10/14 produce 10 ms, and 29
produces 25 ms. The stored scale still contains the original argument. Thus a
nonmultiple of five can make the run-loop conversion disagree with the actual
nominal tick period. Arguments below five produce zero cycles and a write of
`0xffffffff` to LOAD, **not a short timer**. The emulator checks register writes;
it does not simulate the hardware's 24-bit LOAD truncation or elapsed time.

Configuration clears SysTick CURRENT and the SDK counter at `0x2003c`, but
preserves the run-loop counter at `0x20640`. Multiplying that accumulated counter
by the current scale is therefore not a stable elapsed-time source across
reconfiguration. The dispatcher at `0x01019aa0` computes
`floor(payload_LE16 * 625 / 1000)`, stores its low 16 bits at `0x20680`, adds
five and calls configuration; the incoming payload's meaning is not asserted
by this audit. Startup call sites at `0x01020448`/`0x01020450` pass ten.

The routine at `0x01020210` increments the SDK counter (wrapping at
`0x7fffffff`), calls through `0x205f4` to the registered run-loop increment,
then calls a side helper and adds a fixed ten to `0x20008`. That last accumulator
does not track a changed tick period. The audit executes the actual callback
registration and interrupt chain with only side helper `0x0101ee40` stubbed.
All 176 configuration cases and three interrupt/counter-wrap cases pass;
metadata is in `evidence/systick-v108.json`. These are offline results, not a
measurement of interrupt cadence, oscillator accuracy, sleep or lost ticks.

Do not call the existing configuration routine with one to obtain 1 ms input
sampling, or alter the shared interrupt rate without auditing its other users.
The custom input stage still needs its own proven clock/sampling integration.

`firmware/button_input.c` therefore provides a separate, unbound per-button
debounce stage: each observed bit must stay unchanged for 8 ms before committing.
It uses only the recovered `0x3ff9` mask, keeps chattering buttons independent,
and requires 52 bytes of owned state plus a regularly polled millisecond clock.
Eight milliseconds is a proposed policy, not measured switch behavior. Reset on
boot/clock restart/sampling resume; held buttons qualify again from released state.
Neither its clock nor a GPIO/timer hook has been installed.

## IPC exact-fill issue

The same emulator checks all 1,024 read/write cursor pairs of a simulated
32-byte radio ring with a 13-byte command. Stock submit at `0x010202c8` accepts
`available >= packet_size`, copies bytes synchronously, and wraps correctly.
When available space equals the packet size, the resulting write cursor equals
the read cursor. The capacity function treats that equality as a fully empty
ring. This ambiguity is confirmed by execution, not merely disassembly.

A custom producer must reserve at least one byte, using
`available > header_size + payload_size`, with check and submission serialized
against other producers. The isolated checks set `0x00020038` to zero; actual
radio sleep/wake, concurrent cursor changes, interrupts, command completion and
BLE delivery are **not** emulated. No transport wrapper is bound yet.

## Memory and execution-placement constraints

`tools/memory_layout.py` adds reproducible constraints to the stock inspection
report. It approves no RAM or executable location. The visible pool initializer
at `0x01023bb4`, called at `0x0101a73a`, reserves these BSS-backed block arrays:

| Head pointer | Storage, end exclusive | Blocks | Bytes per block |
| --- | --- | --- | --- |
| `0x206e0` | `0x22064`–`0x2276c` | 3 | 600 |
| `0x206e4` | `0x2276c`–`0x227bc` | 4 | 20 |
| `0x206e8` | `0x227bc`–`0x228bc` | 4 | 64 |
| `0x206ec` | `0x228bc`–`0x22970` | 3 | 60 |
| `0x206f0` | `0x22970`–`0x22980` | 1 | 16 |
| `0x206f4` | `0x22980`–`0x229f8` | 3 | 40 |
| `0x206f8` | `0x229f8`–`0x22a84` | 5 | 28 |
| `0x206fc` | `0x22a84`–`0x22aa8` | 3 | 12 |

Actual stock execution, without stubs, confirms all eight registration arguments,
26 free-list blocks and their terminating links. The initializer writes only
pool heads, each block's link word, and its stack. Observed stack use for this
isolated call is 72 bytes; this is not a whole-firmware bound. These 2,628 bytes
of block storage are already inside the zero-initialized region, not extra free
space. Other BSS objects remain outside these arrays.

At the top of RAM, code explicitly reads/writes mode/restart marker `0x2fff0`
and version marker `0x2fff4`. Startup SP is `0x2ff00`. Main reserves 24 bytes;
the event dispatcher at `0x0101986c` reserves another 824 bytes (20 saved-register
bytes plus local allocations of 508 and 296). Thus that call path accounts for
848 bytes before deeper callees or exception handling. No worst-case stack bound
has been proved. The component build separately reports compiler frames of
24 bytes for `z2_stream_poll` and 20 for `z2_input_poll`; caller stack arguments,
the send callback, stock frames and interrupt nesting are additional costs.

The interval `[0x22b18, 0x2ff00)` is merely outside the known scatter output and
below initial SP. It is **not proven available RAM**. Startup calls external ARM
ROM through Thumb target `0x45d9`, passing `0x20000`, bracketed by wrappers for
ROM targets `0x442d` and `0x4481`. The pinned RT-Thread YC3121 `rom_api.h`
identifies these exact targets as `READ_CHIPID`, `INIT_OTP` and `DEINIT_OTP`,
respectively. Live readback now provides their ARM ROM code. `READ_CHIPID`
requests six bytes from OTP offset 2; the visible `READ_OTP` loop writes those
six bytes to its destination. The later expanded capture includes its delay
callee at `0xc6`, now also executed offline. This is progress on startup ownership, not a complete clobber,
stack, DMA or runtime memory audit. See the hardware section in `findings.md`.

The compressed data consumes bytes through section offset `0x11c01`, followed
by two zero alignment bytes. The zero-initializer record's source points to
`0x11c04`; the remaining **508 bytes** through `0x11dff` are zero. This is only
a package-padding region, not approved code space. Original live readback showed
nonzero contents: 499 of the 508 bytes differed, stable across two reads. Those
backups remain local. The official stock reflash subsequently replaced them with
zeros, verified across the whole application; their original purpose remains
unknown. No assumption is made
about boot validation, external references, required padding or executable
mapping. The components' 330 combined text bytes also exclude adapters, hooks,
alignment and other linker sections. No image-tail patch has been generated.

## Remaining evidence needed

The remaining transport blocker is a revision-matched YC3121 radio ROM
implementation or equivalent SDK contract. Live investigation is now authorized
and has established working readback; the separate radio ROM mapping remains
to be located. ARM ROM API bytes have already been captured.
Public YC1021/YC1121 sources supply ancestry but cannot prove the missing Zero 2
behavior. The public Yichip YC3121 repository has only a README; the inspected
RT-Thread YC3121 SDK inventory contains GPIO/UART/DMA/timer/watchdog drivers,
without Bluetooth implementation.

The same-family D110 printer comparison now independently demonstrates an ARM
sender constructing a LE16 dynamic characteristic handle followed by payload,
using command `0x09` and acknowledgement bit 6. Its radio patch shares the
handle lookup and external `0x4f01` notification continuation with Zero 2, but
differs as a whole and still omits that ROM implementation. The packet-builder
emulation in `tools/inspect_printer_reference.py` stubs IPC, time and registration
results explicitly. It establishes printer behavior, not Zero 2 CCC semantics
or radio delivery. See `evidence/niimbot-reference.json` and the source pins in
`evidence/references.json`; no printer address, timeout or payload limit is a
patch binding for Zero 2.

After that: establish notification acceptance and CCC epochs, choose the custom
advertised service, finish the scan task and memory/stack/branch placement audit, then
produce and independently unpack a version-pinned experimental GATT package.
Experimental flashing is authorized and the name-only image has booted after
full readback verification. The visibility experiment above is the next bounded
hardware test; neither it nor the name-only image includes the unbound stream.
