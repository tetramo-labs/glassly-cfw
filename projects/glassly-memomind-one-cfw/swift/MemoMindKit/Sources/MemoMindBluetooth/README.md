# Native macOS RFCOMM transport

`MacRFCOMMTransport` implements `MemoMindCore.MemoMindTransport`. Call it on
the main thread from a synchronous CLI/main-run-loop context. It is deliberately
not Sendable. Do not call it directly from a Swift task-pool executor.

```swift
let transport = MacRFCOMMTransport(traffic: { event in
    // Persist event.kind, timestamp, uptime, status and every event.data byte.
    // Throw if durable logging fails. Do not reenter the transport here.
})
defer { transport.close() }
try transport.connect(address: address, service: .normal) // .ota for update service
try transport.write(request)
let bytes = try transport.read(timeout: 10)
```

Each instance permits one connection attempt. Instantiate a new transport for a
later explicit connection. There are no automatic retries, scans, pairing requests,
channel-ID fallbacks, or application commands. Normal UUID is
`00007033-0000-1000-8000-00805f9b34fb`; OTA is
`00007034-0000-1000-8000-00805f9b34fb`, matching
`android_bridge/src/org/memomind/research/bridge/BridgeActivity.java:190` and captured
SDP evidence in `analysis/protocol.md`. RFCOMM channel numbers come from the
UUID-matched cached SDP service record when available; otherwise a bounded
asynchronous SDP query must complete. Channels must be in 1...30. There are no
hard-coded channels or fallback after a query timeout. On the tested Mac, fresh
SDP completion did not arrive even after successful pairing; the cached record
opened the service successfully. `serviceDiscoverySource` and `resolvedChannelID`
expose the selected record source and channel, and the CLI logs both.

Public extras:

- `checkHealth()` throws any retained failure, including receive overflow or a
  traffic-log error on an idle normal channel while OTA is active.
- `drainReceived()` returns currently queued `[Data]` chunks without waiting.
  These are stream chunks, not GM messages. It throws if the session has failed.
- `lastFailure` retains the first terminal error; `lastCloseStatus` exposes the
  native channel-close result. `close()` is main-thread-only and nonthrowing.
- `pairedDevices()` reads local paired-device records; `hostStatus()` reads local
  controller availability, power state, name and address. Neither initiates a
  discovery, pairing operation or remote connection.

Default deadlines: one total 20-second SDP+open deadline; one total 10-second
write deadline across all MTU chunks. Read accepts a caller deadline. Values must
be finite, positive and at most 300 seconds. Read timeout throws but leaves the
healthy channel open. Open/write failure closes the channel, since partial
transmission may already have occurred. The monotonic clock controls deadlines;
the default main run loop is pumped while waiting and at operation entry, so
callbacks for another normal/OTA transport can run. These are application
deadlines, not a hard real-time guarantee against a stalled framework entry point
or a blocking application/log/run-loop callback.

Receive storage is bounded to 1 MiB by default and 4096 callback chunks; exceeding
either fails closed. Configurable byte limits are clamped to 0...16 MiB. Successful
read/drain releases queued bytes. An overflow callback is rejected before copying
or logging it, so a failed-overflow session must not be described as a complete
capture. RX bytes are copied before the native callback returns. Data is never
interpreted as text. Writes split only at the discovered MTU/UInt16 API limit and
pin each buffer until completion or confirmed channel closure.

Traffic phases are intentionally distinct: `transmitSubmission` runs before the
native call; `transmitCompletion` contains its native completion status. Successful
completion means passed to Bluetooth hardware, not acknowledged by the glasses.
RX entries use `receive`. A logging exception stops the connection. Callbacks must
be bounded; transport timeouts cannot interrupt a blocking logger.

Delegate lifetime follows Apple's header warning that modern IOBluetooth does
not retain RFCOMM delegates. The session pins itself while a channel is active or
asynchronous SDP/open/write completion remains outstanding. Timeout closes the
RFCOMM channel without closing the shared baseband ACL. A late open completion is
closed. Confirmed closure detaches the delegate and releases its write buffer.
If the framework never delivers a pending completion/closure, that single-use
session stays retained rather than allowing a dangling delegate/buffer. Callers
must not implement an unbounded reconnect loop around this failure.

API grounding: local macOS SDK `IOBluetooth.framework/Headers/objc/`:
`IOBluetoothDevice.h` (async SDP/open), `IOBluetoothSDPServiceRecord.h`
(`getRFCOMMChannelID`), `IOBluetoothRFCOMMChannel.h` (MTU, asynchronous write,
delegate ownership, callbacks, close), and `IOBluetoothHostController.h` (read-only
controller status). Compiled against the installed Xcode macOS 27 SDK, deployment
target macOS 13. The source is excluded on non-macOS platforms.

Validation on 2026-11-01: standalone API probe and full transport typecheck passed,
including Swift 6 typechecking. A same-file temporary harness passed 23 offline
checks: timeout/address/disconnected validation, exact service UUIDs, copied RX
lifetime, overflow, durable-log failure, invalid callback, write-buffer token and
completion handling, pinned active delegate and confirmed-close release. Callback
state was injected directly with nil channel identity; no controller or remote
device was constructed. Those offline checks do not establish radio behavior. Subsequent hardware work
paired the glasses, probed their identity and transferred the complete reader OTA
using cached SDP records. The first post-reboot connection timed out; a new
connection after the user woke the glasses verified the exact runtime profile
and full 256-byte application header. See the historical transfer report at
`analysis/native-mac-hardware-20261101/report.json` and the subsequent boot/storage
verification at `analysis/native-mac-preflight-20261101/verification.json`.
