import copy
from pathlib import Path
import unittest

import build_memomind_exclusive_storage as S
from build_memomind_graphics import BODY_BASE, construct_graphics
from memomind_flasher import validate_image
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]


class ExclusiveStorageConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        cls.blob = (ROOT / 'runtime/build/storage-diag-001/graphics.bin').read_bytes()
        cls.image, cls.manifest, cls.proof = S.construct_exclusive_storage(cls.source, cls.blob)

    def test_only_six_gates_change(self):
        base, _, _ = construct_graphics(self.source, self.blob)
        _, original = unpack_ota(base)
        _, final = unpack_ota(self.image)
        allowed = set()
        for address, before, after, _, _ in S.GATES:
            offset = address - BODY_BASE
            length = len(bytes.fromhex(before))
            self.assertEqual(original[3]['raw'][32 + offset:32 + offset + length], bytes.fromhex(before))
            self.assertEqual(final[3]['raw'][32 + offset:32 + offset + length], bytes.fromhex(after))
            allowed.update(range(offset, offset + length))
        self.assertEqual(len(allowed), 26)
        changed = {i for i, (a, b) in enumerate(zip(original[3]['raw'][32:], final[3]['raw'][32:])) if a != b}
        self.assertTrue(changed and changed <= allowed)
        self.assertEqual(changed, set(self.proof['changed_body_byte_offsets']))
        for i in (0, 1, 2, 4, 5, 6):
            self.assertEqual(final[i]['raw'], original[i]['raw'])
            self.assertEqual(final[i]['packed'], original[i]['packed'])

    def test_exact_manifest_and_explicit_scope(self):
        image, proof = S.verify_exclusive_storage(self.source, self.blob, self.manifest)
        self.assertEqual(image, self.image)
        self.assertEqual(proof, self.proof)
        self.assertEqual(self.manifest['proposed_storage']['bytes'], 3 * 1024 * 1024)
        for key in ('live_flashing_enabled', 'exclusive_ownership_proven',
                    'native_writer_enabled', 'stock_plugin_compatibility'):
            self.assertIs(self.manifest[key], False)

    def test_all_original_witnesses_required_and_hook_overlap_rejected(self):
        original = (ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
        for address, *_ in S.GATES:
            offset = address - BODY_BASE
            corrupt = bytearray(original)
            corrupt[offset] ^= 1
            with self.subTest(address=hex(address)):
                with self.assertRaises(ValueError):
                    S.apply_owner_gates(corrupt)
                with self.assertRaises(ValueError):
                    S.apply_owner_gates(original, [(offset, offset + 8)])

    def test_manifest_cannot_enable_writes(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['native_writer_enabled'] = True
        with self.assertRaises(ValueError):
            S.verify_exclusive_storage(self.source, self.blob, manifest)

    def test_live_flasher_rejects_offline_candidate(self):
        with self.assertRaises(ValueError):
            validate_image(self.image, stock_source=self.source,
                           runtime_manifest=self.manifest, runtime_blob=self.blob)


if __name__ == '__main__':
    unittest.main()
