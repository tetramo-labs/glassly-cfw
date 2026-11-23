import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import build_memomind_storage as S
from build_memomind_graphics import construct_graphics, BODY_BASE
from memomind_flasher import validate_image
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]


class StorageConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        cls.blob = (ROOT / 'runtime/build/external-read-001/graphics.bin').read_bytes()
        cls.image, cls.manifest, cls.proof = S.construct_storage(cls.source, cls.blob)

    def test_exact_eleven_witnesses_and_other_components_unchanged(self):
        base, _, _ = construct_graphics(self.source, self.blob)
        _, original = unpack_ota(base)
        _, result = unpack_ota(self.image)
        allowed = set()
        for address, before, after, _ in S.PATCHES:
            offset = address - BODY_BASE
            self.assertEqual(original[3]['raw'][32 + offset:36 + offset], bytes.fromhex(before))
            self.assertEqual(result[3]['raw'][32 + offset:36 + offset], bytes.fromhex(after))
            allowed.update(range(offset, offset + 4))
        self.assertEqual(len(allowed), 44)
        diff = {i for i, (a, b) in enumerate(zip(original[3]['raw'][32:], result[3]['raw'][32:])) if a != b}
        self.assertTrue(diff and diff <= allowed)
        self.assertEqual(diff, set(self.proof['changed_body_byte_offsets']))
        for i in (0, 1, 2, 4, 5, 6):
            self.assertEqual(result[i]['raw'], original[i]['raw'])
            self.assertEqual(result[i]['packed'], original[i]['packed'])

    def test_manifest_reproduces_and_has_no_live_grant(self):
        rebuilt, proof = S.verify_storage(self.source, self.blob, self.manifest)
        self.assertEqual(rebuilt, self.image)
        self.assertEqual(proof, self.proof)
        self.assertFalse(self.manifest['live_flashing_enabled'])
        self.assertEqual(self.manifest['reservation']['physical_start'], 0x700000)
        self.assertEqual(self.manifest['reservation']['native_capacity'], 0x200000)
        self.assertEqual(self.manifest['reservation']['reserved_badmap_slice'], [64, 96])

    def test_manifest_changes_cannot_enable_or_move_reservation(self):
        for change in ('live_flashing_enabled', 'reservation', 'extra'):
            manifest = copy.deepcopy(self.manifest)
            if change == 'reservation': manifest[change]['physical_start'] -= 4096
            else: manifest[change] = True
            with self.assertRaises(ValueError):
                S.verify_storage(self.source, self.blob, manifest)

    def test_wrong_source_fails(self):
        with self.assertRaises(ValueError):
            S.construct_storage(bytes([self.source[0] ^ 1]) + self.source[1:], self.blob)

    def test_witness_overlap_and_unbounded_edit_fail(self):
        first = S.PATCHES[0]
        cases = [((first[0], '00000000', first[2], first[3]), *S.PATCHES[1:]),
                 (first, first, *S.PATCHES[2:]),
                 ((BODY_BASE - 4, first[1], first[2], first[3]), *S.PATCHES[1:]),
                 ((first[0], '00', '01', first[3]), *S.PATCHES[1:])]
        for edits in cases:
            with patch.object(S, 'PATCHES', edits), self.assertRaises(ValueError):
                S.construct_storage(self.source, self.blob)

    def test_live_flasher_rejects_unregistered_storage_profile(self):
        with self.assertRaises(ValueError):
            validate_image(self.image, stock_source=self.source,
                           runtime_manifest=self.manifest, runtime_blob=self.blob)


if __name__ == '__main__':
    unittest.main()
