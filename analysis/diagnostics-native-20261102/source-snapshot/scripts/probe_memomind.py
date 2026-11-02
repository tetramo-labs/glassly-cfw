#!/usr/bin/env python3
"""Read-only public heartbeat and device-info probe via Android RFCOMM bridge.

Does not enter OTA mode, alter device settings, install plugins, or flash.
"""
import argparse
import json
from pathlib import Path

from memomind_transport import RfcommBridge, GmStream, gm_frames, await_gm


def probe(transport, address, legacy_repeat_fa=False):
    connection = transport.connect(address, "control")
    parser = GmStream(legacy_repeat_fa=legacy_repeat_fa)
    unsolicited = []
    transport.write(gm_frames(1, 1, 1)[0])
    heartbeat = await_gm(transport, parser, 1, 1, 1, unsolicited=unsolicited)
    status = [value[0] for kind, value in heartbeat["tlvs"] if kind == 6]
    if status != [0]:
        raise RuntimeError(f"Heartbeat did not return STATUS 0: {status}")
    transport.write(gm_frames(2, 1, 2)[0])
    info = await_gm(transport, parser, 2, 1, 2, unsolicited=unsolicited)
    strings = [value for kind, value in info["tlvs"] if kind == 2]
    if len(strings) != 1:
        raise RuntimeError("Device-info response did not contain exactly one STRING TLV")
    device = json.loads(strings[0].decode("utf-8").rstrip("\0"))
    if not isinstance(device, dict):
        raise RuntimeError("Device-info JSON was not an object")
    return {"connection": connection, "heartbeat_status": 0, "device": device,
            "unsolicited": unsolicited, "operations_sent": ["heartbeat", "device_information"]}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--address", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=38741)
    p.add_argument("--trace", type=Path, help="New JSONL trace file (exclusive creation)")
    p.add_argument("--legacy-repeat-fa", action="store_true")
    args = p.parse_args()
    trace = args.trace.open("x") if args.trace else None

    def record(row):
        trace.write(json.dumps(row) + "\n")
        trace.flush()

    try:
        with RfcommBridge(args.host, args.port, trace=record if trace else None) as transport:
            result = probe(transport, args.address, args.legacy_repeat_fa)
        print(json.dumps(result, indent=2))
    finally:
        if trace:
            trace.close()
