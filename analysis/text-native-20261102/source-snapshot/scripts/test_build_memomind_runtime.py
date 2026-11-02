import copy
from pathlib import Path
import unittest

from build_memomind_runtime import (construct_runtime, verify_runtime, address_pair,
                                   BODY_BASE, HOOK_ADDRESS, HOOK_BEFORE, ENTRY)
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin'
BLOB = ROOT/'runtime/build/probe-003/probe.bin'


@unittest.skipUnless(SOURCE.exists() and BLOB.exists(), 'Local text OTA and compiled probe are required')
class RuntimeConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.blob = SOURCE.read_bytes(), BLOB.read_bytes()
        cls.output, cls.manifest, cls.proof = construct_runtime(cls.source, cls.blob)

    def test_exact_prefix_edit_append_and_other_components(self):
        _, old = unpack_ota(self.source)
        _, new = unpack_ota(self.output)
        before, after = old[3]['raw'][32:], new[3]['raw'][32:]
        off = HOOK_ADDRESS-BODY_BASE
        self.assertEqual(before[off:off+8], HOOK_BEFORE)
        self.assertEqual(after[:off], before[:off])
        self.assertEqual(after[off:off+8], address_pair(ENTRY))
        self.assertEqual(after[off+8:len(before)], before[off+8:])
        self.assertEqual(after[len(before):], bytes(8)+self.blob)
        self.assertIn(b'Glassly firmware ready\0', after)
        for i in (1, 2, 4, 5, 6):
            self.assertEqual(new[i]['packed'], old[i]['packed'])
        self.assertTrue(self.proof['callback_store_preserved'])

    def test_reproduction_and_manifest_tampering(self):
        output, _ = verify_runtime(self.source, self.blob, self.manifest)
        self.assertEqual(output, self.output)
        for key in self.manifest:
            bad = copy.deepcopy(self.manifest)
            bad[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_runtime(self.source, self.blob, bad)

    def test_unknown_source_and_blob_bounds(self):
        with self.assertRaisesRegex(ValueError, 'exact visually verified'):
            construct_runtime(self.source[:-1], self.blob)
        for blob in (b'', bytes(1), bytes(17), bytes(4112)):
            with self.subTest(size=len(blob)), self.assertRaises(ValueError):
                construct_runtime(self.source, blob)

    def test_instruction_pair_decodes_expected_register_and_signed_low(self):
        import struct
        for address in (ENTRY, 0x042e4680):
            lui, addi = struct.unpack('<II', address_pair(address))
            self.assertEqual(lui & 0xfff, (15<<7)|0x37)
            self.assertEqual(addi & 0xfffff, (15<<15)|(15<<7)|0x13)
            low = addi >> 20
            if low & 0x800:
                low -= 4096
            self.assertEqual((lui & 0xfffff000)+low, address)


if __name__ == '__main__':
    unittest.main()
