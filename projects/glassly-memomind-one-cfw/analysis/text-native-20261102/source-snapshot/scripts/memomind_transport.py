#!/usr/bin/env python3
"""Host transport for the task-local Android RFCOMM bridge and public GM codec."""
from collections import deque
import json
import select
import socket
import time

MAX_GM_LOGICAL = 80 * 1024


class BridgeError(RuntimeError):
    pass


class RfcommBridge:
    """Sequential request API; async Bluetooth data is retained while awaiting replies."""
    def __init__(self, host="127.0.0.1", port=38741, timeout=20, trace=None, connected_socket=None):
        self.socket = connected_socket or socket.create_connection((host, port), timeout=timeout)
        self.socket.setblocking(False)
        self.timeout = timeout
        self.trace = trace
        self.buffer = bytearray()
        self.incoming = deque()
        self.next_id = 1
        try:
            ready = self._receive(time.monotonic() + timeout)
            self.capabilities = ready
            if ready.get("event") != "ready" or ready.get("protocol") != 1:
                raise BridgeError("Unexpected bridge protocol greeting")
        except Exception:
            self.close()
            raise

    def _record(self, direction, message):
        if self.trace:
            self.trace({"host_time_ns": time.time_ns(), "direction": direction, "message": message})

    def _receive(self, deadline):
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.socket], [], [], remaining)[0]:
                raise TimeoutError("Bridge response timed out")
            data = self.socket.recv(65536)
            if not data:
                self.incoming.clear()
                self.buffer.clear()
                raise BridgeError("Bridge TCP connection closed")
            self.buffer.extend(data)
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        message = json.loads(line)
        self._record("receive", message)
        return message

    def _send(self, message, deadline):
        data = memoryview((json.dumps(message, separators=(",", ":")) + "\n").encode())
        while data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.socket], [], remaining)[1]:
                raise TimeoutError("Bridge write timed out")
            sent = self.socket.send(data)
            if not sent:
                raise BridgeError("Bridge TCP connection closed during write")
            data = data[sent:]
        self._record("send", message)

    def _event(self, message):
        event = message.get("event")
        if event == "data":
            self.incoming.append(bytes.fromhex(message["hex"]))
        elif event == "disconnected":
            self.incoming.clear()
            raise BridgeError("RFCOMM disconnected: " + str(message.get("reason")))
        else:
            raise BridgeError("Unexpected bridge event: " + str(event))

    def request(self, operation, **parameters):
        identifier = self.next_id
        self.next_id += 1
        deadline = time.monotonic() + self.timeout
        self._send({"id": identifier, "op": operation, **parameters}, deadline)
        while True:
            message = self._receive(deadline)
            if "event" in message:
                self._event(message)
                continue
            if message.get("id") != identifier:
                raise BridgeError("Bridge response ID does not match pending request")
            if not message.get("ok"):
                raise BridgeError(str(message.get("error")))
            return message.get("result", {})

    def connect(self, address, service="control"):
        self.incoming.clear()
        return self.request("connect", address=address.upper(), service=service)

    def write(self, data):
        result = self.request("write", hex=bytes(data).hex())
        if result.get("written") != len(data):
            raise BridgeError("Bridge did not confirm the complete local socket write")

    def read(self, timeout=None):
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while not self.incoming:
            message = self._receive(deadline)
            if "event" not in message:
                raise BridgeError("Unexpected response without a pending request")
            self._event(message)
        return self.incoming.popleft()

    def close(self):
        if getattr(self, "socket", None) is not None:
            self.socket.close()
            self.socket = None
        self.buffer.clear()
        self.incoming.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def gm_frames(event, service, command, body=b"", *, fragment_payload=503):
    """GM framing. Public/default bodies503; pinned MemoMind RFCOMM ingress642.

    The two directions are asymmetric on H001Y1.0.3.127. Select642 explicitly
    for large requests to its RFCOMM receiver; replies still decode at503.
    """
    if fragment_payload not in (503, 642):
        raise ValueError('Unsupported GM fragment payload profile')
    body = bytes(body)
    logical = len(body) + 9
    if logical > MAX_GM_LOGICAL:
        raise ValueError("GM logical message exceeds documented limit")
    result = []
    for index, offset in enumerate(range(0, max(1, len(body)), fragment_payload)):
        raw = bytes([0xfa if index == 0 else index]) + logical.to_bytes(3, "big")
        raw += bytes([event, service, command]) + body[offset:offset + fragment_payload]
        result.append(raw + (sum(raw) & 0xffff).to_bytes(2, "big"))
    return result


def parse_tlvs(body):
    result = []
    offset = 0
    while offset < len(body):
        if len(body) - offset < 4:
            raise ValueError("Truncated GM TLV header")
        kind = body[offset]
        length = int.from_bytes(body[offset + 1:offset + 4], "big")
        offset += 4
        if length > len(body) - offset:
            raise ValueError("Truncated GM TLV value")
        value = body[offset:offset + length]
        offset += length
        fixed = {3: 4, 6: 1, 7: 2, 8: 1}
        if kind in fixed and len(value) != fixed[kind]:
            raise ValueError("Invalid fixed-width GM TLV")
        result.append((kind, value))
    return result


class GmStream:
    """Documented SPP stream framing; reset on connection loss.

    legacy_repeat_fa handles the repeated-FA continuation heads observed in
    the official app's 1.0.2.151 traffic. It is opt-in because current public
    docs require numbered continuation heads.
    """
    def __init__(self, legacy_repeat_fa=False, fragment_acks=False):
        self.legacy_repeat_fa = legacy_repeat_fa
        self.fragment_acks = fragment_acks
        self.reset()

    def reset(self):
        self.buffer = bytearray()
        self.body = bytearray()
        self.key = None
        self.fragment = 0

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        try:
            while len(self.buffer) >= 7:
                head = self.buffer[0]
                logical = int.from_bytes(self.buffer[1:4], "big")
                key = (logical, *self.buffer[4:7])
                if not 9 <= logical <= MAX_GM_LOGICAL:
                    raise ValueError("Invalid GM logical length")
                # The native receiver echoes each accepted fragment's head in
                # an independent empty9B ACK. It is not a response continuation.
                if self.fragment_acks and logical == 9 and (head == 0xfa or 1 <= head < 0xf0):
                    if len(self.buffer) < 9:
                        break
                    packet = bytes(self.buffer[:9])
                    if sum(packet[:-2]) & 0xffff != int.from_bytes(packet[-2:], 'big'):
                        raise ValueError('GM additive checksum mismatch')
                    del self.buffer[:9]
                    messages.append({'head': head, 'event': key[1], 'service': key[2],
                                     'command': key[3], 'body': b'', 'tlvs': []})
                    continue
                repeated = self.legacy_repeat_fa and self.key == key and head == 0xfa
                first = head == 0xfa and not repeated
                accumulated = 0 if first else len(self.body)
                if not first and (self.key != key or (head != self.fragment and not repeated)):
                    raise ValueError("GM continuation identity or order mismatch")
                physical = min(512, logical - accumulated)
                if physical < 9:
                    raise ValueError("Invalid GM continuation length")
                if len(self.buffer) < physical:
                    break
                packet = bytes(self.buffer[:physical])
                if sum(packet[:-2]) & 0xffff != int.from_bytes(packet[-2:], "big"):
                    raise ValueError("GM additive checksum mismatch")
                del self.buffer[:physical]
                if first:
                    self.key = key
                    self.body.clear()
                    self.fragment = 0
                self.body.extend(packet[7:-2])
                self.fragment += 1
                if len(self.body) == logical - 9:
                    messages.append({"head": head, "event": key[1], "service": key[2], "command": key[3],
                                     "body": bytes(self.body), "tlvs": parse_tlvs(self.body)})
                    self.body.clear()
                    self.key = None
                    self.fragment = 0
        except Exception:
            self.reset()
            raise
        return messages


def await_gm(transport, parser, event, service, command, timeout=10, unsolicited=None):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out awaiting correlated GM business response")
        matched = None
        for message in parser.feed(transport.read(remaining)):
            if (message["event"], message["service"], message["command"]) == (event, service, command):
                if not message["tlvs"]:
                    continue  # Intermediate fragment ACK is not a final response.
                matched = message
            elif unsolicited is not None:
                unsolicited.append({"event": message["event"], "service": message["service"],
                                    "command": message["command"], "body_hex": message["body"].hex()})
        if matched is not None:
            return matched


def request_gm(transport, parser, event, service, command, body=b'', timeout=10):
    """H001Y1.0.3.127 request:642-byte ingress and checked per-fragment ACKs.

    Stops immediately on a business rejection; never retries ambiguous delivery.
    Caller supplies GmStream(fragment_acks=True), whose replies remain503-byte.
    """
    if not parser.fragment_acks:
        raise ValueError('Native request requires explicit fragment-ACK parser')
    frames = gm_frames(event, service, command, body, fragment_payload=642)
    for index, frame in enumerate(frames):
        transport.write(frame)
        if index == len(frames)-1:
            return await_gm(transport, parser, event, service, command, timeout=timeout)
        deadline = time.monotonic()+timeout
        acknowledged = False
        while not acknowledged:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Timed out awaiting GM fragment acknowledgment')
            for message in parser.feed(transport.read(remaining)):
                if (message['event'], message['service'], message['command']) != (event, service, command):
                    continue
                if message['tlvs']:
                    # Preserve native rejection for caller interpretation and
                    # stop transmitting before touching any subsequent frame.
                    return message
                if message['head'] != frame[0]:
                    raise BridgeError('GM fragment acknowledgment head mismatch')
                acknowledged = True
