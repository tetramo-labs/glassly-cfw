#!/usr/bin/env python3
"""Verify the opt-in runtime reply and unchanged stock capability handler."""
import argparse
import json
from pathlib import Path

from memomind_transport import RfcommBridge, GmStream, gm_frames, await_gm
from probe_memomind import probe

EXPECTED = {'glassly': 'runtime-probe', 'abi': 1, 'profile': 'H001Y-1.0.3.127',
            'entry': '0439bea0', 'writableStaticBytes': 0}


def json_reply(message):
    values = [v for k, v in message['tlvs'] if k == 5]
    if len(values) != 1:
        raise RuntimeError('Expected exactly one JSON TLV, got: '+
                           repr([(k, v.hex()) for k, v in message['tlvs']]))
    result = json.loads(values[0].decode().rstrip('\0'))
    if not isinstance(result, dict):
        raise RuntimeError('Expected JSON object')
    return result


def verify(transport, address, count=16):
    if not 1 <= count <= 64:
        raise ValueError('Probe count must be 1..64')
    initial = probe(transport, address, legacy_repeat_fa=True)
    parser = GmStream(legacy_repeat_fa=True)

    def query(event, command, body=b''):
        transport.write(gm_frames(event, 15, command, body)[0])
        return json_reply(await_gm(transport, parser, event, 15, command))

    before = query(3, 0x20)
    for event in range(4, count+4):
        runtime = query(event, 0x7e)
        if runtime != EXPECTED:
            raise RuntimeError('Unexpected runtime identity: '+repr(runtime))
    # Exercise ownership of a valid, nonempty request TLV list once.
    if query(0xe0, 0x7e, bytes.fromhex('0800000101')) != EXPECTED:
        raise RuntimeError('Nonempty diagnostic request failed')
    after = query(0xe1, 0x20)
    if before != after:
        raise RuntimeError('Stock capability query changed during diagnostic probes')
    transport.write(gm_frames(0xe2, 1, 1)[0])
    heartbeat = await_gm(transport, parser, 0xe2, 1, 1)
    if heartbeat['tlvs'] != [(6, b'\x00')]:
        raise RuntimeError('Post-probe heartbeat failed')
    return {'device': initial['device'], 'runtime': runtime,
            'empty_probe_queries': count, 'nonempty_probe_queries': 1,
            'stock_capabilities_before': before, 'stock_capabilities_after': after,
            'stock_capabilities_unchanged': True, 'post_probe_heartbeat': 0,
            'limitations': ['Repeated replies do not measure heap use or prove absence of leaks.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address', required=True)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=38741)
    p.add_argument('--count', type=int, default=16)
    p.add_argument('--trace', type=Path, required=True)
    args = p.parse_args()
    with args.trace.open('x') as trace:
        def record(row):
            trace.write(json.dumps(row)+'\n')
            trace.flush()
        with RfcommBridge(args.host, args.port, trace=record) as transport:
            result = verify(transport, args.address, args.count)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
