"""Only the explicit full-reader/gated-owner profile enters modified OTA flow."""
import copy
from pathlib import Path
import unittest

from build_memomind_exclusive_storage import (
    construct_exclusive_reader, construct_exclusive_storage, READER_FORMAT)
from memomind_flasher import validate_image

ROOT = Path(__file__).resolve().parents[1]


class ExclusiveReaderEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        cls.blob = (ROOT / 'runtime/build/full-store-read-001/graphics.bin').read_bytes()
        cls.image, cls.manifest, _ = construct_exclusive_reader(cls.source, cls.blob)

    def test_exact_reproduced_profile_is_modified_ota(self):
        report, modified = validate_image(self.image, stock_source=self.source,
                                          runtime_manifest=self.manifest, runtime_blob=self.blob)
        self.assertTrue(modified)
        self.assertEqual(self.manifest['format'], READER_FORMAT)
        self.assertIs(self.manifest['native_writer_enabled'], False)
        self.assertIs(self.manifest['exclusive_ownership_proven'], False)
        self.assertEqual(report['runtime_verification']['additional_gate_sites'], 6)

    def test_old_profile_stays_offline_and_old_reader_cannot_be_promoted(self):
        old_blob = (ROOT / 'runtime/build/storage-diag-001/graphics.bin').read_bytes()
        with self.assertRaises(ValueError):
            construct_exclusive_reader(self.source, old_blob)
        image, manifest, _ = construct_exclusive_storage(self.source, self.blob)
        with self.assertRaises(ValueError):
            validate_image(image, stock_source=self.source, runtime_manifest=manifest, runtime_blob=self.blob)

    def test_manifest_cannot_move_region_enable_writer_or_remove_gate(self):
        for kind in ('region', 'writer', 'gate'):
            manifest = copy.deepcopy(self.manifest)
            if kind == 'region':
                manifest['proposed_storage']['physical_start'] -= 4096
            elif kind == 'writer':
                manifest['native_writer_enabled'] = True
            else:
                manifest['edits'].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_image(self.image, stock_source=self.source,
                               runtime_manifest=manifest, runtime_blob=self.blob)

    def test_changed_blob_or_image_is_rejected(self):
        for image, blob in ((self.image, self.blob[:-1] + bytes([self.blob[-1] ^ 1])),
                            (self.image[:-1] + bytes([self.image[-1] ^ 1]), self.blob)):
            with self.assertRaises((ValueError, RuntimeError)):
                validate_image(image, stock_source=self.source,
                               runtime_manifest=self.manifest, runtime_blob=blob)


if __name__ == '__main__':
    unittest.main()
