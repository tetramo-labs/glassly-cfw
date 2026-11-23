"""Independently decode native GM record traffic; no device operations."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from memomind_transport import GmStream


def verify(trace):
    streams = [GmStream(legacy_repeat_fa=True, fragment_acks=True) for _ in range(2)]
    decoder = None
    partial = bytearray()
    expected_sequence = None
    pending = {}
    records = []
    for row in map(json.loads, trace.splitlines()):
        event = row['event']
        if event not in ('transmitSubmission', 'receive'):
            continue
        incoming = int(event == 'receive')
        for message in streams[incoming].feed(bytes.fromhex(row['hex'])):
            if (message['service'], message['command']) != (15, 125) or not message['tlvs']:
                continue
            key = message['event']
            if not incoming:
                assert len(message['tlvs']) == 1 and message['tlvs'][0][0] == 1
                packet = message['tlvs'][0][1]
                if packet[0] != 126:
                    continue
                assert len(packet) <= 132 and packet[1] == 1 and packet[3] & 3 == 1
                if packet[3] & 128:
                    assert not partial
                    expected_sequence = packet[2]
                    stream_id = packet[2]
                assert packet[2] == expected_sequence
                expected_sequence = (expected_sequence + 1) & 255
                partial.extend(packet[4:])
                completed = None
                if packet[3] & 64:
                    flags, wire_length, crc = struct.unpack_from('<BHH', partial)
                    assert flags in (5, 13) and len(partial) == wire_length + 5
                    wire = bytes(partial[5:]); assert wire.endswith(b'\x00\x00\xff\xff')
                    if flags & 8:
                        decoder = zlib.decompressobj()
                    assert decoder is not None
                    body = decoder.decompress(wire, 65536)
                    assert not decoder.eof and not decoder.unconsumed_tail and len(body) <= 65535
                    assert binascii.crc_hqx(body, 65535) == crc
                    completed = dict(mode=body[0], decodedBytes=len(body), wireBytes=wire_length,
                        crc16=crc, streamID=stream_id, resetContext=bool(flags & 8),
                        decodedSHA256=hashlib.sha256(body).hexdigest())
                    partial.clear()
                assert key not in pending
                pending[key] = completed
            elif key in pending:
                assert len(message['tlvs']) == 1 and message['tlvs'][0][0] == 5
                reply = json.loads(message['tlvs'][0][1].rstrip(b'\0'))
                if reply.get('result') == 'settled':
                    continue
                assert reply['glassly'] == 'record-transport' and reply['abi'] == 1 and reply['status'] == 0
                record = pending.pop(key)
                frames = [bytes.fromhex(f) for f in reply['frames']]
                if record is None:
                    assert not frames and reply['closing'] == 0
                    continue
                assert frames and len(frames) <= 2
                ack = frames[-1]
                assert 9 <= len(ack) <= 30 and (len(ack) - 9) % 7 == 0
                assert ack[:5] == bytes([1, record['streamID'], 0, 0, 1])
                assert struct.unpack_from('<HH', ack, 5) == (record['decodedBytes'], record['crc16'])
                if len(frames) == 2:
                    assert frames[0][:5] == bytes([5, record['streamID'], 0, 0, 1])
                    record['binaryReplyBytes'] = len(frames[0]) - 5
                record['closing'] = reply['closing']; records.append(record)
    assert not pending and not partial
    assert any(r['decodedBytes'] == 65535 for r in records)
    assert any(r['mode'] == 11 and r['closing'] == 1 for r in records)
    repeated = [r for r in records if r['decodedBytes'] == 4096]
    assert len(repeated) == 2 and repeated[0]['decodedSHA256'] == repeated[1]['decodedSHA256']
    assert repeated[1]['wireBytes'] < 100 and repeated[1]['wireBytes'] < repeated[0]['wireBytes']
    assert any(r.get('binaryReplyBytes') == 20 for r in records)
    return dict(passed=True, records=records, traceSHA256=hashlib.sha256(trace).hexdigest(),
                limitation='Application callback traffic, not independent radio capture or visual confirmation')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); assert not a.output.exists()
    report = verify(a.trace.read_bytes())
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Verified', len(report['records']), 'compressed records')


if __name__ == '__main__':
    main()
