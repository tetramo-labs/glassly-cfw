import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from firmware_image import load_crypto, load_stock, parse_sections, unpack
from radio_config import parse_script, parse_attributes
from inspect_stock import inspect
from build_name_probe import build as build_name_probe
from build_ble_probe import build as build_ble_probe
from build_notify_probe import build as build_notify_probe
from build_buttons_probe import build as build_buttons_probe, HOOKS


class ContainerTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / 'research/downloads/Zero2-v1.08.dat').exists(), 'Fetch pinned OEM image')
    def test_buttons_image_preserves_extent_startup_and_other_section(self):
        package, payload, report = build_buttons_probe()
        original_package, baseline, _ = build_ble_probe()
        self.assertLessEqual(report['tail_used_bytes'], 508)
        allowed = set(range(0x11c04, 0x11c04 + report['tail_used_bytes']))
        for offset, old in HOOKS.items():
            allowed.update(range(offset, offset+len(old)))
        changed = {i for i, (a,b) in enumerate(zip(payload,baseline)) if a != b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(payload), len(baseline))
        self.assertEqual(len(package), len(original_package))
        self.assertEqual(package[:0xc81c], original_package[:0xc81c])
        self.assertEqual(payload[0x1182c:0x11c04], baseline[0x1182c:0x11c04])
        self.assertEqual(report['tail_used_bytes'], 408)
        self.assertEqual(report['led_hooks'], ['0xc304', '0xc354', '0xc5ee', '0xc62e'])
        self.assertEqual(report['package_sha256'], '007ca4b94e765ba20bfeb7aaaf7728c14a741b6bac821d74932084b8536334a8')
        self.assertEqual(report['plaintext_sha256'], '9c93ce2bbf3bba0a4e41e7505e65b4c0deeedb082668ad384e8653aad3333528')
        flasher = (ROOT / 'tools/flash_zero2.c').read_text()
        for pinned in (report['package_sha256'], report['plaintext_sha256'],
                       report['previous_buttons_plaintext_sha256']):
            self.assertIn(pinned, flasher)

    @unittest.skipUnless((ROOT / 'research/downloads/Zero2-v1.08.dat').exists(), 'Fetch pinned OEM image')
    def test_notification_probe_changes_only_two_calls_and_bounded_tail(self):
        package, payload, report = build_notify_probe()
        baseline_package, baseline, _ = build_ble_probe()
        changed = {i for i, pair in enumerate(zip(payload, baseline)) if pair[0] != pair[1]}
        allowed = set(range(0x1918, 0x191c)) | set(range(0x3e36, 0x3e3a)) | set(range(0x11c04, 0x11ce0))
        self.assertTrue(changed <= allowed)
        self.assertEqual(package[:0xc81c], baseline_package[:0xc81c])
        self.assertEqual(len(payload), len(baseline))
        self.assertEqual(report['package_sha256'], '3a92dd60565e136a810fd0dc0148418c7b13cdb678eae66a5d5a8e2634369ed3')
        self.assertEqual(report['plaintext_sha256'], '940d562d4552a35d70fa25538ef452708cd1fbed6e930eeb43d8eae720373aa5')
        self.assertEqual(payload[0x11ce0:], baseline[0x11ce0:])

    @unittest.skipUnless((ROOT / 'research/downloads/Zero2-v1.08.dat').exists(), 'Fetch pinned OEM image')
    def test_ble_probe_changes_only_visibility_immediate_from_verified_name_image(self):
        package, payload, report = build_ble_probe()
        name_package, name_payload, _ = build_name_probe()
        self.assertEqual(len(payload), 73216)
        self.assertEqual(len(package), len(name_package))
        self.assertEqual([i for i, pair in enumerate(zip(payload, name_payload)) if pair[0] != pair[1]], [0x2310])
        self.assertEqual(payload[0x2310:0x2312], bytes.fromhex('0126'))
        self.assertEqual(report['package_sha256'], 'c51e350561aa51130b552efbaa64b3b5c2547731947001a0255ac36e60f43e59')
        self.assertEqual(report['plaintext_sha256'], '2c86e745cfadb4df8692c58bb1747bd9e957ecfc999f6501cd6450cd2b83fe22')
        self.assertEqual(package[:0xc81c], name_package[:0xc81c])

    def setUp(self):
        self.crypto = load_crypto()
        self.payload = bytes(range(256)) * 2
        self.image = self.crypto.build_section(self.payload, self.crypto.CIPHERS["gd32"], 108)

    def test_two_different_ciphers(self):
        second = self.crypto.build_section(self.payload, self.crypto.CIPHERS["yichip"], 108, pid=0x9018)
        sections, payloads = unpack(self.image + second, ["gd32", "yichip"])
        self.assertEqual(payloads, [self.payload, self.payload])
        self.assertEqual(sections[1]["pid"], 0x9018)

    def test_every_truncation_rejected(self):
        for length in range(len(self.image)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse_sections(self.image[:length])

    def test_trailing_bytes_rejected(self):
        for tail in (b"\0", bytes(28), bytes(512)):
            with self.assertRaises(ValueError):
                parse_sections(self.image + tail)

    def test_invalid_payload_lengths(self):
        for size in (0, 1, 511, 513, 1024, 0xffffffff):
            image = bytearray(self.image)
            struct.pack_into("<I", image, 8, size)
            with self.assertRaises(ValueError):
                parse_sections(image)

    def test_unknown_reserved_header_rejected(self):
        for offset in range(16, 28):
            image = bytearray(self.image); image[offset] = 1
            with self.assertRaises(ValueError):
                parse_sections(image)

    def test_cipher_schedule_limit(self):
        raw = struct.pack("<4I", 108, 0x8003400, 131584, 0) + bytes(12 + 131584)
        with self.assertRaisesRegex(ValueError, "key schedule"):
            unpack(raw, ["gd32"])

    def test_cipher_count(self):
        for ciphers in ([], ["gd32", "yichip"]):
            with self.assertRaises(ValueError):
                unpack(self.image, ciphers)

    def test_yichip_schedule_wrap(self):
        payload = bytes(range(256)) * 514
        raw = self.crypto.build_section(payload, self.crypto.CIPHERS["yichip"], 108)
        _, extracted = unpack(raw, ["yichip"])
        self.assertEqual(extracted, [payload])

    def test_roundtrip_is_not_authentication(self):
        modified = bytearray(self.image); modified[100] ^= 1
        _, extracted = unpack(modified, ["gd32"])
        self.assertNotEqual(extracted, [self.payload])


class RadioTests(unittest.TestCase):
    def test_microcode_and_write_records(self):
        image = bytes.fromhex("0002 aa55 0200 1234 aa55 0100 7549 56 0000")
        records, size = parse_script(image, 0)
        self.assertEqual(size, 15)
        self.assertIsNone(records[0]["address"])
        self.assertEqual(records[0]["payload"], b"\x12\x34")
        self.assertEqual(records[1]["address"], 0xc4975)
        self.assertEqual(records[1]["payload"], b"\x56")

    def test_script_truncation(self):
        for image in (b"", bytes.fromhex("0002 aa55"), bytes.fromhex("0002 aa55 1000 12")):
            with self.assertRaises(ValueError):
                parse_script(image, 0)

    def test_attributes(self):
        data = bytes.fromhex("0100 02 0028 02 0018 0200 02 0328 01 10 0000")
        attributes = parse_attributes(data)
        self.assertEqual([a["handle"] for a in attributes], [1, 2])
        self.assertEqual(attributes[1]["value_hex"], "10")

    def test_attributes_reject_corruption(self):
        for data in (b"", bytes.fromhex("0100 03"), bytes.fromhex("0100 02 0028 02 00"),
                     bytes.fromhex("0100 02 0028 00 0100 02 0028 00 0000")):
            with self.assertRaises(ValueError):
                parse_attributes(data)


class StockTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "research/downloads/Zero2-v1.08.dat").exists(), "Fetch pinned stock to run OEM checks")
    def test_pinned_stock_and_evidence(self):
        raw, sections, payloads = load_stock()
        self.assertEqual(len(raw), 124472)
        self.assertEqual([s["payload_len"] for s in sections], [51200, 73216])
        self.assertEqual(len(payloads), 2)
        report, _ = inspect()
        self.assertEqual(len(report["radio_script"]["records"]), 70)
        self.assertEqual(len(report["radio_attribute_table"]["attributes"]), 18)
        expected = json.loads((ROOT / "docs/evidence/stock-v108.json").read_text())
        self.assertEqual(report, expected)


if __name__ == "__main__":
    unittest.main()
