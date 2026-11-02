# Task-local MemoMind RFCOMM bridge

Standalone Android Activity with a loopback TCP JSON-lines bridge to one selected
RFCOMM service. It resolves the service through Android SDP using
`createRfcommSocketToServiceRecord`, without hardcoded RFCOMM channel numbers.
Connecting sends no application protocol bytes. The Activity must remain open;
it is not a background service. Closing the host connection, stopping the bridge,
or destroying the Activity closes its Bluetooth socket.

## Build

```sh
sh android_bridge/build.sh
```

Uses installed SDK `platforms/android-36`, Build Tools `36.0.0`, and Homebrew
JDK21. Override `ANDROID_SDK_ROOT` / `BRIDGE_JDK` for another local installation.
No Gradle, network downloads, or global tool upgrades are required. The build
generates a local debug signing key and verifies the signed APK. Output:
`android_bridge/build/memomind-bridge.apk`. The generated key is task-local and
ignored; retain it to permit `adb install -r` across rebuilds.

## Operator commands

The parent investigation executed this workflow on the connected Pixel9 Pro,
Android16, with MemoMind One firmware1.0.3.127. The bridge implementation task
itself performed no device operations.

```sh
adb -s 47011FDAP0083R install -r android_bridge/build/memomind-bridge.apk
adb -s 47011FDAP0083R shell pm grant org.memomind.research.bridge android.permission.BLUETOOTH_CONNECT
adb -s 47011FDAP0083R shell am start -n org.memomind.research.bridge/.BridgeActivity
adb -s 47011FDAP0083R forward tcp:38741 tcp:38741
python3 scripts/probe_memomind.py --address 4C:3C:8F:90:CC:C3 --trace captures/independent-probe.jsonl
```

Avoid a competing official-app connection while probing the same service. The
probe sends only public service1/command1 heartbeat and service1/command2 device
information. It requires STATUS0 for heartbeat and parses device-info's STRING
JSON TLV. It does not enter OTA mode or send settings, installation, or flashing
commands. The host returns the device's identity/version and retains unrelated
GM events. `--legacy-repeat-fa` enables the old repeated-FA continuation behavior
observed in the stock app capture; the default follows the public numbered-head
contract. The trace includes raw bytes and device identifiers; keep it local.

Cleanup:

```sh
adb -s 47011FDAP0083R forward --remove tcp:38741
adb -s 47011FDAP0083R shell am force-stop org.memomind.research.bridge
adb -s 47011FDAP0083R shell am start -n com.memomind.ai.aphrodite/.MainActivity
```

## JSON-lines API

The listener binds `127.0.0.1:38741` only. A launch `--ei port PORT` can select a
different loopback port. Use `adb forward` from the host. Up to two simultaneous host clients each own one Bluetooth socket. This lets
control and OTA remain connected independently. On connection it receives `{"event":"ready","protocol":1,"maxSessions":2}`. A third concurrent client
is closed without a greeting.
Requests contain an integer/string `id` and `op`; replies echo `id`, with
`ok:true,result:{...}` or `ok:false,error:"..."`.

| Operation | Fields | Result |
|---|---|---|
| `connect` | `address` uppercase MAC, `service` = `control` or `ota` | Resolves UUID 7033 or 7034 through SDP, connects with a 15s deadline; returns selected UUID |
| `write` | `hex`, 1–65535 decoded bytes | `written` confirms local stream write only, never remote business acknowledgment |
| `status` | none | Connected state and selected address/service |
| `disconnect` | none | Closes socket |

Raw input arrives asynchronously as `{"event":"data","hex":"...","elapsedRealtimeNanos":...}`;
socket loss produces `{"event":"disconnected","reason":"..."}`. Input callbacks
are arbitrary byte-stream chunks, not GM/OTA packets. The host queues them while
awaiting command replies. The raw `write` API is the transport foundation. The read-only probe has been
verified on hardware; the separately gated stock transaction driver and its
offline replay proof are documented in `analysis/stock-driver.md`.

## Evidence and verification

Official local source: `.tools/memomind-open-platform/GlassSDK/docs/PROTOCOL.md`,
`DEVICE_BUSINESS_PROTOCOL.md`, `WIRE_EXAMPLES.md` and `docs/examples/bluetooth_wire.py`.
The GM parser supports logical 80KiB, physical 512B, BE24 length, additive16 checksums,
numbered continuation heads, full TLV reassembly, response correlation and reset
after errors/disconnect. Tests cover arbitrary stream splits, fragmented TLVs,
bad checksum, missing continuation, unknown TLVs, explicit legacy behavior,
interleaved bridge events, permission errors and socket loss:

```sh
python3 -m unittest discover -s scripts -p test_memomind_transport.py -v
```

Ten focused transport/codec tests passed. The parent then installed the signed
APK, granted BLUETOOTH_CONNECT, stopped the competing MemoMind app connection,
forwarded TCP, and ran the probe successfully. The device returned heartbeat
STATUS0 and device-info H001Y / firmware1.0.3.127 / hardware2.1.2 / front1.3.
No legacy-fragment compatibility flag was needed for these replies. Evidence:
`captures/probe/read-only-01*` and `captures/probe/after-read-only.btsnoop`.

This proves an independent read-only control connection over the real RFCOMM
service. Android's interactive permission-denial UI, unpaired-device flows,
and connection loss during a real transfer are not hardware-tested here.
The initial read-only verification sent no OTA commands. The parent later
ran the stock driver in check-only mode: control→OTA SDP service switching,
attach/e1/e2, and e2/result3 succeeded on firmware1.0.3.127. It stopped before
OTA entry with zero blocks/chunks. Evidence is `captures/probe/ota-check-01/`;
see `analysis/stock-driver.md` for the exact scope and commands. This handshake
can change transient updater state and is not a read-only query. Full independent
flashing, plugin installation and modified-image acceptance remain untested.
The parent restored MemoMind after the check.


## Concurrent control and OTA revision

The rebuilt bridge accepts two concurrent loopback clients; each session retains
its own Bluetooth reader, command responses, and raw events. Stopping the Activity
closes both. The live OTA driver now opens one session for control and a second
for OTA, preserving control as observed in the stock-app capture. It checks the
`maxSessions:2` capability before sending device queries, so reinstall the rebuilt
APK before running the new driver. The same TCP port/ADB forward serves both.

APK SHA-256:
`5133971b9ab4cf0639535823a7802d9ea493e19fc28ace632fe46cfffde93826`.
The APK builds and its v3 signature verifies. Offline full stock replay passes
with two transports; hardware validation of concurrent sessions is separate from
the earlier one-session check-only evidence above. Modified-image eligibility
requires exact stock-source manifest reproduction as documented in
`analysis/stock-driver.md`; no generic image bypass was added.
