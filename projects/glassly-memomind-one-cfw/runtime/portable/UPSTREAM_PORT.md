# Portable routing, settings and telemetry compatibility core

`upstream.c/.h` extracts production protocol and policy from G2 commit
`1a6db4fd75de202a96599cc8f9f12fa721e7c3ce`. The upstream license and
source hashes are retained in `tests/g2_compat/upstream` and
`tests/g2_compat/UPSTREAM.json`. The standalone runner verifies every source used.
This is a compatibility core, not a native MemoMind settings implementation.

| Original source | Extracted behavior | Portable API |
| --- | --- | --- |
| `protobuf.c` | Capacity-checked length-delimited extension encoding | `mm_upstream_append` |
| `settings_ext.c` | Varint parsing, six extension-control routes, bounded response extensions and separate battery notification after successful send | `mm_upstream_scan`, `mm_upstream_settings_send` |
| `zlib_glue.c::is_shadow_message` | Original raw/RLE mode classification | `mm_upstream_shadow` |
| `ring_battery.c` | Connected/valid/charging flags, unknown level, query packet | `mm_upstream_battery_append`, `mm_upstream_battery_query` |
| `compass.c` | Source precedence, magnetic diagnostic fallback, timestamp-keyed 20-sample sidecar and backward record selection | `mm_upstream_capture_sample`, `mm_upstream_heading` |
| `ble_link.c` | Fast/stock flag transitions, profile policy, classification, generation-bearing deferred request and status | `mm_upstream_filter/classify/request/link_control/link_cleanup/link_status` |

Production accepts typed profiles, explicit connection interval/latency, normalized
sensor samples, battery values and callbacks. It contains no G2 memory addresses,
GAF offsets, connection-record offsets, native profile byte casts, ARM hooks or
context singleton. The test-only adapter decodes original fake layouts and
encodes them back for original assertions. Actual production policy determines
those outputs; the adapter does not copy the upstream state-machine algorithms.

## Contracts and caller responsibilities

Zero-initialize each `mm_upstream_state`. Each caller owns and serializes its
state and callbacks; this core adds no allocator, locks, timers or persistent
settings writes. Input buffers must remain valid and immutable during calls.
Output buffers must have their declared capacity. Callbacks must not reenter the
same state or mutate input while a call is in progress.

The protobuf scanner preserves the original incremental behavior: valid earlier
fields may dispatch before a later malformed field stops scanning. This is not
an atomic multi-command transaction. It recognizes only fields 101, 103, 126,
127, 130 and 132 and delegates their bodies; it does not implement their native
handlers. Its unsigned varint behavior is inherited from the original parser.
The public wrapper bounds the message to 65,535 bytes.

Extension append performs all space checks before writing. The portable boundary
also rejects invalid fields/null payloads and overlapping payload/output storage.
Settings response composition takes a caller-supplied extension list, at most 32
items. Descriptors and payloads must not overlap its response buffer. Optional
extensions that do not fit remain omitted, exactly as the original appender.
The core does **not** hard-code `GLASSLYCFW/50`; only the original test fixture
supplies that string. Callers must advertise capabilities they actually support.
Diagnostics/microphone/volume blocks in the host fixture are mock status bytes;
their presence tests do not implement those feature state machines.

Settings channel 9, compass channel 8, field numbers, mode values and side 1 are
preserved **logical G2 compatibility values**, not MemoMind native service IDs.
The sender callback copies/consumes stack payloads before returning. On a failed
settings send the battery notification is suppressed. A successful settings send
is followed by the separate battery query notification; its send result does not
change the original response's result, matching upstream. No notifications are
retried by this core.

The battery provider supplies connected, charging and level values. A level over
100 is unknown even while connected; disconnected is also unknown. The core does
not discover, connect, poll or claim existence of a MemoMind ring accessory.

Heading capture takes already normalized GRV/GMRV/RV validity and magnetic
metadata. The adapter decides when a decoded sample is available; no GAF buffer
is read here. The core preserves source precedence and timestamp matching,
including unknown diagnostics for missing/stale samples. Heading output requires
an explicit forward flag, eligible side and 0–359 degree value. The caller keeps
native stock-event forwarding separate. The native magnetic-accuracy preservation
hook and sensor ownership/reconfiguration are not extracted or verified.

BLE policy takes typed min/max interval, latency, timeout, retries and opaque
profile metadata. Fast mode requests interval 6 (1.25 ms units) and latency zero,
copying the remaining stock profile values. It clears applied mode, updates
wanted mode, cancels and posts a generation-bearing request through callbacks.
Profile objects selected by a callback must remain valid until replaced; the
state must not be freed while its profile is installed. The native adapter must
serialize profile mutation and restore stock before releasing state. The core
never dereferences its opaque native connection argument. Native mode numbers,
scheduler generation semantics and actual profile storage require an adapter.

This BLE interval policy does **not** speed up MemoMind's classic RFCOMM app
transport. Whether it is useful for a separate MemoMind BLE/HOGP connection is
pending native investigation. No radio requests are performed by host tests.

## Test mapping and evidence

Run:

```
python3 runtime/portable/tests/run_upstream_tests.py --output NEW_DIRECTORY
```

The runner checks all source pins, all 78 original assert expressions in order,
unchanged bodies of `routing`, `batteries`, `settings`, `headings` and `ble_link`,
and exactly one call to each in `main`. It records and requires 25,620 runtime
assert evaluations. All original scenario fixtures execute against linked
`upstream.c`. Original native-address/callback assertions use the test-only shim,
so the file remains **mixed: portable core tested, native adapter pending**.

`analysis/portable-upstream-tests-01/report.json` records both the original suite
and independent public API tests passing ASan/UBSan. Extra tests cover 20,000
malformed packets, all 256 mode bytes, two states, nonzero request generations,
normalized profiles, null/bounds/alias rejection, failed-send composition and
heading timestamp mismatch. Mapping and exact assertion provenance are in
`tests/upstream/mapping.json` and the report's `assertion-map.json`.

The pinned RV32 GCC 15.2.0 build (`rv32imafc/ilp32f`) has 2574 text bytes, no
rodata, no unresolved imports and no writable globals. State is 180 bytes; the
optional link-callback table is 52 bytes. Typed profile is 16 bytes, sample and
record eight bytes each. There is no dynamic core allocation. Largest individual
stack frame is 80 bytes, excluding call chains, native callbacks and adapter
buffers; this is not a task-stack claim or machine-execution test.

## Native work still pending

MemoMind's documented head-up settings already use normal GM service 1. The
separate evidence `analysis/ghidra/input-settings/report.md` establishes ranges,
setter ownership and that several write ACKs can mask setter failure. None of
this host suite performs a GM setting write, checks readback, or demonstrates
physical head-up/wake behavior. A native settings adapter must validate ranges,
retain existing user values, compare exact query readback and test physical
behavior in stock and custom-scene contexts. G2 extension routing is not that
adapter, and the suite's settings response test never covered that behavior.

Native accessory battery source/lifecycle, heading source/diagnostic mapping,
stock event hooks, BLE scheduling/profile ownership, transport routing and
truthful runtime capability publication remain pending. Full-suite/full-port
completion remains false. No phone, glasses, source checkout, main test runner
or global inventory was modified for this port.
