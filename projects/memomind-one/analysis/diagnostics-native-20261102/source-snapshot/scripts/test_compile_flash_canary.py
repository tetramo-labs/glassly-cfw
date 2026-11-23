"""Optional one-shot worker profile requires the read-only prerequisite chain."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from compile_memomind_graphics import compile_graphics
ROOT=Path(__file__).resolve().parents[1]
PIN='c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992'
class CanaryBuildTests(unittest.TestCase):
 def test_requires_full_store_reader_without_creating_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'no-build'
   with self.assertRaisesRegex(ValueError,'requires the full-store-reader'):
    compile_graphics(out,scene_session=True,input_observer=True,flash_reader=True,external_tail_reader=True,storage_diagnostics=True,flash_canary=True)
   self.assertFalse(out.exists())
 def test_pinned_actual_build_and_registry_contract(self):
  directory=ROOT/'runtime/build/flash-canary-004';b=json.loads((directory/'build.json').read_text())
  self.assertEqual(hashlib.sha256((directory/'graphics.bin').read_bytes()).hexdigest(),PIN);self.assertEqual(b['blob_sha256'],PIN);self.assertEqual(b['blob_bytes'],59584)
  self.assertTrue(b['flash_canary'] and b['full_store_reader'] and b['storage_diagnostics'])
  self.assertEqual(b['undefined_symbols'],[]);self.assertEqual(b['nonempty_writable_sections'],[]);self.assertIn('-DMM_FLASH_CANARY=1',b['flags'])
  for name in ('glassly_flash_canary_entry','glassly_flash_canary_command_entry','glassly_flash_canary_worker','glassly_canary_layout_valid','mm_flash_native_read','mm_flash_native_program','mm_flash_native_erase'):self.assertIn(name,b['symbols'])
  self.assertEqual(b['entry_address'],'0x0439bea0');self.assertEqual(b['display_gate_address'],'0x0439bee0')
if __name__=='__main__':unittest.main()
