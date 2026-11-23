# Captured normal app and connection behavior

Target: MemoMind One H001Y, Android app1.3.81. The main trace starts before a
Bluetooth restart and continues through stock OTA1.0.3.127, its reboot, service
reconnection and normal settings activity. Initial bonding happened earlier;
the capture does not contain first-time pair/key creation.

`captures/general-session.btsnoop` and
`captures/session-20261030-2019/actions.jsonl` preserve traffic and action markers.
`analysis/protocol/general-session/normal-frames.json` inventories the observed
GM frames. Raw HCI includes Classic links and their SDP/audio-control activity;
these phone/glasses command sessions used RFCOMM, not ATT/GATT.

| Observed action | Captured effect |
|---|---|
| Bluetooth off/on | Reconnection, SDP and subsequent command/service traffic |
| Open firmware screen | Current-version and OTA-check logs, then stock update sequence |
| Post-update Display settings | Service1/command6 query, JSON status response split across physical frames |
| Eco Mode off→on | Service1/command0x2a, INT8 value1; response STATUS0 |
| Restore Eco Mode on→off | Service1/command0x2a, INT8 value0; response STATUS0 |
| Other app writes accompanying Eco Mode | Service1/command0x38 value0 on both transitions and command0x2b value0 after off; these observations do not assign their semantics |
| Independent client heartbeat | Service1/command1, STATUS0 through our built Android/Python bridge |
| Independent client device info | Service1/command2, fresh H001Y version1.0.3.127/hardware2.1.2/front1.3 |
| Independent native capabilities | Service15/command0x20, empty request, type5 JSON with ABI/display/cache limits |
| Independent stock eligibility check | Service1/command0x1c, then OTA attach0x02, identify0xe1 and eligibility0xe2; result3 on1.0.3.127; stopped before entry0xe3 |

Eco Mode was restored to off; the additional Monocular row disappeared as it
had been absent initially. Independent probes sent no OTA-entry, plugin-install
or firmware-write commands. Their JSONL traces and HCI snapshots are under
`captures/probe/`. The research bridge was force-stopped and its ADB port forward
removed afterward, and MemoMind was reopened.

This is a record of exercised behaviors, not exhaustive coverage of every app
feature. Microphone recording, account actions, factory reset, unbinding and
first-time pairing were not exercised by these probes.

The later eligibility check is under `captures/probe/ota-check-01/`. It changes
transient updater state, but sent no entry/data/finalize/reboot command. Its
before/after HCI files contain one timestamp regression of546 microseconds at
record10964, present before the check began. Both files parse to their exact
ends, with no truncated records. The reason for that timestamp ordering is
unknown; see `evidence/ota-check-capture-timing.json`. The earlier frozen
successful-OTA capture does not have this anomaly. Record order and the bridge's
raw timestamped trace preserve the independent handshake evidence.
