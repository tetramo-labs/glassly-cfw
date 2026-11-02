#!/usr/bin/env python3
"""Replay emitted production C and RV32 replies through the actual Python client."""
import argparse
from collections import deque
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from memomind_flash_read import FlashReadClient, FlashReadNativeError, FlashReadProtocolError
from memomind_transport import gm_frames, parse_tlvs


class Replay:
    timeout = 10

    def __init__(self, exchanges):
        self.exchanges = deque(exchanges)
        self.incoming = deque()

    def write(self, frame):
        if len(frame) == 9:  # GM fragment acknowledgment, not an extra request.
            return
        body, reply = self.exchanges.popleft()
        assert tuple(frame[5:7]) == (15, 0x7b)
        assert parse_tlvs(frame[7:-2]) == [(1, body)]
        if set(reply) == {'status'}:
            payload = b'\x06\0\0\x01' + bytes([reply['status']])
        else:
            raw = json.dumps(reply, separators=(',', ':')).encode()
            payload = b'\x05' + len(raw).to_bytes(3, 'big') + raw
        encoded = b''.join(gm_frames(frame[4], 15, 0x7b, payload))
        # Exercise stream reassembly independently of GM fragment boundaries.
        self.incoming.extend(encoded[n:n + 13] for n in range(0, len(encoded), 13))

    def read(self, timeout):
        if not self.incoming:
            raise TimeoutError('No replay reply remains')
        return self.incoming.popleft()


def check(path):
    replies = json.loads(path.read_text())['replies']
    query = next(row for row in replies if row.get('result') == 'ok' and 'ranges' in row)
    counts = {'query': 0, 'read': 0, 'native_error': 0, 'status_error': 0}
    for reply in replies:
        if reply.get('result') == 'ok' and 'hex' in reply:
            body = struct.pack('<BBIH', 1, reply['device'], reply['offset'], reply['length'])
            io = Replay([(b'\0', query), (body, reply)])
            client = FlashReadClient(io, profile=query['profile'])
            client.query()
            assert client.read(reply['device'], reply['offset'], reply['length']) == bytes.fromhex(reply['hex'])
            counts['read'] += 1
        elif reply.get('result') == 'ok':
            io = Replay([(b'\0', reply)])
            assert FlashReadClient(io, profile=query['profile']).query() == reply
            counts['query'] += 1
        else:
            io = Replay([(b'\0', reply)])
            client = FlashReadClient(io, profile=query['profile'])
            expected = FlashReadProtocolError if set(reply) == {'status'} else FlashReadNativeError
            try:
                client.query()
            except expected:
                assert client.failed
            else:
                raise AssertionError('Native error incorrectly accepted')
            counts['status_error' if set(reply) == {'status'} else 'native_error'] += 1
        assert not io.exchanges and not io.incoming
    assert counts['query'] and counts['read'] and counts['native_error']
    return {'source': str(path), 'reply_count': len(replies), 'counts': counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-report', type=Path, required=True)
    parser.add_argument('--rv32-report', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    results = [check(args.host_report), check(args.rv32_report)]
    report = {'passed': True, 'sources': results, 'hardware_tested': False,
              'scope': 'Production C/RV32 emitted replies replayed through GM stream and Python client; native flash mocked'}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
