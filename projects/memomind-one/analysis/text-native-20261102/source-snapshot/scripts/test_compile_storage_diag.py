import hashlib,json,unittest
from pathlib import Path
from compile_memomind_graphics import compile_graphics
ROOT=Path(__file__).resolve().parents[1]
class StorageDiagnosticBuildTests(unittest.TestCase):
    def test_explicit_external_profile_required(self):
        out=ROOT/'unused-storage-diagnostic-prerequisite'
        with self.assertRaisesRegex(ValueError,'requires the external-tail-reader'):
            compile_graphics(out,scene_session=True,input_observer=True,flash_reader=True,storage_diagnostics=True)
        self.assertFalse(out.exists())
    def test_actual_artifact_has_fixed_read_only_profile(self):
        directory=ROOT/'runtime/build/storage-diag-001';build=json.loads((directory/'build.json').read_text())
        digest=hashlib.sha256((directory/'graphics.bin').read_bytes()).hexdigest()
        self.assertEqual(digest,'265f8837b2b939930434253f7be63a1155190fef701c57d8c123d482a66725eb')
        self.assertEqual(build['blob_sha256'],digest);self.assertEqual(build['blob_bytes'],54064)
        self.assertTrue(build['storage_diagnostics'] and build['external_tail_reader'] and build['flash_reader'])
        self.assertEqual(build['undefined_symbols'],[]);self.assertEqual(build['nonempty_writable_sections'],[])
        self.assertIn('glassly_storage_snapshot',build['symbols']);self.assertIn('glassly_storage_badmap_read',build['symbols'])
        self.assertIn('-DMM_STORAGE_DIAGNOSTICS=1',build['flags'])
if __name__=='__main__':unittest.main()
