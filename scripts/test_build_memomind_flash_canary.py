import copy
from pathlib import Path
import unittest

from build_memomind_exclusive_storage import construct_exclusive_storage
from build_memomind_flash_canary import construct_canary, verify_canary, REGISTRY_PATCHES
from build_memomind_graphics import BODY_BASE
from memomind_flasher import validate_image
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]


class CanaryConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        cls.blob = (ROOT / 'runtime/build/flash-canary-004/graphics.bin').read_bytes()
        cls.image, cls.manifest, cls.proof = construct_canary(cls.source, cls.blob)

    def test_only_registry_edits_added_to_exact_owner_gates(self):
        base, _, _ = construct_exclusive_storage(self.source, self.blob)
        _, before = unpack_ota(base)
        _, after = unpack_ota(self.image)
        allowed = {a - BODY_BASE + i for a, *_ in REGISTRY_PATCHES for i in range(4)}
        changed = {i for i,(a,b) in enumerate(zip(before[3]['raw'][32:],after[3]['raw'][32:])) if a!=b}
        self.assertTrue(changed and changed <= allowed)
        self.assertEqual(changed, set(self.proof['registry_changed_body_offsets']))
        for index in (0,1,2,4,5,6):
            self.assertEqual(before[index]['raw'], after[index]['raw'])
            self.assertEqual(before[index]['packed'], after[index]['packed'])

    def test_exact_manifest_rebuild_is_eligible_modified_image(self):
        rebuilt, proof = verify_canary(self.source, self.blob, self.manifest)
        self.assertEqual(rebuilt, self.image)
        self.assertEqual(proof, self.proof)
        report, modified = validate_image(self.image, stock_source=self.source,
                                          runtime_manifest=self.manifest, runtime_blob=self.blob)
        self.assertTrue(modified)
        self.assertEqual(report['runtime_verification']['registry_edit_span_bytes'], 12)
        self.assertTrue(self.manifest['native_writer_enabled'])
        self.assertFalse(self.manifest['general_mutable_store_enabled'])

    def test_manifest_cannot_move_canary_heap_or_remove_gate(self):
        for kind in ('canary', 'heap', 'gate'):
            manifest = copy.deepcopy(self.manifest)
            if kind == 'canary': manifest['canary']['sector_start'] -= 4096
            elif kind == 'heap': manifest['private_ram']['native_heap_start'] -= 256
            else: manifest['owner_gate_base_manifest']['edits'].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_image(self.image, stock_source=self.source,
                               runtime_manifest=manifest, runtime_blob=self.blob)

    def test_noncanary_profile_or_mutated_blob_rejected(self):
        old = (ROOT / 'runtime/build/full-store-read-001/graphics.bin').read_bytes()
        with self.assertRaises(ValueError): construct_canary(self.source, old)
        changed = self.blob[:-1] + bytes([self.blob[-1] ^ 1])
        with self.assertRaises(ValueError):
            validate_image(self.image, stock_source=self.source,
                           runtime_manifest=self.manifest, runtime_blob=changed)


if __name__ == '__main__':
    unittest.main()
