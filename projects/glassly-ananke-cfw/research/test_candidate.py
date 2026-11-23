"""Offline regression checks for the per-unit candidate builder."""
import unittest
import importlib.util
from build_candidate import (APP_BYTES, BASE, AREA_BYTES, BACKUP, EXTRACTED, ELF,
                             ROOT, ORIGIN, package, patch_application, read_elf,
                             call_target, encode_call, audit_listing)


@unittest.skipUnless(ELF.exists() and (BACKUP/'flash-pass1.bin').exists() and
                     (EXTRACTED/'jlfw.yaml').exists() and importlib.util.find_spec('yaml') and
                     importlib.util.find_spec('crcmod'),
                     'Candidate tests require preserved local artifacts and the analysis venv')
class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml
        cls.original = (BACKUP/'flash-pass1.bin').read_bytes()
        cls.installed = (EXTRACTED/'files/app.bin').read_bytes()
        cls.key = yaml.safe_load((EXTRACTED/'jlfw.yaml').read_text())['chip-key']
        cls.oem = (ROOT/'research/oem-unpacked/IG05_V0900.ufw/files/app.bin').read_bytes()
        cls.elf = ELF.read_bytes()
        cls.payload, cls.symbols = read_elf(cls.elf)

    def test_original_byte_exact_roundtrip(self):
        self.assertEqual(package(self.original, self.installed, self.key), self.original)

    def test_patch_preserves_ram_and_fixed_layout(self):
        app, patches = patch_application(self.oem, self.payload, self.symbols)
        self.assertEqual(len(app), APP_BYTES)
        self.assertEqual(len(patches), 8)
        self.assertEqual(app[0x1e37a5c-ORIGIN:0x1e37a60-ORIGIN], bytes.fromhex('43f08004'))
        self.assertEqual(app[0x4c42c:0x52af0], self.oem[0x4c42c:0x52af0])
        image = package(self.original, app, self.key)
        self.assertEqual(image[:BASE], self.original[:BASE])
        self.assertEqual(image[BASE+AREA_BYTES:], self.original[BASE+AREA_BYTES:])

    def test_reject_wrong_original(self):
        bad = bytearray(self.original); bad[-1] ^= 1
        with self.assertRaises(ValueError): package(bad, self.installed, self.key)

    def test_reject_wrong_key(self):
        with self.assertRaises(ValueError): package(self.original, self.installed, self.key ^ 1)

    def test_reject_wrong_oem(self):
        bad = bytearray(self.oem); bad[0] ^= 1
        with self.assertRaises(ValueError): patch_application(bad, self.payload, self.symbols)

    def test_reject_growth(self):
        with self.assertRaises(ValueError): package(self.original, self.installed+b'\0', self.key)
        with self.assertRaises(ValueError): patch_application(self.oem, bytes(APP_BYTES), self.symbols)

    def test_reject_truncated_or_wrong_elf(self):
        for blob in (self.elf[:40], self.elf[:-1], b'x'*len(self.elf)):
            with self.assertRaises(ValueError): read_elf(blob)

    def test_compiler_and_oem_call_encoding(self):
        # Independent bytes emitted by the official compiler, including PC wrap.
        self.assertEqual(call_target(0x1e52c3c, bytes.fromhex('8dea4376')), 0x18c6)
        self.assertEqual(call_target(0x1e3b5b6, bytes.fromhex('8eea8631')), 0x18c6)
        self.assertEqual(encode_call(0x1e52c58, 0x1e169d8), bytes.fromhex('beeabe1e'))
        with self.assertRaises(ValueError): encode_call(ORIGIN, ORIGIN+1)
        with self.assertRaises(ValueError): encode_call(ORIGIN, 0x18c6)

    def test_disassembly_matches_every_payload_byte(self):
        listing = ELF.with_suffix('.asm').read_text()
        audit = audit_listing(self.payload, self.symbols, listing)
        self.assertTrue(audit['all_payload_bytes_disassembled'])
        bad = bytearray(self.payload); bad[0] ^= 1
        with self.assertRaises(ValueError): audit_listing(bad, self.symbols, listing)
        with self.assertRaises(ValueError): audit_listing(self.payload, self.symbols, '')


if __name__ == '__main__':
    unittest.main()
