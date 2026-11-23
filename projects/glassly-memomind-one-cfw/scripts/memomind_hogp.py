#!/usr/bin/env python3
"""Explicit native GM HOGP controller; never opens a device or retries commands.

Native control ACK means queue admission, not completed pairing/discovery.
Asynchronous events are retained separately with bounded memory. No operation,
including scan, forwarding, disconnect or unbond, is sent implicitly.
"""
from collections import deque
import json
import re
import time

from memomind_scene import _DeadlineIO, uint
from memomind_transport import GmStream, request_gm

SERVICE = 0x10
ASYNC_COMMANDS = frozenset((2, 4, 5, 6, 7, 8, 9, 10, 12))


class HogpError(RuntimeError):
    pass


class HogpProtocolError(HogpError):
    pass


class HogpNativeError(HogpError):
    def __init__(self, status, token=None):
        self.status, self.token = status, token
        super().__init__(f'Native HOGP rejection: status={status}, token={token!r}')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def json_tlv(value):
    data = json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    if not 1 <= len(data) <= 255:
        raise ValueError('Native HOGP metadata must fit1..255 UTF-8 bytes')
    return b'\x05' + len(data).to_bytes(3, 'big') + data


def decode(message, *, asynchronous=False):
    """Return typed JSON/data or an ordinary status ACK; reject ambiguous TLVs."""
    tlvs = message['tlvs']
    if tlvs and tlvs[0][0] == 6:
        if asynchronous or len(tlvs[0][1]) != 1 or len(tlvs) > 2:
            raise HogpProtocolError('Invalid status response')
        status = tlvs[0][1][0]
        token = None
        if len(tlvs) == 2:
            if tlvs[1][0] != 2:
                raise HogpProtocolError('Unexpected error token type')
            try:
                token = tlvs[1][1].decode('utf-8').rstrip('\0')
            except UnicodeError as exc:
                raise HogpProtocolError('Invalid error text') from exc
        if status:
            raise HogpNativeError(status, token)
        if token is not None:
            raise HogpProtocolError('Success ACK carried an error token')
        return {'kind': 'ack', 'status': 0}
    if not tlvs or tlvs[0][0] != 5 or len(tlvs) > 2 or (len(tlvs) == 2 and tlvs[1][0] != 1):
        raise HogpProtocolError('Expected JSON optionally followed by BYTES')
    try:
        value = json.loads(tlvs[0][1].decode('utf-8').rstrip('\0'), object_pairs_hook=_object)
    except (UnicodeError, ValueError) as exc:
        raise HogpProtocolError('Malformed HOGP JSON') from exc
    if not isinstance(value, dict):
        raise HogpProtocolError('HOGP JSON must be an object')
    data = tlvs[1][1] if len(tlvs) == 2 else b''
    if len(data) > 8192:
        raise HogpProtocolError('Oversized HOGP data event')
    if value.get('type') == 'hid_raw':
        if type(value.get('len')) is not int or value['len'] != len(data):
            raise HogpProtocolError('HID raw length mismatch')
    return {'kind': 'json', 'json': value, 'data_hex': data.hex()}


def validate_control(op, fields):
    schemas = {
        'query_cap': (set(), set()), 'query_status': (set(), set()),
        'scan_start': ({'duration_ms'}, {'duration_ms', 'report'}),
        'scan_stop': (set(), set()), 'connect': ({'addr', 'addr_type'}, {'addr', 'addr_type', 'name'}),
        'disconnect': (set(), set()), 'unbond': (set(), set()),
        'query_gatt_list': (set(), set()), 'query_gatt_db': (set(), set()),
        'query_hid_desc': (set(), {'include_usages'}),
        'enable_hid_event': ({'enable'}, {'enable', 'raw'}),
    }
    if op not in schemas:
        raise ValueError('Unsupported explicit HOGP operation')
    required, allowed = schemas[op]
    if not required <= fields.keys() <= allowed:
        raise ValueError('Missing or unexpected HOGP control fields')
    for name in ('report', 'enable', 'raw', 'include_usages'):
        if name in fields and type(fields[name]) is not bool:
            raise ValueError(name + ' must be boolean')
    if op == 'scan_start':
        uint(fields['duration_ms'], 32, 'duration_ms')
        if not 1 <= fields['duration_ms'] <= 60000:
            raise ValueError('Explicit scan duration must be1..60000ms')
    if op == 'connect':
        if not isinstance(fields['addr'], str) or not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', fields['addr']):
            raise ValueError('Use the exact uppercase address from the current scan')
        uint(fields['addr_type'], 8, 'addr_type')
        if 'name' in fields and (not isinstance(fields['name'], str) or '\0' in fields['name']):
            raise ValueError('Invalid accessory name')
    return {'op': op, **fields}


class _Parser:
    fragment_acks = True

    def __init__(self, receive):
        self.stream = GmStream(legacy_repeat_fa=True, fragment_acks=True)
        self.receive = receive
        self.pending = None
        self.seen = False

    def begin(self, key):
        self.pending, self.seen = key, False

    def feed(self, data):
        result = []
        for message in self.stream.feed(data):
            key = message['event'], message['service'], message['command']
            if key[1] == SERVICE and key[2] in ASYNC_COMMANDS and message['tlvs']:
                self.receive(message)
                continue
            if key[1] == SERVICE and message['tlvs']:
                if key != self.pending or self.seen:
                    raise HogpProtocolError('Uncorrelated or duplicate HOGP response')
                self.seen = True
            result.append(message)
        return result


class HogpClient:
    """One sequential controller on an already-connected RFCOMM transport.

    Any request/read error poisons the client; recovering is an explicit new
    session, never a replay of an ambiguous action. Drain events before256
    messages or256KiB of raw bodies accumulate; overflow is an error, not loss.
    """
    def __init__(self, transport, *, timeout=10):
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError('timeout must be positive and at most60s')
        self.transport, self.timeout = transport, timeout
        self.events = deque()
        self.event_bytes = 0
        self.parser = _Parser(self._receive)
        self.event_id = 0x90
        self.failed = False

    def _receive(self, message):
        value = decode(message, asynchronous=True)
        size = sum(len(data) for _, data in message['tlvs'])
        if len(self.events) >= 256 or self.event_bytes + size > 262144:
            raise HogpProtocolError('HOGP event queue overflow; drain explicitly')
        self.events.append(({'event': message['event'], 'command': message['command'], **value}, size))
        self.event_bytes += size

    def request(self, command, body, *, expect_json=False):
        if self.failed:
            raise HogpError('Client stopped after prior error; no automatic recovery')
        if command not in (1, 3):
            raise ValueError('Unsupported HOGP request command')
        self.event_id = self.event_id % 255 + 1
        key = self.event_id, SERVICE, command
        self.parser.begin(key)
        try:
            message = request_gm(_DeadlineIO(self.transport, self.timeout), self.parser,
                                 *key, body, timeout=self.timeout)
            result = decode(message)
            if (result['kind'] == 'json') != expect_json:
                raise HogpProtocolError('Unexpected control response kind')
            if result['kind'] == 'json' and result['data_hex']:
                raise HogpProtocolError('Unexpected control response bytes')
            self.parser.begin(None)
            return result
        except Exception:
            self.failed = True
            raise

    def control(self, op, **fields):
        body = json_tlv(validate_control(op, fields))
        return self.request(1, body, expect_json=op in ('query_cap', 'query_status', 'enable_hid_event'))

    def gatt(self, op, *, seq, list_id, value_handle, data=None, cccd_handle=None, subscribe_type=None):
        """Queue an explicit operation. Await a separate command4 result by seq.

        Caller must use a current complete GATT-list generation and maintain
        pending seq uniqueness. No handle discovery, auto-splitting or retry.
        """
        if op not in ('read', 'write', 'write_no_rsp', 'subscribe', 'unsubscribe'):
            raise ValueError('Invalid GATT operation')
        uint(seq, 16, 'seq'); uint(list_id, 8, 'list_id'); uint(value_handle, 16, 'value_handle')
        if not seq or not value_handle:
            raise ValueError('seq and value_handle must be nonzero')
        value = {'seq': seq, 'op': op, 'list_id': list_id, 'value_handle': value_handle}
        if op in ('subscribe', 'unsubscribe'):
            uint(cccd_handle, 16, 'cccd_handle')
            if not cccd_handle:
                raise ValueError('CCCD must be nonzero')
            value['cccd_handle'] = cccd_handle
            if op == 'subscribe':
                if subscribe_type not in ('notify', 'indicate'):
                    raise ValueError('Explicit subscription type required')
                value['subscribe_type'] = subscribe_type
            elif subscribe_type is not None:
                raise ValueError('Unsubscribe does not take subscription type')
        elif cccd_handle is not None or subscribe_type is not None:
            raise ValueError('Unexpected subscription fields')
        body = json_tlv(value)
        if op in ('write', 'write_no_rsp'):
            if not isinstance(data, (bytes, bytearray)) or len(data) > 64:
                raise ValueError('Explicit write bytes must fit native64-byte limit')
            body += b'\x01' + len(data).to_bytes(3, 'big') + bytes(data)
        elif data is not None:
            raise ValueError('Unexpected GATT data')
        return self.request(3, body)

    def drain_events(self):
        result = [event for event, _ in self.events]
        self.events.clear(); self.event_bytes = 0
        return result

    def read_events(self, seconds):
        if self.failed:
            raise HogpError('Client stopped after prior error')
        if type(seconds) not in (int, float) or not 0 < seconds <= 60:
            raise ValueError('Read duration must be positive and at most60s')
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.parser.feed(self.transport.read(remaining))
            return self.drain_events()
        except TimeoutError:
            # An idle read has no mutating request in flight.
            return self.drain_events()
        except Exception:
            self.failed = True
            raise
