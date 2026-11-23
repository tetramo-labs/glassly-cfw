# Offline Android BLE HID keyboard fixture

This is a separate test-peripheral APK, **built and signed locally, never installed or run on a phone in this task**. It leaves `android_bridge/` unchanged. It provides a small HID-over-GATT keyboard for a future explicitly operated glasses test. It is not a certified HOGP implementation or evidence that a phone can successfully act as the glasses' keyboard while retaining its primary Classic connection.

Build and validation:

```sh
python3 android_hid_fixture/tests/run_tests.py
python3 -m unittest discover -s android_hid_fixture/tests -p 'test_*.py' -v
sh android_hid_fixture/build.sh
python3 android_hid_fixture/tests/verify_apk.py
```

Uses the existing local Android36 SDK/build-tools36.0.0 and JDK21; no Gradle/download/global installation. Override `ANDROID_SDK_ROOT` and `HID_JDK`. APK: `build/memomind-hid-fixture.apk`; package `org.memomind.research.hid`, minimum Android13/API33, target36. Signing key `.debug.keystore` stays local and is ignored. APK v3 signature verification and manifest inspection passed. [validation.json](validation.json) pins the APK/source/test evidence. The debug manifest permits `run-as` log retrieval; this is a local research artifact, not a release build.

## Lifecycle and authorization boundary

Opening the Activity alone displays permission/start/stop controls. The explicit **Start bounded controller service** button (or launch flag `--ez start_controller true`, handled after Activity resume) starts a non-exported `connectedDevice` foreground service with a visible notification and STOP action. It opens only a loopback listener at `127.0.0.1:38742`; BLE remains off. The service requires CONNECT, ADVERTISE and POST_NOTIFICATIONS permissions plus an enabled notification channel. It does **not** open a GATT server, advertise, initiate pairing, connect, or inject a report before the authenticated controller's explicit `start` command.

One authenticated controller is allowed; extra sockets are closed. Supply a32..128-character random launch token, or use the generated token shown for a new service. Reopening the Activity never replaces an existing service's token or lease. The first JSON line must be `hello` with the token. Invalid authentication shuts down the service. The token is never written into the fixture log. This is access control for ordinary loopback clients, not a security boundary against root/ADB or another app able to manipulate this debug Activity.

An explicit `start` registers services one at a time, waits for all three `onServiceAdded` callbacks, then starts connectable legacy advertising. Its immediate response means **accepted**, not advertising success; wait for the `advertising` event. The advertisement includes HID service UUID0x1812, with the **existing Android adapter name** in scan response. No adapter rename, scanning, bond creation/removal or pairing confirmation API is used. If the name is absent, advertising is rejected; an oversized platform name/unsupported advertiser can cause an asynchronous failure.

Only one GATT peer is accepted. Advertising stops once it connects. Peer disconnect closes the GATT fixture and requires another explicit `start` within the still-active controller lease. JSON `stop`, the Activity STOP button, notification STOP/dismiss, controller loss, Bluetooth shutdown, disabled notification permissions/channel, service destruction, or log-queue overflow tears down advertising/GATT, the listener, controller and foreground service. JSON STOP allows250ms for its best-effort reply before closing; it immediately revokes the lease, so subsequent commands cannot restart BLE. STOP remains accepted at the lease boundary.

The service waits at most120 seconds for authentication. After successful authentication, it has a **nonrenewable600-second hard lease** and a120-second idle lease. A complete authenticated request can refresh the idle deadline but never the hard deadline; partial incoming bytes cannot keep it alive. A one-second watchdog enforces expiry and notification availability, subject to Android scheduling. The service uses `START_NOT_STICKY`: no restart after process death, boot receiver, reconnect loop or implicit advertising. A new session after stop/expiry requires explicitly starting the controller service again from the Activity.

The Activity has no `onStop`/`onDestroy` teardown. The service owns listener, GATT, callbacks and watchdog independently, so switching to the existing RFCOMM bridge or showing system pairing UI does not itself stop the fixture. The existing bridge likewise has no `onStop` teardown and was not edited. This closes the application lifecycle conflict; concurrent radio/bond operation and Android process-survival behavior still require hardware validation. Notification STOP remains available when the fixture UI is hidden. POST_NOTIFICATIONS is deliberately required even though Android permits some foreground services without drawer notifications. There is no automatic bond confirmation, wake lock or automatic typing.

There is no automatic key release. Send `release` explicitly and wait for `notification_sent` before stopping if a report was previously submitted. Teardown never injects an extra report. A host's response to disconnect while a key is held is outside the fixture's control.

## Future operator CLI (documented, not executed)

Review same-phone/bond interactions below before installing or starting. Commands intentionally use an explicitly chosen serial rather than implicitly selecting a device.

```sh
# Set PHONE_SERIAL to the reviewed test phone. These device commands were NOT run.
adb -s "$PHONE_SERIAL" install -r android_hid_fixture/build/memomind-hid-fixture.apk
adb -s "$PHONE_SERIAL" shell pm grant org.memomind.research.hid android.permission.BLUETOOTH_CONNECT
adb -s "$PHONE_SERIAL" shell pm grant org.memomind.research.hid android.permission.BLUETOOTH_ADVERTISE
adb -s "$PHONE_SERIAL" shell pm grant org.memomind.research.hid android.permission.POST_NOTIFICATIONS
umask 077
openssl rand -hex 16 > /tmp/memomind-hid-token
HID_CONTROL_TOKEN=$(cat /tmp/memomind-hid-token)
adb -s "$PHONE_SERIAL" shell am start -n org.memomind.research.hid/.HidActivity --es token "$HID_CONTROL_TOKEN" --ez start_controller true
adb -s "$PHONE_SERIAL" forward tcp:38742 tcp:38742
python3 android_hid_fixture/control.py --token-file /tmp/memomind-hid-token
```

The CLI authenticates and prints replies/events; it sends no automatic start, key, release, or heartbeat. Type individual JSON lines interactively. EOF/Ctrl-C closes the controller and therefore stops the fixture. Do not pipe a one-line `start` command then expect advertising to persist after stdin closes.

First, inspect status. Starting is a separate explicit action:

```json
{"id":1,"op":"status"}
{"id":2,"op":"start","security":"encrypted"}
```

Any remote central can discover/connect while advertising; verify the logged peer address and bond state before report injection. The fixture does not select or drive the glasses' scan/connect operation. A future glasses controller must separately request that using the existing HOGP gateway. Do not silently replace an existing accessory/bond.

After the intended peer connects, finishes security/discovery, and enables the correct CCCD, an explicit Up-arrow press and explicit release are:

```json
{"id":3,"op":"report","hex":"0000520000000000"}
{"id":4,"op":"release"}
```

Wait for `notification_sent` after each submitted report; if another is pending the next submission is rejected. No report is sent until the operator issues one. The eight bytes are modifier, reserved0, six Keyboard/Keypad usage slots. **Do not prepend Report ID1** to a GATT report value. These examples will affect a connected host if eventually executed; they were not executed in this task. `notification_sent` confirms the Android stack result, not a visible glasses action.

```json
{"id":5,"op":"stop"}
```

Cleanup after a future run:

```sh
adb -s "$PHONE_SERIAL" forward --remove tcp:38742
adb -s "$PHONE_SERIAL" shell am force-stop org.memomind.research.hid
rm /tmp/memomind-hid-token
```

Do not unbond/reset Bluetooth as routine cleanup: bonds are shared system state. The app never removes them.

## JSON protocol and logs

UTF-8 JSON lines, maximum4096 bytes per request, protocol1. Requests have `id` and `op`; responses echo `id` with `ok:true,result:{...}` or `ok:false,error`. First request:

```json
{"id":"hello","op":"hello","token":"<launch token>"}
```

| Operation | Fields / behavior |
| --- | --- |
| `status` | Starting/advertising/registered/connected, current peer, protocol0boot/1report, suspend state, CCCDs, pending notification, MTU, security, generation, remaining lease and hard deadline in elapsedRealtime milliseconds. No radio mutation; refreshes idle lease only. |
| `start` | `security:"encrypted"` default. Opens a new fixture run and registers all services; errors if already started. Explicit `security:"open"` is a diagnostic mode, **not HOGP security conformance**. |
| `stop` | Immediately revokes the lease, stops advertising and cancels this server's peer. Closes controller/listener/foreground service after a best-effort reply. Does not delete system bonds. |
| `report` | `hex` exactly8 bytes, reserved byte0, usages0..101, no duplicate nonzero usages. Modifiers0..255. Requires active peer/protocol CCCD, not suspended, no pending notification. No sequences, delays or implicit release. |
| `release` | Explicit all-zero8-byte report, with identical eligibility checks. |

Events include service registration, advertising success/failure, adapter state, connection and bond state, pairing **variant only**, MTU, characteristic/descriptor reads and writes, offsets, response-needed/prepared flags, ATT responses, submitted reports, notification completion and stop reasons. `elapsedRealtimeNanos` provides the device monotonic clock. The callback values contain report/LED bytes, not SMP keys. The implementation never reads `EXTRA_PAIRING_KEY`, PINs, LTKs, IRKs or link keys and never confirms a pairing prompt.

After authentication, the writer stores JSONL to private `files/hid-<timestamp>.jsonl` and streams the same events/replies. It uses a bounded1024-line queue; overflow stops the fixture and attempts to append `log_overflow` with `lossless:false`. It is not guaranteed lossless under process death, disk failure or a stalled host. A future log can be retrieved with:

```sh
adb -s "$PHONE_SERIAL" shell run-as org.memomind.research.hid ls files
adb -s "$PHONE_SERIAL" exec-out run-as org.memomind.research.hid cat files/hid-CHOSEN_TIMESTAMP.jsonl > captures/hid-fixture-CHOSEN_RUN.jsonl
```

The server log records current peer addresses and input reports; keep it task-local. The app currently records bond/pairing broadcasts only for its connected GATT peer. It cannot prove every system-wide security transition, transport-specific encryption level, ATT packet on air, HCI event, OS-internal request rejection, or hidden stack retry. Capture HCI separately in a future live experiment if those are needed.

## GATT / HID contract

All UUIDs use the Bluetooth base UUID. Android assigns attribute handles; do not hardcode them. Two distinct Report characteristics share UUID0x2a4d and are distinguished by their Report Reference descriptors.

| Service / characteristic | Properties and value |
| --- | --- |
| HID1812 / Information2a4a | Read; `11 01 00 02` (HID1.11,country0,NormallyConnectable; no remote wake). |
| HID / Report Map2a4b | Read;69-byte Keyboard Application descriptor, Report ID1; input64bits, output8bits. Read Blob offsets and negotiated MTU slices supported. |
| HID / Input Report2a4d | Read+Notify;8 bytes without ID. Report Reference2908=`01 01`; CCCD2902 accepts only0000/0100 (disable/notify). |
| HID / Output Report2a4d | Read+Write+WriteWithoutResponse;1 byte, five LED bits and three zero padding bits. Report Reference=`01 02`. |
| HID / Protocol Mode2a4e | Read+WriteWithoutResponse; initial1report,0boot accepted. Switching clears local input value without sending it. |
| HID / Control Point2a4c | WriteWithoutResponse;0suspend,1exit suspend. Injection is rejected while suspended. |
| HID / Boot Keyboard Input2a22 | Read+Notify;8 bytes, separate CCCD. |
| HID / Boot Keyboard Output2a32 | Read+Write+WriteWithoutResponse;1-byte LEDs. |
| Battery180f / Level2a19 | Read; fixed100. This is test data, not the phone battery. No notifications or battery report embedded in HID map. |
| Device Information180a | Manufacturer2a29,Model2a24,Firmware2a26; PnP ID2a50 has test source1/vendor0/product0/version1. The zero vendor/product identifiers are deliberately unassigned local fixture identifiers, not a claim of a registered product. |

Encrypted mode marks all HID reads/writes/descriptors with Android encrypted permissions; Battery/Device Information remain readable. It does not require MITM and cannot choose the OS's I/O capability or SMP algorithm. Attribute permission enforcement is delegated to Android; encrypted notification delivery is not independently proven. Prepared/execute writes are rejected, write offsets must be0, read offsets beyond the value reject, and EOF offsets return empty success. The fixture supports a simple six-key keyboard subset; it deliberately rejects duplicate nonzero usage arrays, including USB ErrorRollOver repeat arrays. Battery, manufacturer and firmware data are deterministic.

State (including CCCDs) resets for each fixture run; bonded-peer CCCD persistence/reconnect behavior and full HOGP qualification are outside this first fixture. A host which assumes persisted subscriptions may need an explicit rediscovery/resubscription workflow; do not silently clear a bond to fix this. These limitations, the unassigned test PnP identity and Android-managed GAP appearance mean this APK must not be labelled HOGP-certified or generally interoperable.

## Android and same-phone coexistence limits

The API choice is Android's GATT server/LE advertiser, **not** `BluetoothHidDevice`, which is a different HID profile API. API33 permits immutable-value notification submission; the build requires that version. CONNECT, ADVERTISE and POST_NOTIFICATIONS are runtime permissions. FOREGROUND_SERVICE and FOREGROUND_SERVICE_CONNECTED_DEVICE authorize the declared service type; no SCAN, location, privileged Bluetooth, bond editing or root capability is requested. Support still depends on the controller/OS offering peripheral advertising and concurrent links. See the official [GATT server API](https://developer.android.com/reference/android/bluetooth/BluetoothGattServer), [callback contract](https://developer.android.com/reference/android/bluetooth/BluetoothGattServerCallback) and [advertiser API](https://developer.android.com/reference/android/bluetooth/le/BluetoothLeAdvertiser).

The same phone already carries the glasses' primary BR/EDR connection in the parent investigation. LE identity/bonds are system-wide, not per app. Bluetooth cross-transport key derivation can relate BR/EDR and LE keys under specified conditions; this app cannot disable CTKD or guarantee that a new LE pairing will preserve the primary transport's bond/session. It also cannot guarantee that `cancelConnection` affects only the desired logical link on every Android/controller combination. This is an interoperability concern to investigate, **not a finding that the connected phone has a CTKD vulnerability**. The relevant normative context is [Bluetooth Core GAP](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-62/out/en/host/generic-access-profile.html); the [SIG security guidance](https://www.bluetooth.com/download/bluetooth-security-and-privacy-best-practices-guide/) explains cross-transport key relationships.

Another separate test phone/peripheral may provide a cleaner experiment if shared identity/bond ownership prevents this arrangement. No scan, advertisement, pairing, connection, notification, install or phone control was performed while preparing this APK. The existing RFCOMM bridge was not edited, but concurrent operation with it remains untested. The host's local HOGP manager owns one accessory and may reject an already-bonded/different target; see [native keyboard boundary](../analysis/ghidra/keyboard-adapter/report.md).

## Evidence scope

`tests/run_tests.py` compiles and executes the **actual APK's Android-independent ATT model** on JDK21:1089 assertions cover every usage byte/modifier/LED value, CCCD validation, protocol switching, suspend, notification backpressure, prepared writes, offsets/lengths, read-map fragmentation across MTUs23/40/64/247/517 and reset. Its independent HID short-item decoder checks top-level Keyboard Application, Report ID, input64/output8bits, modifier/reserved/array layout, output logical range and both Report References. Three loopback-only CLI tests confirm EOF produces no implicit start/report, only an explicitly supplied status is sent, and unknown/oversized requests are rejected without transmission. APK build, dex packaging, min/target SDK, permission list and v3 signature are inspected separately.

The actual `ControllerLease` used by the service also passes1827 assertions covering the pre-auth deadline, rejected unauthenticated/duplicate authentication, exact idle/hard boundaries, repeated idle renewal without hard extension, irreversible STOP, and64-bit monotonic uptime.

The service lifetime follows the official [connected-device foreground-service requirements](https://developer.android.com/develop/background-work/services/fgs/service-types) and [foreground-service notification contract](https://developer.android.com/develop/background-work/services/fgs). Its visible notification/channel is required by the fixture and periodically checked. APK inspection verifies the non-exported service, `connectedDevice` type and `stopWithTask=false`.

These tests do not emulate Android Binder/GATT callbacks, the controller radio, SMP, scheduling, OS permissions/pairing UI, service-cache behavior, disconnection semantics, or real glasses parsing. No hardware result is implied. HOGP field semantics follow the [Bluetooth SIG HOGP specification](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/hogp_v1-2_1777405843/HOGP_v1.2/out/en/index-en.html); no conformance certification was attempted.
