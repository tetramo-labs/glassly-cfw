"""Malformed-profile regression checks; no firmware or device is required."""
import struct
import unittest
from pathlib import Path
from inspect_ananke import characteristics, inspect, parse_profile


def record(handle, uuid, value=b'', flags=2):
    return struct.pack('<4H', 8 + len(value), flags, handle, uuid) + value


def profile():
    return (record(1, 0x2800, b'\x40\xae') +
            record(2, 0x2803, struct.pack('<BHH', 0x10, 3, 0xae42)) +
            record(3, 0xae42, flags=0x10) +
            record(4, 0x2902, b'\0\0', flags=0x10a) + b'\0\0')


class ProfileTests(unittest.TestCase):
    def test_unaligned_profile_and_descriptor_ownership(self):
        data = b'X' + profile()
        rows, end = parse_profile(data, 1)
        self.assertEqual(end, len(data))
        char, = characteristics(rows)
        self.assertEqual((char['service_uuid'], char['uuid'], char['value_handle'], char['ccc_handle']),
                         (0xae40, 0xae42, 3, 4))

    def test_every_truncation_rejected(self):
        data = profile()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse_profile(data[:length], 0)

    def test_handle_reversal_and_uuid128_rejected(self):
        for data in (record(1, 0x2800, b'\x40\xae') + record(1, 0xae42) + b'\0\0',
                     record(1, 0x2800, b'\x40\xae', flags=0x202) + b'\0\0'):
            with self.assertRaises(ValueError):
                parse_profile(data, 0)

    def test_declaration_value_mismatch_rejected(self):
        rows, _ = parse_profile(profile(), 0)
        rows[2]['uuid'] = 0xae02
        with self.assertRaisesRegex(ValueError, 'declaration/value mismatch'):
            characteristics(rows)

    def test_missing_duplicate_and_orphan_ccc_rejected(self):
        rows, _ = parse_profile(profile(), 0)
        for malformed in (rows[:-1], rows + [rows[-1]], [rows[0], rows[-1]]):
            with self.assertRaises(ValueError):
                characteristics(malformed)

    def test_other_firmware_rejected(self):
        with self.assertRaisesRegex(ValueError, 'size/hash'):
            inspect(profile())

    def test_pinned_local_oem_when_available(self):
        app = Path(__file__).parent / 'oem-unpacked/IG05_V0900.ufw/files/app.bin'
        if not app.exists():
            self.skipTest('OEM firmware remains local')
        report = inspect(app.read_bytes())
        self.assertEqual(report['profile']['file_offset'], 0x4a69f)
        self.assertEqual(len(report['profile']['attributes']), 91)
        self.assertEqual(report['vendor_characteristics'][1]['ccc_handle'], 0x55)


if __name__ == '__main__':
    unittest.main()
