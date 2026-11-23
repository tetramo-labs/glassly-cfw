import hashlib
import json
from pathlib import Path
import unittest

from compile_memomind_graphics import compile_graphics

ROOT = Path(__file__).resolve().parents[1]


class ExternalReaderBuildTests(unittest.TestCase):
    def test_explicit_flash_reader_prerequisite(self):
        output = ROOT / 'unused-external-reader-prerequisite'
        with self.assertRaisesRegex(ValueError, 'requires the flash-reader'):
            compile_graphics(output, scene_session=True, input_observer=True, external_tail_reader=True)
        self.assertFalse(output.exists())

    def test_actual_profile_is_read_only_and_pinned(self):
        directory = ROOT / 'runtime/build/external-read-001'
        build = json.loads((directory / 'build.json').read_text())
        digest = hashlib.sha256((directory / 'graphics.bin').read_bytes()).hexdigest()
        self.assertEqual(digest, '6c317933ca7edef1375843375dceb18f94ef0efca93246076c92c023a56432bd')
        self.assertEqual(build['blob_sha256'], digest)
        self.assertTrue(build['external_tail_reader'] and build['flash_reader'])
        self.assertEqual(build['blob_bytes'], 50944)
        self.assertEqual(build['undefined_symbols'], [])
        self.assertEqual(build['nonempty_writable_sections'], [])
        self.assertEqual(build['flash_reader_native'], '0x04329ad8')
        self.assertIn('-DMM_EXTERNAL_TAIL_READ=1', build['flags'])


if __name__ == '__main__':
    unittest.main()
