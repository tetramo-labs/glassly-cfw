from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from radio_disasm import decode, decode_blob
from startup import unpack_data, reconstruct
from firmware_image import load_stock
from memory_layout import analyze as analyze_memory


class StartupTests(unittest.TestCase):
    def test_literal_and_zero_runs(self):
        self.assertEqual(unpack_data(b'\x14ABC', 4), (b'ABC\0', 4))
        # Extended literal count and extended zero-run count.
        self.assertEqual(unpack_data(b'\x00\x04\x02ABC', 5), (b'ABC\0\0', 6))

    def test_overlapping_backreference(self):
        self.assertEqual(unpack_data(b'\x1ax\x01', 4), (b'xxxx', 3))
        self.assertEqual(unpack_data(b'\x0b\x02ab\x02', 6), (b'ababab', 5))

    def test_bad_runs_rejected(self):
        for data, size in [(b'', 1), (b'\x14AB', 4), (b'\x14ABC', 3),
                           (b'\x18\x00', 4), (b'\x1ax\x00', 4),
                           (b'\x1ax\x02', 4), (b'\x1ax\x01', 3)]:
            with self.subTest(data=data, size=size), self.assertRaises(ValueError):
                unpack_data(data, size)

    def test_other_scatter_layout_rejected(self):
        with self.assertRaises(ValueError):
            reconstruct(bytes(0x11e00))


class RadioDecoderTests(unittest.TestCase):
    def test_dispatch_and_rom_boundary(self):
        self.assertEqual(decode(0xc0048530), ('beq', '0x09, 0x0530', 0x530))
        self.assertEqual(decode(0x20204eda), ('branch', '0x4eda, always', 0x4eda))
        self.assertEqual(decode(0x24345e1d), ('nbranch', '0x5e1d, user', 0x5e1d))
        self.assertEqual(decode(0x20600000), ('rtn', 'always', None))

    def test_target_memory_width_not_yc1121_width(self):
        self.assertEqual(decode(0x6fe44652), ('fetch', '2, 0x4652', None))
        self.assertEqual(decode(0x6844467b), ('fetcht', '2, 0x467b', None))
        self.assertEqual(decode(0xe7e60005), ('istore', '3, contw', None))
        self.assertEqual(decode(0xe7e80005), ('istore', '4, contw', None))
        self.assertEqual(decode(0xe7f00005), ('istore', '8, contw', None))

    def test_unknown_and_trailing_data_are_not_instructions(self):
        self.assertEqual(decode(0xffffffff)[0], '.word')
        self.assertEqual(decode(0xc1000001)[0], '.word')  # reserved return target
        insns = decode_blob(bytes.fromhex('c0048530 20204eda c1e6'))
        self.assertEqual(len(insns), 2)
        self.assertEqual([i['pc'] for i in insns], [0, 1])
        self.assertEqual([i['target'] for i in insns], [0x530, 0x4eda])


@unittest.skipUnless((ROOT / 'research/downloads/Zero2-v1.08.dat').exists(), 'Fetch pinned OEM image')
class StockAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.payloads = load_stock()

    def test_compressed_runtime_profile(self):
        records, regions, consumed = reconstruct(self.payloads[1])
        self.assertEqual(consumed, 950)
        self.assertEqual(records[1]['destination'] + records[1]['size'], 0x22b18)
        data = regions[0x20000]
        self.assertEqual(data[0x65a:0x66b].hex(), '10fb349b5f800000800010000010ff0000')
        self.assertEqual(data[0x66b:0x67f].hex(), '1810fb349b5f800000800010000013ff00000100')

    def test_memory_constraints_do_not_approve_placement(self):
        report = analyze_memory(self.payloads[1])
        self.assertFalse(report['placement_approved'])
        self.assertFalse(report['image_tail']['reclaimable'])
        self.assertFalse(report['ram']['unproven_interval']['free_ram_claimed'])
        self.assertIsNone(report['stack']['worst_case_bound'])
        self.assertEqual(report['image_tail']['size'], 508)
        self.assertEqual(report['stack']['main_plus_dispatcher_bytes'], 848)
        pools = report['ram']['pools']
        self.assertEqual(sum(p['count'] for p in pools), 26)
        for a, b in zip(pools, pools[1:]):
            self.assertEqual(a['end'], b['start'])
        self.assertEqual(pools[-1]['end'], 0x22aa8)

    def test_memory_audit_rejects_changed_constraints(self):
        for offset in (0xbc1c, 0x11c02, 0x11c04, 0x186c, 0xcf48, 0x210):
            changed = bytearray(self.payloads[1])
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                analyze_memory(changed)

    def test_constructor_defines_attribute_sizes(self):
        data = self.payloads[1]
        # Independently check the stock constants and transfer widths against
        # expected table fields (LE data vs BE radio instruction words).
        for pc, immediate, count, expected in [
            (0x207, 0x280002, 3, '020028'),
            (0x20c, 0x01280302, 4, '02032801'),
            (0x21f, 0x02290202, 8, '0202290200000000')]:
            word, transfer = struct.unpack_from('>2I', data, 0xda74 + pc * 4)
            self.assertEqual(word, (11 << 27) | immediate)
            self.assertEqual(decode(transfer), ('istore', f'{count}, contw', None))
            self.assertEqual(immediate.to_bytes(count, 'little').hex(), expected)

    def test_command_09_completion_route(self):
        data = self.payloads[1]

        def switch_target(table, index):
            count = data[table]
            entry = min(index, count)
            return table + data[table + 1 + entry] * 2

        def branch_target(offset):
            word = struct.unpack_from('<H', data, offset)[0]
            self.assertEqual(word >> 11, 0x1c)  # Thumb unconditional B
            immediate = word & 0x7ff
            if immediate & 0x400:
                immediate -= 0x800
            return offset + 4 + immediate * 2

        # The stock __ARM_common_switch8 helper uses byte offsets * 2.
        self.assertEqual(branch_target(switch_target(0xe3e, 6)), 0x10ca)
        self.assertEqual(branch_target(switch_target(0x10e6, 9)), 0x1336)
        self.assertEqual(data[0x133c:0x1344].hex(), '4078002803d10621')
        # Application dispatcher increments opcode before this separate switch.
        self.assertEqual(branch_target(switch_target(0x188a, 2 + 1)), 0x1ad2)
        self.assertEqual(branch_target(switch_target(0x188a, 5 + 1)), 0x1b2c)
        self.assertEqual(switch_target(0x188a, 8 + 1), 0x18e8)


if __name__ == '__main__':
    unittest.main()
