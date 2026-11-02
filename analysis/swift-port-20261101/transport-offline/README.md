# Retained offline macOS transport checks

The original 23-check harness is retained verbatim as `checks.swift.txt`.
`original-checked-combined.swift.txt` preserves the exact temporary source compiled
for the earlier result; its transport prefix is separately retained as
`original-checked-transport.swift.snapshot`. The original core source snapshot was
not retained then, so the earlier combined source is provenance, not a claim to
fully reproduce that historical binary.

`run-001` reran all 23 checks successfully against the **current formatted**
production transport, snapshotted as `MacRFCOMMTransport.swift.snapshot`, and
current `Protocol.swift`, snapshotted as `Protocol.swift.snapshot`. These snapshots
match production bytes at the time of this run. `report.json` records SHA-256
values for both old and current source; it does not assume their difference is
formatting alone. Production transport hash for this run:

`f8936e33b772239ca2a59071f2b95b5e58f4996f0c2a96f8bea5f53101f1d2d5`

Reproduce on macOS with Xcode installed:

```sh
bash analysis/swift-port-20261101/transport-offline/run.sh run-002
```

Use a new simple directory name each time. The runner refuses an existing output
directory. All generated files and compiler caches remain inside this evidence
directory. The runner compiles the frozen snapshots, not potentially changing
production files. It does not modify the package, production source or test suite.

`run-001/compiler.stderr` records the exact expanded compiler/linker commands.
`compiler-version.txt`, `sdk.txt`, `architecture.txt`, and `inputs.sha256` record the
environment and inputs. Both compiler commands completed successfully. The actual
arm64 executable output in `run-001/stdout.txt` is:

```text
PASS 23 offline transport checks; no device/controller calls
```

The harness concatenates production source and assertions in one Swift file to
reach the private delegate class without changing access control in production.
The actual current `Protocol.swift` is compiled as a small MemoMindCore library to
provide the transport protocol and its other standalone definitions; this is not
a full firmware-validation or OTA transaction test.

Covered checks include invalid timeout/address/disconnected argument handling,
exact service UUIDs, copied receive bytes surviving mutation of the source buffer,
receive overflow, logger failure, invalid data callback, wrong write token ignored,
correct token completing and releasing its buffer, write-completion error, active
delegate retention, and confirmed-close state release.

Important limits:

- No IOBluetooth device or controller is constructed. The two `connect` calls
  fail validation before `IOBluetoothDevice(addressString:)` can execute. No valid
  address with a valid timeout is supplied. Local paired-device/status methods
  are not called.
- Delegate state is injected directly with a **nil channel** whose identity
  matches the initially nil stored channel. This tests Swift state handling,
  not real IOBluetooth callback scheduling, channel ownership, SDP, transmission,
  MTU fragmentation or remote acknowledgements.
- Timeout assertions check invalid arguments, not elapsed real-operation deadline
  expiry. `mustThrow` checks for an error, not its specific enum case.
- The harness does not prove reentrancy behavior, background-thread callbacks,
  late SDP/open completion, actual close return values, or framework lifetime
  behavior. It cannot establish Bluetooth permissions, pairing, connectivity or
  successful OTA behavior.

The parent's separate native Mac attempt timed out during SDP before application
bytes. That observation is not produced or explained by these offline checks, and
no retry or device action was performed for this evidence preservation.
