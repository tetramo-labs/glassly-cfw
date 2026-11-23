#!/usr/bin/env python3
"""Sequential client for the optional native cooked-input observer.

No device is opened here. Polls retain records until an explicit acknowledge()
followed by the next poll. Call acknowledge only after saving the returned data.
Any ambiguous delivery/protocol error stops this client; no automatic retry.
"""
import json
import secrets
import struct

from memomind_scene import _DeadlineIO, tlv_bytes, uint
from memomind_transport import GmStream, request_gm

SERVICE = 15
COMMAND = 0x7c


class InputError(RuntimeError):
    pass


class InputProtocolError(InputError):
    pass


class InputNativeError(InputError):
    def __init__(self, reply):
        self.reply = reply
        super().__init__('Input observer rejected request: ' + repr(reply))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def decode_reply(message):
    tlvs = message['tlvs']
    if len(tlvs) != 1 or tlvs[0][0] != 5:
        raise InputProtocolError('Expected one JSON TLV')
    try:
        value = json.loads(tlvs[0][1].decode('utf-8').rstrip('\0'), object_pairs_hook=_object)
    except (UnicodeError, ValueError) as exc:
        raise InputProtocolError('Malformed input JSON') from exc
    if not isinstance(value, dict) or value.get('glassly') != 'input' or type(value.get('abi')) is not int or value['abi'] != 1:
        raise InputProtocolError('Unexpected input observer identity')
    if value.get('result') != 'ok':
        raise InputNativeError(value)
    try:
        for key in ('nonce', 'sequence', 'ack', 'drops'):
            uint(value.get(key), 32, key)
        uint(value.get('mask'), 2, 'mask')
    except ValueError as exc:
        raise InputProtocolError(str(exc)) from exc
    if (type(value.get('active')) is not bool or type(value.get('exhausted')) is not bool
            or type(value.get('capacity')) is not int or value['capacity'] != 32
            or type(value.get('leaseTicks')) is not int or value['leaseTicks'] != 30000
            or value['ack'] > value['sequence']
            or value['exhausted'] != (value['sequence'] == 0xffffffff)):
        raise InputProtocolError('Invalid input observer metadata')
    records = value.get('records')
    if not isinstance(records, list) or len(records) > 8:
        raise InputProtocolError('Invalid bounded input page')
    previous = value['ack']
    for record in records:
        if not isinstance(record, dict):
            raise InputProtocolError('Invalid input record')
        try:
            for key in ('tick', 'sequence'):
                uint(record.get(key), 32, key)
            uint(record.get('id'), 16, 'id')
            uint(record.get('class'), 8, 'class')
        except ValueError as exc:
            raise InputProtocolError(str(exc)) from exc
        kind, event = record['class'], record['id']
        allowed = ((kind == 2 and value['mask'] & 1 and
                    (0x1f7b <= event <= 0x1f7f or 0x1fb0 <= event <= 0x1fb9)) or
                   (kind == 3 and value['mask'] & 2 and 1 <= event <= 8))
        if not allowed or not previous < record['sequence'] <= value['sequence']:
            raise InputProtocolError('Invalid event or sequence order')
        previous = record['sequence']
    if value['active']:
        if not value['nonce'] or not value['mask']:
            raise InputProtocolError('Active observer lacks session identity')
    elif records or any(value[key] for key in ('nonce', 'mask', 'sequence', 'ack', 'drops')) or value['exhausted']:
        raise InputProtocolError('Inactive observer contains session state')
    return value


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
                    raise InputProtocolError('Uncorrelated or duplicate input reply')
                self.seen = True
        return messages


class InputClient:
    def __init__(self, transport, *, timeout=10):
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError('timeout must be positive and at most60 seconds')
        self.transport, self.timeout = transport, timeout
        self.parser = _Parser()
        self.event = 0x70
        self.failed = False
        self.nonce = self.mask = self.ack = self.delivered = 0
        self.sequence = self.drops = 0

    def _request(self, body, check):
        if self.failed:
            raise InputError('Client stopped after prior error; no automatic recovery')
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

    def _same_session(self, result):
        if not result['active'] or result['nonce'] != self.nonce or result['mask'] != self.mask:
            raise InputProtocolError('Input session changed')
        if result['sequence'] < self.sequence or result['drops'] < self.drops:
            raise InputProtocolError('Input counters moved backwards')

    def status(self):
        def check(result):
            if result['records']:
                raise InputProtocolError('Status unexpectedly returned records')
            if self.nonce:
                self._same_session(result)
        return self._request(b'\x01\x00', check)

    def subscribe(self, mask=3, *, nonce=None):
        if self.nonce:
            raise InputError('This client already owns a subscription')
        uint(mask, 2, 'mask')
        if not mask:
            raise ValueError('mask must select buttons and/or IMU')
        if nonce is None:
            nonce = secrets.randbelow(0xffffffff) + 1
        uint(nonce, 32, 'nonce')
        if not nonce:
            raise ValueError('nonce must be nonzero')

        def check(result):
            if not result['active'] or result['nonce'] != nonce or result['mask'] != mask or result['records']:
                raise InputProtocolError('Subscribe identity mismatch')
            # A nonce collision must never silently attach to an existing log.
            if result['sequence'] or result['ack'] or result['drops']:
                raise InputProtocolError('Subscribe returned an existing nonempty session')
        result = self._request(struct.pack('<BBBI', 1, 1, mask, nonce), check)
        self.nonce, self.mask = nonce, mask
        self.ack = self.delivered = self.sequence = self.drops = 0
        return result

    def poll(self):
        if not self.nonce:
            raise InputError('Subscribe before polling')

        def check(result):
            self._same_session(result)
            if result['ack'] != self.ack:
                raise InputProtocolError('Poll acknowledgment mismatch')
        result = self._request(struct.pack('<BBII', 1, 2, self.nonce, self.ack), check)
        self.sequence, self.drops = result['sequence'], result['drops']
        if result['records']:
            self.delivered = max(self.delivered, result['records'][-1]['sequence'])
        return result

    def acknowledge(self, sequence):
        """Advance local ACK only; the next poll submits it to the device."""
        if self.failed or not self.nonce:
            raise InputError('No usable subscription')
        uint(sequence, 32, 'sequence')
        if not self.ack <= sequence <= self.delivered:
            raise ValueError('ACK must be monotonic and no later than delivered data')
        self.ack = sequence

    def stop(self):
        if not self.nonce:
            raise InputError('No subscription to stop')

        def check(result):
            if result['active']:
                raise InputProtocolError('Stop left observer active')
        result = self._request(struct.pack('<BBI', 1, 3, self.nonce), check)
        self.nonce = self.mask = 0
        return result
