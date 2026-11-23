#!/usr/bin/env python3
"""Execute linked GM ingress, record parser, inflater and scene on RV32."""
import argparse
import binascii
import json
import struct
import unittest
import zlib
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import rect_copy_runtime_emulator_test as R
import text_command_runtime_emulator_test as T
from wake_control_runtime_emulator_test import WakeMachine


def record(body, flags=9, compressed=None):
    wire = body if compressed is None else compressed
    return struct.pack('<BHH', flags, len(wire), binascii.crc_hqx(body, 65535)) + wire


class RecordMachine(WakeMachine):
    def cstring(self, pointer):
        output = bytearray()
        for i in range(6144):
            byte = self.read(pointer + i, 1)[0]
            if not byte:
                return output.decode('ascii')
            output.append(byte)
        raise AssertionError('Unterminated JSON')

    def packet(self, data, seq=0, flags=0xc1):
        _, values = self.send_scene(bytes([126, 1, seq, flags]) + data, patch_epoch=False)
        value = next(v for v in values if v.get('glassly') == 'record-transport')
        frames = [bytes.fromhex(f) for f in value['frames']]
        return value, frames

    def records(self, data, seq=0, split=128):
        replies = []
        for i, offset in enumerate(range(0, len(data), split)):
            flags = 1 | (0x80 if not i else 0) | (0x40 if offset + split >= len(data) else 0)
            value, frames = self.packet(data[offset:offset + split], (seq + i) & 255, flags)
            assert value['status'] == 0, value
            replies += frames
        return replies

    def clear(self):
        self.call('glassly_launcher_destroy_entry', display=True)
        assert not (self.images or self.timers or self.owned_live())


class Tests(unittest.TestCase):
    def test_empty_shapes_take_over_animation(self):
        for mode in (36, 164):
            m = RecordMachine(); m.establish()
            m.send_scene(S.animate_packet()); m.tick_at(120)
            before = m.pixels()
            frames = m.records(record(bytes([mode, 0])))
            self.assertEqual(frames[-1][0], 1)
            self.assertEqual(m.pixels(), before)
            m.tick_at(500)
            self.assertEqual(m.pixels(), before)
            m.clear()

    def test_high_bit_cache_and_shape_aliases(self):
        plain, alias = RecordMachine(), RecordMachine()
        commands = [S.reset_packet(), S.put_packet(), S.show_packet(),
                    bytes([40]) + bytes(8), bytes([39]) + bytes(6),
                    G.point_message(),
                    bytes([36, 0]), S.reset_packet()]
        epoch = 0
        for index, command in enumerate(commands):
            if command[0] in (37, 38, 39):
                command = command[:1] + struct.pack("<H", epoch) + command[3:]
            high = bytes([command[0] | 128]) + command[1:]
            a = plain.records(record(command), index * 10)
            b = alias.records(record(high), index * 10)
            self.assertEqual(a[-1][0], 1, command.hex())
            self.assertEqual(b[-1][0], 1, high.hex())
            self.assertEqual(a[:-1], b[:-1])
            if command[0] == 41:
                epoch = int.from_bytes(a[0][9:11], "little")
            self.assertEqual(plain.pixels(), alias.pixels())
        plain.clear(); alias.clear()

    def test_compressed_drawing_dictionary_and_maximum(self):
        m = RecordMachine()
        m.send_scene(S.reset_packet())
        payload = R.keyframe()
        compressor = zlib.compressobj()
        packed = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
        frames = m.records(record(payload, 13, packed))
        self.assertEqual(frames[-1][0], 1)
        expected = m.pixels()
        plain = RecordMachine(); plain.send_scene(payload)
        self.assertEqual(expected, plain.pixels()); plain.clear()
        # Arbitrary trailing bundle bytes are intentionally ignored by G2 mode 8/count 0.
        payload = b'\x08\0' + bytes((i * 37) & 255 for i in range(4094))
        packed = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
        self.assertEqual(m.records(record(payload, 5, packed), 70)[-1][0], 1)
        packed = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
        self.assertLess(len(packed), 100)
        self.assertEqual(m.records(record(payload, 5, packed), 90)[-1][0], 1)
        payload = b'\x08\0' + b'x' * 65533
        packed = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
        self.assertEqual(m.records(record(payload, 5, packed), 110)[-1][0], 1)
        self.assertEqual(m.pixels(), expected)
        m.clear()

    def test_replies_multiple_records_and_clear_inside_dispatch(self):
        m = RecordMachine()
        frames = m.records(record(S.reset_packet()))
        self.assertEqual([f[0] for f in frames], [5, 1])
        self.assertEqual(frames[0][5], S.reset_packet()[0])
        body = record(b'\x07\x03') + record(b'\x24\0') + record(b'\x0b') + record(b'\x24\0')
        frames = m.records(body, 30)
        self.assertEqual([f[0] for f in frames], [5, 1, 1, 1, 3])
        self.assertEqual(len(frames[0]), 25)
        self.assertFalse(m.graphics())
        m.clear()

    def test_crc_context_failure_and_expiry(self):
        m = RecordMachine()
        before = m.send_scene(R.keyframe()); pixels = m.pixels()
        bad = bytearray(record(T.text(b'BAD'))); bad[3] ^= 1
        self.assertEqual(m.records(bytes(bad))[-1][0], 3)
        self.assertEqual(m.pixels(), pixels)
        self.assertEqual(m.records(record(T.text(b'SWIFT'), 1), 10)[-1][0], 3)
        self.assertEqual(m.records(record(T.text(b'SWIFT')), 20)[-1][0], 1)
        m.control(5)
        m.tick_at(m.now + 30001)
        self.assertEqual(m.records(record(T.text(b'SWIFT'), 1), 30)[-1][0], 3)
        m.clear()

    def test_low_memory_and_raw_assembly_exclusion(self):
        m = RecordMachine()
        head = struct.pack('<BBIH', 127, 0, 23, 10)
        m.send_scene(head, patch_epoch=False)
        _, values = m.send_scene(bytes([126, 1, 0, 0xc1]) + record(b'\x24\0'), patch_epoch=False)
        self.assertEqual(values[0]['result'], 'invalid')
        m.send_scene(b'\x0b', patch_epoch=False)
        m.free_bytes = 160000
        _, values = m.send_scene(bytes([126, 1, 0, 0xc1]) + record(b'\x24\0'), patch_epoch=False)
        self.assertEqual(values[0]['result'], 'allocation-failed')
        m.free_bytes = 353656; m.clear()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    G.BUILD = a.build.resolve()
    build = json.loads((G.BUILD / 'build.json').read_text())
    assert build['record_transport']
    G.PINNED_SHA = build['blob_sha256']; G.RESULTS.clear()
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    a.report.write_text(json.dumps(dict(passed=result.wasSuccessful(), groups=result.testsRun,
        runtimeSHA256=G.PINNED_SHA, maxObservedStackBytes=max((x['observed_stack_bytes'] for x in G.RESULTS), default=0),
        calls=G.RESULTS, nativeAPIsMocked=True, hardwareTested=False), indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
