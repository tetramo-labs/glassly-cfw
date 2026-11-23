"""Graphics uses exact profile reproduction and the existing modified-OTA rules."""
import copy
from pathlib import Path
import unittest

from build_memomind_graphics import construct_graphics, DISPLACED_LOAD
from memomind_flasher import validate_image

SOURCE=Path(__file__).resolve().parents[1]/'captures/firmware/ota-1.0.3.127-glassly-text.bin'


@unittest.skipUnless(SOURCE.exists(),'Verified text OTA required')
class GraphicsEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SOURCE.read_bytes()
        cls.blob=bytes(64)+DISPLACED_LOAD+bytes(12) # non-executable container fixture
        cls.image,cls.manifest,_=construct_graphics(cls.source,cls.blob)

    def test_exact_reproduced_graphics_is_modified_image(self):
        report,modified=validate_image(self.image,stock_source=self.source,
                                      runtime_manifest=self.manifest,runtime_blob=self.blob)
        self.assertTrue(modified)
        self.assertTrue(report['runtime_verification']['only_two_pinned_prefix_hook_ranges_changed'])

    def test_graphics_cannot_be_admitted_with_other_blob_or_profile(self):
        for manifest,blob in [(self.manifest,self.blob[:-1]+b'\x01'),
                              ({**self.manifest,'format':'unrecognized-profile'},self.blob)]:
            with self.assertRaises(ValueError):
                validate_image(self.image,stock_source=self.source,runtime_manifest=manifest,runtime_blob=blob)
        bad=copy.deepcopy(self.manifest);bad['hooks'][1]['target']+=2
        with self.assertRaises(ValueError):
            validate_image(self.image,stock_source=self.source,runtime_manifest=bad,runtime_blob=self.blob)
