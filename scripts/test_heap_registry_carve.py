from pathlib import Path
import unittest

from build_memomind_flash_canary import apply_registry_carve, REGISTRY_PATCHES, REGISTRY_END, HEAP_END
from build_memomind_graphics import BODY_BASE

ROOT = Path(__file__).resolve().parents[1]


class HeapRegistryCarveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = (ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()

    def test_exact_twelve_byte_spans_and_unchanged_heap_end(self):
        changed, edits = apply_registry_carve(self.body)
        allowed = {a - BODY_BASE + i for a, *_ in REGISTRY_PATCHES for i in range(4)}
        diff = {i for i, (a, b) in enumerate(zip(self.body, changed)) if a != b}
        self.assertEqual(len(changed), len(self.body))
        self.assertEqual(len(allowed), 12)
        self.assertTrue(diff and diff <= allowed)
        self.assertEqual(len(edits), 3)
        offset = 0x04399550 - BODY_BASE
        start = int.from_bytes(changed[offset:offset + 4], 'little')
        size = int.from_bytes(changed[offset + 4:offset + 8], 'little')
        self.assertEqual((start, start + size), (REGISTRY_END, HEAP_END))
        self.assertEqual(changed[offset + 8:offset + 12], bytes.fromhex('02000000'))

    def test_each_witness_and_pool_flags_are_required(self):
        for address in [row[0] for row in REGISTRY_PATCHES] + [0x04399558]:
            body = bytearray(self.body)
            body[address - BODY_BASE] ^= 1
            with self.subTest(address=hex(address)), self.assertRaises(ValueError):
                apply_registry_carve(body)

    def test_already_carved_or_truncated_body_rejected(self):
        carved, _ = apply_registry_carve(self.body)
        for body in (carved, self.body[:0x04399550 - BODY_BASE + 3]):
            with self.assertRaises(ValueError):
                apply_registry_carve(body)


if __name__ == '__main__':
    unittest.main()
