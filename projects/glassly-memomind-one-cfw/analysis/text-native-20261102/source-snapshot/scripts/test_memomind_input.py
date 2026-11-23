import copy
from collections import deque
import json
import struct
import unittest
from unittest.mock import patch

from memomind_input import InputClient, InputError, InputNativeError, InputProtocolError, decode_reply
from memomind_transport import gm_frames, parse_tlvs
from probe_memomind_input import capture


def state(active=False, nonce=0, mask=0, sequence=0, ack=0, drops=0, records=None):
    return dict(glassly='input', abi=1, result='ok', active=active, nonce=nonce,
                mask=mask, capacity=32, leaseTicks=30000, sequence=sequence,
                ack=ack, drops=drops, exhausted=sequence == 0xffffffff,
                records=records or [])


class NativeFake:
    """Independent fixed-command model and actual GM wire framing."""
    timeout = 20

    def __init__(self):
        self.state = state()
        self.records = []
        self.reads = deque()
        self.messages = []
        self.edit = None
        self.event_delta = 0
        self.duplicate = self.drop = False

    def emit(self, event=0x1f7b, kind=2, tick=100):
        self.state['sequence'] += 1
        self.records.append(dict(tick=tick, sequence=self.state['sequence'], id=event, **{'class': kind}))
        if len(self.records) > 32:
            self.records.pop(0)
            self.state['drops'] += 1

    def write(self, frame):
        assert frame[0] == 250 and int.from_bytes(frame[1:4], 'big') == len(frame)
        assert sum(frame[:-2]) & 65535 == int.from_bytes(frame[-2:], 'big')
        event, service, command = frame[4:7]
        assert (service, command) == (15, 0x7c)
        tlvs = parse_tlvs(frame[7:-2])
        assert len(tlvs) == 1 and tlvs[0][0] == 1
        data = tlvs[0][1]
        self.messages.append(data)
        assert data[0] == 1
        op = data[1]
        if op == 1:
            _, _, mask, nonce = struct.unpack('<BBBI', data)
            self.state = state(True, nonce, mask)
        elif op in (2, 3):
            nonce = int.from_bytes(data[2:6], 'little')
            assert nonce == self.state['nonce']
            if op == 2:
                ack = int.from_bytes(data[6:10], 'little')
                assert self.state['ack'] <= ack <= self.state['sequence']
                self.state['ack'] = ack
                self.records = [r for r in self.records if r['sequence'] > ack]
            else:
                self.state = state()
                self.records = []
        result = copy.deepcopy(self.state)
        result['records'] = copy.deepcopy(self.records[:8]) if op == 2 else []
        if self.edit:
            result = self.edit(result)
        encoded = json.dumps(result, separators=(',', ':')).encode()
        frames = b''.join(gm_frames((event + self.event_delta) & 255, 15, 0x7c,
                                   b'\x05' + len(encoded).to_bytes(3, 'big') + encoded))
        if not self.drop:
            self.reads.append(frames + frames if self.duplicate else frames)

    def read(self, timeout):
        if not self.reads:
            raise TimeoutError('No reply')
        return self.reads.popleft()


class InputTests(unittest.TestCase):
    def client(self):
        io = NativeFake()
        return io, InputClient(io)

    def test_passive_status_does_not_subscribe(self):
        io, client = self.client()
        self.assertFalse(client.status()['active'])
        self.assertEqual(io.messages, [b'\1\0'])

    def test_subscribe_poll_retains_until_explicit_ack(self):
        io, client = self.client()
        client.subscribe(nonce=0x12345678)
        io.emit()
        first = client.poll()
        self.assertEqual(first, client.poll())
        client.acknowledge(1)
        self.assertEqual(client.poll()['records'], [])
        self.assertEqual(io.messages[-1], struct.pack('<BBII', 1, 2, 0x12345678, 1))
        self.assertFalse(client.stop()['active'])

    def test_fragmented_reply_and_bounded_pages(self):
        io, client = self.client()
        client.subscribe(nonce=1)
        for _ in range(32):
            io.emit()
        found = []
        for _ in range(4):
            page = client.poll()['records']
            self.assertEqual(len(page), 8)
            found += [r['sequence'] for r in page]
            client.acknowledge(found[-1])
        self.assertEqual(found, list(range(1, 33)))

    def test_overflow_remains_explicit(self):
        io, client = self.client()
        client.subscribe(nonce=1)
        for _ in range(40):
            io.emit()
        result = client.poll()
        self.assertEqual(result['drops'], 8)
        self.assertEqual(result['records'][0]['sequence'], 9)

    def test_ack_cannot_skip_undelivered_or_go_backwards(self):
        io, client = self.client()
        client.subscribe(nonce=1)
        io.emit()
        with self.assertRaises(ValueError):
            client.acknowledge(1)
        client.poll()
        client.acknowledge(1)
        for value in (0, 2, True, -1):
            with self.assertRaises(ValueError):
                client.acknowledge(value)

    def test_native_rejection_poisoned_no_retry(self):
        io, client = self.client()
        io.edit = lambda r: dict(glassly='input', abi=1, result='allocation-failed')
        with self.assertRaises(InputNativeError):
            client.subscribe(nonce=1)
        with self.assertRaises(InputError):
            client.status()
        self.assertEqual(len(io.messages), 1)

    def test_timeout_does_not_retry_or_auto_stop(self):
        io, client = self.client()
        io.drop = True
        with self.assertRaises(TimeoutError):
            client.subscribe(nonce=1)
        with self.assertRaises(InputError):
            client.subscribe(nonce=2)
        self.assertEqual(len(io.messages), 1)

    def test_wrong_event_and_duplicate_replies_fail(self):
        for field in ('event_delta', 'duplicate'):
            io, client = self.client()
            setattr(io, field, 1)
            with self.assertRaises(InputProtocolError):
                client.status()
            self.assertTrue(client.failed)

    def test_session_and_counter_checks(self):
        for edit in (lambda r: {**r, 'nonce': 2}, lambda r: {**r, 'ack': 1},
                     lambda r: {**r, 'mask': 1}):
            io, client = self.client()
            client.subscribe(nonce=1)
            io.emit()
            io.edit = edit
            with self.assertRaises(InputProtocolError):
                client.poll()

    def test_invalid_parameters_never_send(self):
        io, client = self.client()
        for nonce in (0, -1, True, 1 << 32):
            with self.assertRaises(ValueError):
                client.subscribe(nonce=nonce)
        for mask in (0, 4, True):
            with self.assertRaises(ValueError):
                client.subscribe(mask, nonce=1)
        for method in (client.poll, client.stop):
            with self.assertRaises(InputError):
                method()
        self.assertEqual(io.messages, [])

    def test_strict_reply_schema(self):
        original = state(True, 1, 3, 1, records=[dict(tick=5, sequence=1, id=1, **{'class': 3})])
        variants = [{**original, key: value} for key, value in (
            ('abi', True), ('capacity', 31), ('leaseTicks', 1), ('sequence', True),
            ('active', 1), ('exhausted', True), ('records', [1]), ('nonce', 0))]
        for change in ({'class': 0x11}, {'id': 9}, {'sequence': 0}, {'tick': -1}):
            variants.append({**original, 'records': [{**original['records'][0], **change}]})
        for value in variants:
            with self.assertRaises(InputProtocolError):
                decode_reply({'tlvs': [(5, json.dumps(value).encode())]})
        with self.assertRaises(InputProtocolError):
            decode_reply({'tlvs': [(5, b'{"glassly":"input","glassly":"input"}')]})

    def test_durable_save_before_ack(self):
        io, client = self.client()
        saved = []
        def save(row):
            saved.append(row)
            if row['kind'] == 'subscribe':
                io.emit()
            elif row['kind'] == 'poll':
                self.assertEqual(client.ack, 0)
        with patch('probe_memomind_input.time') as clock:
            clock.monotonic.side_effect = [0, 2]
            result = capture(client, 1, .1, save)
        self.assertEqual(result['recorded_events'], 1)
        self.assertEqual([r['kind'] for r in saved], ['subscribe', 'poll', 'stop'])

    def test_save_failure_leaves_record_unacknowledged(self):
        io, client = self.client()
        def save(row):
            if row['kind'] == 'subscribe':
                io.emit()
            else:
                raise OSError('Disk write failed')
        with self.assertRaises(OSError):
            capture(client, 1, .1, save)
        self.assertEqual(client.ack, 0)
        self.assertEqual(io.state['ack'], 0)
        self.assertEqual(len(io.messages), 2)


if __name__ == '__main__':
    unittest.main()
