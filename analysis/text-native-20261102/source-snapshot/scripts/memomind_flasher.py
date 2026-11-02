#!/usr/bin/env python3
"""Captured-stock MemoMind OTA transaction driver. Default use is offline replay.

Eligible images are captured H001Y stock or an exactly reproduced, hash-pinned
patch manifest based on that stock, or the fixed runtime-probe constructor
based on the visually verified text image. No retry, resume, rollback, or
post-reboot success claim. Live use is explicit.
"""
import argparse
from collections import deque
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time
import threading

from apply_memomind_patch import apply_patch
from build_memomind_runtime import verify_runtime
from build_memomind_graphics import verify_graphics, FORMAT as GRAPHICS_FORMAT
from build_memomind_exclusive_storage import verify_exclusive_reader, READER_FORMAT
from build_memomind_flash_canary import verify_canary, FORMAT as CANARY_FORMAT
from decode_memomind import OtaStream, encode_ota, encode_chunk
from memomind_ota import unpack_ota
from memomind_transport import RfcommBridge, GmStream, gm_frames, await_gm
from probe_memomind import probe

STOCK_SHA256 = '08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712'
ROOT = Path(__file__).resolve().parents[1]
MAX_STAGED_PAYLOAD = 0x25e000  # Captured partition type4 / native e2 capacity.


class TransactionError(RuntimeError):
    """Unsupported or ambiguous state. Caller must not automatically retry."""


def require(condition, reason):
    if not condition:
        raise TransactionError(reason)


def validate_image(data, patch_manifest=None, stock_source=None,
                   runtime_manifest=None, runtime_blob=None):
    actual = hashlib.sha256(data).hexdigest()
    require(patch_manifest is None or runtime_manifest is None,
            'Patch and runtime manifests are mutually exclusive')
    require((runtime_manifest is None) == (runtime_blob is None),
            'Runtime manifest and runtime blob must be supplied together')
    has_manifest = patch_manifest is not None or runtime_manifest is not None
    require(has_manifest == (stock_source is not None),
            'A modification manifest and its exact source must be supplied together')
    if not has_manifest:
        require(actual == STOCK_SHA256, 'Unsupported image: modified images require a verified manifest and source')
        report, _ = unpack_ota(data)
        return report, False
    require(len(data) - 18 <= MAX_STAGED_PAYLOAD,
            'Modified payload exceeds observed staging capacity 0x25e000')
    report, _ = unpack_ota(data)
    if runtime_manifest is not None:
        require(isinstance(runtime_manifest, dict), 'Runtime manifest must be a JSON object')
        verifier = {GRAPHICS_FORMAT: verify_graphics,
                    READER_FORMAT: verify_exclusive_reader,
                    CANARY_FORMAT: verify_canary}.get(runtime_manifest.get('format'), verify_runtime)
        rebuilt, runtime_report = verifier(stock_source, runtime_blob, runtime_manifest)
        require(rebuilt == data, 'Image is not byte-identical to the reproduced runtime manifest')
        report['runtime_verification'] = runtime_report
        return report, True
    require(hashlib.sha256(stock_source).hexdigest() == STOCK_SHA256,
            'Patch source must be the exact captured stock image')
    rebuilt, patch_report = apply_patch(stock_source, patch_manifest)
    require(rebuilt == data, 'Image is not byte-identical to the reproduced patch manifest')
    require(actual != STOCK_SHA256, 'Patch eligibility requires an actual modified image')
    report['patch_verification'] = patch_report
    return report, True


def load_image(path, expected_sha256, patch_manifest=None, stock_source=None,
               runtime_manifest=None, runtime_blob=None):
    data = Path(path).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    require(actual == expected_sha256.lower(), 'Image does not match explicit expected SHA-256')
    report, _ = validate_image(data, patch_manifest, stock_source, runtime_manifest, runtime_blob)
    return data, report


class ControlLinkMonitor:
    """Drain/log unsolicited normal traffic while preserving the stock control link."""
    def __init__(self, control):
        self.control = control
        self.stopping = threading.Event()
        self.failure = None
        self.thread = threading.Thread(target=self._run, name='memomind-control-monitor', daemon=True)

    def _run(self):
        while not self.stopping.is_set():
            try:
                self.control.read(0.2)  # Raw receive bytes remain in the bridge trace.
            except TimeoutError:
                continue
            except Exception as exc:
                self.failure = exc
                return

    def start(self):
        self.thread.start()

    def check(self):
        require(self.failure is None, f'Preserved control connection failed: {self.failure}')

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=1)
        require(not self.thread.is_alive(), 'Control monitor did not stop')


def validate_identity(device, address):
    require(device.get('model') == 'H001Y', 'Unsupported device model')
    require(device.get('hver') == '2.1.2' and device.get('fver') == '1.3',
            'Unsupported hardware/front version')
    require(device.get('ver') in ('1.0.2.151', '1.0.3.127'), 'Unsupported source firmware')
    require(device.get('mac', '').upper() == address.upper(), 'Device-info MAC differs from target')


class StockTransaction:
    """Consumes device requests; each logical block advances base sequence once.

    The transport must already have a fresh, verified control connection.
    Any exception ends this attempt; no command is resent automatically.
    """
    def __init__(self, transport, image, device, address, pace=0.045, timeout=15,
                 patch_manifest=None, stock_source=None, ota_transport=None,
                 runtime_manifest=None, runtime_blob=None):
        _, self.modified = validate_image(image, patch_manifest, stock_source, runtime_manifest, runtime_blob)
        validate_identity(device, address)
        self.control = transport
        self.transport = ota_transport if ota_transport is not None else transport
        self.monitor = None
        self.image, self.address = image, address
        self.image_sha256 = hashlib.sha256(image).hexdigest()
        self.device, self.pace, self.timeout = device, pace, timeout
        self.sequence = 0
        self.parser = OtaStream()
        self.pending = deque()
        self.phase = 'validated'
        self.blocks = []
        self.chunks = 0

    def write(self, data):
        if self.monitor:
            self.monitor.check()
        self.transport.write(data)

    def next_sequence(self):
        self.sequence = (self.sequence + 1) & 255
        return self.sequence

    def response(self, command, sequence):
        deadline = time.monotonic() + self.timeout
        while not self.pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('OTA reply timeout')
            self.pending.extend(self.parser.feed(self.transport.read(remaining)))
        frame = self.pending.popleft()
        require(frame[3] == 0 and frame[4] == command, 'Unexpected OTA reply flags/command')
        payload = frame[7:-1]
        require(len(payload) >= 2 and payload[0] == 0 and payload[1] == sequence,
                'Unexpected OTA transport status/sequence')
        require(not self.pending and not self.parser.buffer, 'Unexpected additional OTA reply bytes')
        return payload[2:]

    def command(self, command, parameters=b''):
        self.phase = f'command 0x{command:02x}'
        sequence = self.next_sequence()
        self.write(encode_ota(command, sequence, parameters))
        return self.response(command, sequence)

    def run(self, check_only=False):
        try:
            return self._run(check_only)
        except Exception as exc:
            raise TransactionError(f'Stopped during {self.phase}: {exc}. No retry was sent; '
                                   'device state may be ambiguous. Close connection and inspect logs.') from exc
        finally:
            if self.monitor:
                self.monitor.stop()

    def _run(self, check_only):
        self.phase = 'pre-OTA control notification'
        self.control.write(gm_frames(0x15, 1, 0x1c, bytes.fromhex('0800000101'))[0])
        reply = await_gm(self.control, GmStream(legacy_repeat_fa=True), 0x15, 1, 0x1c, self.timeout)
        # Private command-specific acceptance is STATUS 1 in the successful stock capture.
        require(reply['tlvs'] == [(6, b'\x01')], 'Unsupported pre-OTA notification reply')
        if self.control is self.transport:
            self.transport.request('disconnect')
        self.transport.connect(self.address, 'ota')
        if self.control is not self.transport:
            self.monitor = ControlLinkMonitor(self.control)
            self.monitor.start()
        attached = self.command(0x02, b'\xff' * 5)
        fields = {}
        while attached:
            length = attached[0]
            require(length >= 1 and len(attached) >= length + 1, 'Malformed attach TLV')
            kind, value = attached[1], attached[2:length + 1]
            require(kind not in fields, 'Duplicate attach TLV')
            fields[kind] = value
            attached = attached[length + 1:]
        require(fields.get(1) == self.image[:4], 'OTA attach profile differs from image')
        # Field 2 is 6464 in the capture. Battery semantics/threshold are not proven;
        # preserve it and every other unknown attach field without interpreting them.
        require(self.command(0xe1) == bytes.fromhex('000000000012'),
                'Unsupported OTA file-identification request')
        require(self.command(0xe2, self.image[:18]) == b'\x03',
                'Device did not return supported can-update result 3; entry not sent')
        result = {'image_sha256': self.image_sha256, 'modified_image': self.modified,
                  'control_link_preserved': self.control is not self.transport, 'device': self.device,
                  'attach_fields': {str(k): v.hex() for k, v in fields.items()},
                  'check_only': check_only}
        if check_only:
            return {**result, 'state': 'eligible; stopped before OTA entry', 'blocks': 0, 'chunks': 0}
        entry = self.command(0xe3)
        require(len(entry) == 8 and entry[0] == 0 and entry[-1] == 1,
                'Unsupported OTA entry result/CRC mode')
        offset, size = int.from_bytes(entry[1:5], 'big'), int.from_bytes(entry[5:7], 'big')
        require(not self.modified or offset == 18,
                'Modified image requires fresh offset 18; refusing stale/partial resume before chunks')
        previous_end = None
        while True:
            self.phase = f'block at offset {offset}, length {size}'
            require(0 < size <= 4096 and 0 < offset < len(self.image) and offset + size <= len(self.image),
                    'Requested block out of supported bounds')
            require(previous_end is None or offset == previous_end,
                    'Noncontiguous/repeated range requires unsupported recovery logic')
            base = self.next_sequence()
            for index, relative in enumerate(range(0, size, 630)):
                sequence = (base + index) & 255
                fragment = self.image[offset + relative:offset + min(relative + 630, size)]
                self.write(encode_chunk(sequence, offset + relative, fragment))
                self.chunks += 1
                if relative + 630 < size and self.pace:
                    time.sleep(self.pace)
            reply = self.response(0xe5, sequence)
            require(len(reply) == 9 and reply[0] == 0, 'Unsupported OTA block result')
            require(reply[7:9] == b'\x00\x00', 'Nonzero delay/retry field is unsupported')
            self.blocks.append({'offset': offset, 'length': size, 'base_sequence': base,
                                'ack_sequence': sequence})
            previous_end = offset + size
            offset, size = int.from_bytes(reply[1:5], 'big'), int.from_bytes(reply[5:7], 'big')
            if offset == 0 and size == 0:
                require(previous_end == len(self.image), 'Premature terminal ACK before image EOF')
                break
        require(self.command(0xe6) == b'\x00', 'Unsupported update-status result')
        require(self.command(0x03, b'\x00') == b'\x00', 'Unsupported reboot result')
        self.phase = 'reboot acknowledged'
        return {**result, 'state': self.phase, 'blocks': len(self.blocks), 'chunks': self.chunks,
                'transferred_range': [self.blocks[0]['offset'], previous_end],
                'post_reboot_version_verified': False}


def read_transcript(path):
    """Read actual TShark RFCOMM records, retaining raw bytes and order."""
    rows = []
    device = None
    parser = GmStream(legacy_repeat_fa=True)
    for line in Path(path).read_text().splitlines():
        number, timestamp, direction, handle, channel, raw = line.split('\t')
        number, direction, channel = int(number), int(direction, 0), int(channel)
        raw = bytes.fromhex(raw)
        if channel == 5 and direction == 1 and number < 1615:
            for message in parser.feed(raw):
                if message['service'] == 1 and message['command'] == 2:
                    strings = [v for k, v in message['tlvs'] if k == 2]
                    if len(strings) == 1:
                        device = json.loads(strings[0])
        if number in (1615, 1617) or channel == 6:
            rows.append({'frame': number, 'direction': direction, 'channel': channel, 'data': raw})
    require(device is not None, 'Recorded device identity missing')
    require(rows and rows[0]['frame'] == 1615, 'Expected captured transaction start missing')
    return rows, device


class ReplayTransport:
    """Strict chronological comparison against raw captured outgoing bytes."""
    def __init__(self, rows):
        self.rows, self.position, self.writes, self.reads = rows, 0, 0, 0
        self.service = 'control'
        self.outgoing_hash = hashlib.sha256()

    def take(self, direction):
        require(self.position < len(self.rows), 'Replay transcript exhausted')
        row = self.rows[self.position]
        require(row['direction'] == direction, f"Replay ordering mismatch at frame {row['frame']}")
        require(row['channel'] == {'control': 5, 'ota': 6}[self.service], 'Replay service mismatch')
        self.position += 1
        return row

    def write(self, data):
        row = self.take(0)
        require(data == row['data'], f"Generated bytes differ from capture at frame {row['frame']}")
        self.writes += 1
        self.outgoing_hash.update(data)

    def read(self, timeout=None):
        self.reads += 1
        return self.take(1)['data']

    def request(self, operation):
        require(operation == 'disconnect', 'Unexpected replay operation')
        return {}

    def connect(self, address, service):
        require(service == 'ota', 'Unexpected replay connection')
        self.service = service
        return {}


def replay(transcript, image, check_only=False):
    rows, device = read_transcript(transcript)
    transport = ReplayTransport(rows)
    result = StockTransaction(transport, image, device, device['mac'], pace=0).run(check_only)
    if not check_only:
        require(transport.position == len(rows), 'Unconsumed transcript records')
    return {**result, 'mode': 'offline replay', 'records_consumed': transport.position,
            'records_total': len(rows), 'outgoing_packets_identical': transport.writes,
            'incoming_packets_consumed': transport.reads,
            'outgoing_wire_sha256': transport.outgoing_hash.hexdigest(),
            'transcript_sha256': hashlib.sha256(Path(transcript).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    for mode in ('replay', 'live'):
        sub = modes.add_parser(mode)
        sub.add_argument('--firmware', type=Path, required=True)
        sub.add_argument('--expected-sha256', required=True)
        if mode == 'replay':
            sub.add_argument('--transcript', type=Path, default=ROOT / 'analysis/protocol/ota-final/rfcomm.tsv')
            sub.add_argument('--check-only', action='store_true')
        else:
            eligibility = sub.add_mutually_exclusive_group()
            eligibility.add_argument('--patch-manifest', type=Path, help='Exact reproducible memomind-body-patch-v1 manifest')
            eligibility.add_argument('--runtime-manifest', type=Path, help='Exact probe, graphics, exclusive reader or fixed-canary manifest')
            sub.add_argument('--runtime-blob', type=Path, help='Exact appended blob required by runtime manifest')
            sub.add_argument('--stock-source', type=Path,
                             help='Exact source: captured stock for body patch, verified text OTA for runtime probe')
            sub.add_argument('--address', required=True)
            sub.add_argument('--host', default='127.0.0.1')
            sub.add_argument('--port', type=int, default=38741)
            sub.add_argument('--trace', type=Path, required=True)
            gate = sub.add_mutually_exclusive_group(required=True)
            gate.add_argument('--check-only', action='store_true')
            gate.add_argument('--confirm-write', action='store_true',
                              help='Explicitly authorize entering OTA, sending verified image bytes, and rebooting')
    args = parser.parse_args()
    manifest_path = getattr(args, 'patch_manifest', None)
    runtime_path = getattr(args, 'runtime_manifest', None)
    blob_path = getattr(args, 'runtime_blob', None)
    source_path = getattr(args, 'stock_source', None)
    require(bool(runtime_path) == bool(blob_path), 'Supply both --runtime-manifest and --runtime-blob')
    require(bool(manifest_path or runtime_path) == bool(source_path),
            'Supply --stock-source with exactly one modification manifest')
    manifest = json.loads(manifest_path.read_text()) if manifest_path else None
    source = source_path.read_bytes() if source_path else None
    runtime_manifest = json.loads(runtime_path.read_text()) if runtime_path else None
    runtime_blob = blob_path.read_bytes() if blob_path else None
    image, _ = load_image(args.firmware, args.expected_sha256, manifest, source,
                          runtime_manifest, runtime_blob)
    if args.mode == 'replay':
        result = replay(args.transcript, image, args.check_only)
    else:
        with args.trace.open('x') as trace, ExitStack() as stack:
            trace_lock = threading.Lock()
            def recorder(session):
                def record(row):
                    with trace_lock:
                        trace.write(json.dumps({'session': session, **row}) + '\n')
                        trace.flush()
                return record
            control = stack.enter_context(RfcommBridge(args.host, args.port, trace=recorder('control')))
            require(control.capabilities.get('maxSessions', 1) >= 2,
                    'Install rebuilt two-session bridge before live OTA')
            identity = probe(control, args.address, legacy_repeat_fa=True)['device']
            validate_identity(identity, args.address)
            ota = stack.enter_context(RfcommBridge(args.host, args.port, trace=recorder('ota')))
            result = StockTransaction(control, image, identity, args.address,
                                      patch_manifest=manifest, stock_source=source,
                                      ota_transport=ota, runtime_manifest=runtime_manifest,
                                      runtime_blob=runtime_blob).run(args.check_only)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
