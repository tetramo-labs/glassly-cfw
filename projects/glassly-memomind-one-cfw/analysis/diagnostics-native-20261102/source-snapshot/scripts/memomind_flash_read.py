#!/usr/bin/env python3
"""Bounded read-only flash acquisition client for the optional H001Y adapter.

No connection, write, erase, retry, or address-space discovery is implicit.
The exact compiled allowlist must match before the first read is admitted.
Host deadlines do not interrupt the stock driver's unbounded busy wait.
"""
import json
import re
import struct

from memomind_scene import _DeadlineIO, tlv_bytes, uint
from memomind_transport import GmStream, request_gm

SERVICE, COMMAND = 15, 0x7b
PROFILE = 'H001Y-1.0.3.127'
REGIONS = {
    'boot-prefix': (0, 0, 0x10000),
    'app-header': (0, 0x1eb000, 0x1eb100),
    'boot-maps': (0, 0x7fc000, 0x7fe000),
    'plugin-directory': (1, 0x500000, 0x510000),
}
EXTERNAL_PROFILE = 'H001Y-1.0.3.127-external-v1'
PROFILES = {PROFILE: REGIONS, EXTERNAL_PROFILE: {**REGIONS, 'external-tail': (1, 0x700000, 0x800000)}}
DIAGNOSTIC_PROFILE = 'H001Y-1.0.3.127-storage-diag-v1'
PROFILES[DIAGNOSTIC_PROFILE] = dict(PROFILES[EXTERNAL_PROFILE])
FULL_STORE_PROFILE = 'H001Y-1.0.3.127-full-store-read-v1'
# Single, nonoverlapping store range; old directory/tail profiles stay exact.
PROFILES[FULL_STORE_PROFILE] = {
    **{name: region for name, region in REGIONS.items() if region[0] == 0},
    'managed-store': (1, 0x500000, 0x800000),
}


CANARY_PROFILE = 'H001Y-1.0.3.127-flash-canary-v1'
PROFILES[CANARY_PROFILE] = dict(PROFILES[FULL_STORE_PROFILE])


class FlashReadError(RuntimeError):
    pass


class FlashReadProtocolError(FlashReadError):
    pass


class FlashReadNativeError(FlashReadError):
    def __init__(self, reply):
        self.reply = reply
        super().__init__('Flash read rejected: ' + repr(reply))


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


def decode_reply(message):
    tlvs = message['tlvs']
    if len(tlvs) != 1 or tlvs[0][0] != 5 or len(tlvs[0][1]) > 768:
        raise FlashReadProtocolError('Expected one bounded JSON TLV')
    try:
        raw = tlvs[0][1]
        if raw.endswith(b'\0'):
            raw = raw[:-1]
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (UnicodeError, ValueError) as exc:
        raise FlashReadProtocolError('Malformed flash JSON') from exc
    if (not isinstance(result, dict) or result.get('glassly') != 'flash-read'
            or type(result.get('abi')) is not int or result['abi'] != 1):
        raise FlashReadProtocolError('Unexpected flash adapter identity')
    if result.get('result') != 'ok':
        if result.get('result') in ('invalid', 'allocation-failed', 'read-failed'):
            raise FlashReadNativeError(result)
        raise FlashReadProtocolError('Unknown flash result')
    return result


def validate_read(device, offset, length, *, profile=PROFILE):
    if profile not in PROFILES:
        raise ValueError('Unknown pinned acquisition profile')
    uint(device, 8, 'device')
    uint(offset, 32, 'offset')
    uint(length, 16, 'length')
    if offset % 256 or not 1 <= length <= 256:
        raise ValueError('Read requires a 256-byte aligned offset and length 1..256')
    if not any(device == dev and start <= offset and offset + length <= end
               for dev, start, end in PROFILES[profile].values()):
        raise ValueError('Read is outside the fixed acquisition ranges')


class _Parser:
    fragment_acks = True

    def __init__(self):
        self.stream = GmStream(legacy_repeat_fa=True, fragment_acks=True)
        self.pending = None
        self.seen = False

    def begin(self, key):
        self.pending, self.seen = key, False

    def feed(self, data):
        messages = self.stream.feed(data)
        for message in messages:
            key = message['event'], message['service'], message['command']
            if key[1:] == (SERVICE, COMMAND) and message['tlvs']:
                if key != self.pending or self.seen:
                    raise FlashReadProtocolError('Uncorrelated or duplicate flash reply')
                self.seen = True
        return messages


class FlashReadClient:
    def __init__(self, transport, *, timeout=10, profile=PROFILE):
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError('timeout must be positive and at most 60 seconds')
        self.transport, self.timeout = transport, timeout
        if profile not in PROFILES:
            raise ValueError('Unknown pinned acquisition profile')
        self.profile = profile
        self.parser = _Parser()
        self.event = 0x90
        self.failed = False
        self.verified = False

    @property
    def regions(self):
        return dict(PROFILES[self.profile])

    def _request(self, body, check):
        if self.failed:
            raise FlashReadError('Client stopped after prior error; no automatic recovery')
        self.event = self.event % 255 + 1
        key = self.event, SERVICE, COMMAND
        self.parser.begin(key)
        try:
            message = request_gm(_DeadlineIO(self.transport, self.timeout), self.parser,
                                 *key, tlv_bytes(body), timeout=self.timeout)
            result = decode_reply(message)
            check(result)
            return result
        except Exception:
            self.failed = True
            raise

    def query(self):
        def check(result):
            if (result.get('profile') != self.profile or type(result.get('maxRead')) is not int
                    or result['maxRead'] != 256 or type(result.get('alignment')) is not int
                    or result['alignment'] != 256):
                raise FlashReadProtocolError('Unknown flash profile or read limits')
            ranges = result.get('ranges')
            if not isinstance(ranges, list) or len(ranges) != len(self.regions):
                raise FlashReadProtocolError('Unexpected flash allowlist')
            actual = []
            for item in ranges:
                if not isinstance(item, dict) or set(item) != {'device', 'start', 'end'}:
                    raise FlashReadProtocolError('Malformed flash range')
                if any(type(item[k]) is not int for k in ('device', 'start', 'end')):
                    raise FlashReadProtocolError('Noninteger flash range')
                actual.append((item['device'], item['start'], item['end']))
            if sorted(actual) != sorted(self.regions.values()):
                raise FlashReadProtocolError('Compiled flash allowlist differs from pinned profile')
        result = self._request(b'\0', check)
        self.verified = True
        return result

    def read(self, device, offset, length=256):
        validate_read(device, offset, length, profile=self.profile)
        if not self.verified:
            raise FlashReadError('Query and verify the flash profile before reading')

        def check(result):
            for key, wanted in (('device', device), ('offset', offset), ('length', length)):
                if type(result.get(key)) is not int or result[key] != wanted:
                    raise FlashReadProtocolError('Read echo mismatch: ' + key)
            text = result.get('hex')
            if not isinstance(text, str) or re.fullmatch('[0-9a-f]{' + str(length * 2) + '}', text) is None:
                raise FlashReadProtocolError('Invalid flash hex or byte count')
        result = self._request(struct.pack('<BBIH', 1, device, offset, length), check)
        return bytes.fromhex(result['hex'])
