from collections import deque
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from capture_memomind_flash import acquire
from memomind_flash_read import (FlashReadClient, FlashReadError, FlashReadNativeError, EXTERNAL_PROFILE, PROFILES,
                                FlashReadProtocolError, PROFILE, REGIONS, decode_reply)
from memomind_transport import gm_frames, parse_tlvs


def identity():
    return dict(glassly='flash-read', abi=1, result='ok', profile=PROFILE,
                maxRead=256, alignment=256,
                ranges=[dict(device=d, start=s, end=e) for d, s, e in REGIONS.values()])


class WireFake:
    """Actual GM framing around an independent fixed-op read-only responder."""
    timeout = 20

    def __init__(self):
        self.messages = []
        self.reads = deque()
        self.edit = None
        self.event_delta = 0
        self.duplicate = self.drop = False

    def write(self, frame):
        # Fragment acknowledgments emitted by request_gm carry no body.
        if len(frame) == 9:
            return
        assert frame[0] == 250 and int.from_bytes(frame[1:4], 'big') == len(frame)
        assert sum(frame[:-2]) & 65535 == int.from_bytes(frame[-2:], 'big')
        event, service, command = frame[4:7]
        assert (service, command) == (15, 0x7b)
        tlvs = parse_tlvs(frame[7:-2])
        assert len(tlvs) == 1 and tlvs[0][0] == 1
        body = tlvs[0][1]
        self.messages.append(body)
        if body == b'\0':
            reply = identity()
        else:
            op, device, offset, length = struct.unpack('<BBIH', body)
            assert op == 1
            raw = bytes((device * 17 + offset + n) & 255 for n in range(length))
            reply = dict(glassly='flash-read', abi=1, result='ok', device=device,
                         offset=offset, length=length, hex=raw.hex())
        if self.edit:
            reply = self.edit(reply)
        raw = json.dumps(reply, separators=(',', ':')).encode()
        wire = b''.join(gm_frames((event + self.event_delta) & 255, 15, 0x7b,
                                 b'\x05' + len(raw).to_bytes(3, 'big') + raw))
        if not self.drop:
            self.reads.append(wire + wire if self.duplicate else wire)

    def read(self, timeout):
        if not self.reads:
            raise TimeoutError('No reply')
        return self.reads.popleft()


class FlashClientTests(unittest.TestCase):
    def test_external_region_is_explicit_and_profile_pinned(self):
        wire, client = self.client()
        client.query()
        with self.assertRaises(ValueError):
            client.read(1, 0x700000)
        self.assertEqual(wire.messages, [b'\0'])
        def external(reply):
            if 'ranges' in reply:
                reply['profile'] = EXTERNAL_PROFILE
                reply['ranges'] = [dict(device=d, start=s, end=e) for d,s,e in PROFILES[EXTERNAL_PROFILE].values()]
            return reply
        wire = WireFake(); wire.edit = external
        client = FlashReadClient(wire, profile=EXTERNAL_PROFILE)
        client.query()
        for offset in (0x700000, 0x7fff00):
            self.assertEqual(len(client.read(1, offset)), 256)
        for args in ((0,0x700000,256),(1,0x6fff00,256),(1,0x800000,1),(1,0x7fff00,257)):
            with self.assertRaises(ValueError): client.read(*args)
        detached = client.regions; detached.clear()
        self.assertIn('external-tail', client.regions)
        wire = WireFake(); wire.edit = external
        with self.assertRaises(FlashReadProtocolError): FlashReadClient(wire).query()
        with self.assertRaises(FlashReadProtocolError): FlashReadClient(WireFake(),profile=EXTERNAL_PROFILE).query()

    def test_external_capture_cannot_use_old_profile(self):
        wire, client = self.client()
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            acquire(client, ['external-tail'], Path(tmp), lambda _: None, expected_app_prefix=bytes(32))
        self.assertFalse(wire.messages)

    def client(self):
        wire = WireFake()
        return wire, FlashReadClient(wire)

    def test_constructor_and_query_do_not_read(self):
        wire, client = self.client()
        self.assertFalse(wire.messages)
        self.assertEqual(client.query(), identity())
        self.assertEqual(wire.messages, [b'\0'])

    def test_read_requires_verified_profile(self):
        wire, client = self.client()
        with self.assertRaises(FlashReadError):
            client.read(0, 0)
        self.assertFalse(wire.messages)

    def test_all_range_edges_and_short_reads(self):
        wire, client = self.client()
        client.query()
        for device, start, end in REGIONS.values():
            for offset in (start, end - 256):
                for length in (1, 2, 255, 256):
                    self.assertEqual(client.read(device, offset, length),
                                     bytes((device * 17 + offset + n) & 255 for n in range(length)))
                    self.assertEqual(wire.messages[-1], struct.pack('<BBIH', 1, device, offset, length))

    def test_invalid_addresses_and_types_send_nothing(self):
        wire, client = self.client()
        client.query()
        invalid = [(0, 0, 0), (0, 0, 257), (0, 0, True), (True, 0, 1), (0, False, 1),
                   (0, 0x10000, 1), (0, 0xffffff00, 256), (0, 1 << 32, 1),
                   (0, -256, 1), (1, 0, 256), (0, 0x500000, 256), (2, 0, 1)]
        invalid += [(d, s + n, 1) for d, s, _ in REGIONS.values() for n in range(1, 256)]
        invalid += [(d, e, 1) for d, _, e in REGIONS.values()]
        for args in invalid:
            with self.assertRaises(ValueError, msg=str(args)):
                client.read(*args)
        self.assertEqual(wire.messages, [b'\0'])

    def test_unknown_or_expanded_profile_is_rejected(self):
        changed = [dict(profile='other'), dict(maxRead=512), dict(alignment=True),
                   dict(ranges=[]), dict(ranges=identity()['ranges'] * 2)]
        ranges = identity()['ranges']
        ranges[0]['end'] += 256
        changed.append(dict(ranges=ranges))
        ranges = identity()['ranges']
        ranges[0]['device'] = False
        changed.append(dict(ranges=ranges))
        for changes in changed:
            wire, client = self.client()
            wire.edit = lambda r: {**r, **changes}
            with self.assertRaises(FlashReadProtocolError):
                client.query()
            self.assertFalse(client.verified)
            self.assertTrue(client.failed)

    def test_mismatched_echo_invalid_hex_and_lengths_poison(self):
        for changes in (dict(device=1), dict(offset=256), dict(length=True), dict(length=1),
                        dict(hex='AA' * 256), dict(hex='00 ' * 256), dict(hex=''), dict(hex=None)):
            wire, client = self.client()
            client.query()
            wire.edit = lambda r: {**r, **changes}
            with self.assertRaises(FlashReadProtocolError):
                client.read(0, 0)
            with self.assertRaises(FlashReadError):
                client.query()
            self.assertEqual(len(wire.messages), 2)

    def test_native_failure_suppresses_bytes_and_has_no_retry(self):
        for result in ('invalid', 'allocation-failed', 'read-failed'):
            wire, client = self.client()
            client.query()
            wire.edit = lambda _: dict(glassly='flash-read', abi=1, result=result)
            with self.assertRaises(FlashReadNativeError):
                client.read(0, 0)
            with self.assertRaises(FlashReadError):
                client.read(0, 0)
            self.assertEqual(len(wire.messages), 2)

    def test_timeout_wrong_correlation_and_duplicates_stop(self):
        for flag, error in (('drop', TimeoutError), ('event_delta', FlashReadProtocolError),
                            ('duplicate', FlashReadProtocolError)):
            wire, client = self.client()
            setattr(wire, flag, True)
            with self.assertRaises(error):
                client.query()
            with self.assertRaises(FlashReadError):
                client.query()
            self.assertEqual(wire.messages, [b'\0'])

    def test_strict_json_and_tlv_boundaries(self):
        for raw in (b'{}', b'[]', b'\xff', b'{"abi":1,"abi":1}', b'null',
                    b'{"glassly":"flash-read","abi":true,"result":"ok"}',
                    b'{"glassly":"flash-read","abi":1,"result":NaN}', b' ' * 769,
                    json.dumps(identity()).encode() + b'\0\0'):
            with self.assertRaises(FlashReadProtocolError):
                decode_reply({'tlvs': [(5, raw)]})
        for tlvs in ([], [(6, b'\0')], [(5, b'{}'), (5, b'{}')]):
            with self.assertRaises(FlashReadProtocolError):
                decode_reply({'tlvs': tlvs})


class AcquisitionTests(unittest.TestCase):
    def test_query_only_has_no_binary(self):
        wire = WireFake()
        with tempfile.TemporaryDirectory() as tmp:
            rows = []
            result = acquire(FlashReadClient(wire), [], Path(tmp), rows.append)
            self.assertTrue(result['complete'])
            self.assertEqual(result['artifacts'], [])
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertEqual(wire.messages, [b'\0'])

    def test_complete_capture_hash_order_and_disk_before_journal(self):
        wire = WireFake()
        rows = []
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            def save(row):
                if row['kind'] == 'chunk':
                    data = (output / (row['region'] + '.bin')).read_bytes()
                    self.assertEqual(len(data), row['file_offset'] + row['length'])
                    self.assertEqual(hashlib.sha256(data[-row['length']:]).hexdigest(), row['sha256'])
                rows.append(copy.deepcopy(row))
            result = acquire(FlashReadClient(wire), ['boot-maps', 'app-header'], output, save,
                             expected_app_prefix=bytes(range(32)))
            self.assertTrue(result['app_header_verified'])
            self.assertEqual(len(wire.messages), 34)  # Query, header, 32 map pages.
            self.assertEqual([a['path'] for a in result['artifacts']], ['app-header.bin', 'boot-maps.bin'])
            for artifact in result['artifacts']:
                path = output / artifact['path']
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact['sha256'])
            self.assertEqual(rows[1]['kind'], 'read-intent')

    def test_header_mismatch_stops_before_other_region(self):
        wire = WireFake()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'App-header mismatch'):
                acquire(FlashReadClient(wire), ['boot-prefix'], Path(tmp), lambda _: None,
                        expected_app_prefix=b'x' * 32)
            self.assertEqual(len(wire.messages), 2)
            self.assertFalse((Path(tmp) / 'boot-prefix.bin').exists())

    def test_missing_expected_header_or_existing_output_sends_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            for names in (['boot-prefix'], ['plugin-directory'], ['app-header', 'app-header'], ['../x']):
                wire = WireFake()
                with self.assertRaises(ValueError):
                    acquire(FlashReadClient(wire), names, output, lambda _: None)
                self.assertFalse(wire.messages)
            (output / 'app-header.bin').write_bytes(b'keep')
            wire = WireFake()
            with self.assertRaises(FileExistsError):
                acquire(FlashReadClient(wire), ['app-header'], output, lambda _: None)
            self.assertFalse(wire.messages)
            self.assertEqual((output / 'app-header.bin').read_bytes(), b'keep')

    def test_failed_journal_stops_without_next_read(self):
        wire = WireFake()
        with tempfile.TemporaryDirectory() as tmp:
            def save(row):
                if row['kind'] == 'chunk':
                    raise OSError('Disk full')
            with self.assertRaisesRegex(OSError, 'Disk full'):
                acquire(FlashReadClient(wire), ['boot-maps'], Path(tmp), save,
                        expected_app_prefix=bytes(range(32)))
            self.assertEqual(len(wire.messages), 2)
            self.assertFalse((Path(tmp) / 'boot-maps.bin').exists())
