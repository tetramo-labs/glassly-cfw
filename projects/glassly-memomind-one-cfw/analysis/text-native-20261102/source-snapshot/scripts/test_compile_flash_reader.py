"""Optional-profile contract: require both prerequisites and preserve old images."""
import json,unittest
from pathlib import Path
from compile_memomind_graphics import compile_graphics,inspect_elf
ROOT=Path(__file__).resolve().parents[1]
class FlashProfileTests(unittest.TestCase):
 def test_require_both_prerequisites_before_any_output(self):
  for scene,inputs in ((False,False),(True,False),(False,True)):
   with self.subTest(scene=scene,inputs=inputs),self.assertRaisesRegex(ValueError,'requires scene-session and input-observer'):
    compile_graphics(ROOT/'unused-flash-missing-prerequisite',scene_session=scene,input_observer=inputs,flash_reader=True)
  self.assertFalse((ROOT/'unused-flash-missing-prerequisite').exists())
 def test_separate_fixture_cannot_enable_reader(self):
  with self.assertRaisesRegex(ValueError,'separate build profiles'):
   compile_graphics(ROOT/'unused-flash-missing-prerequisite',gate_fixture=True,scene_session=True,input_observer=True,flash_reader=True)
 def test_pinned_actual_flash_build_retains_only_read_helper(self):
  b=ROOT/'runtime/build/flash-read-001';r=json.loads((b/'build.json').read_text());self.assertTrue(r['flash_reader']);self.assertEqual(r['flash_reader_native'],'0x04329ad8')
  self.assertEqual(r['blob_sha256'],'d162d7c2f93ac57618f7756260e2b9c945313c160e6874517f98a8202777ca1b')
  self.assertTrue({'glassly_flash_read_command','glassly_flash_read_native'}<=set(r['symbols']))
  self.assertEqual(r['nonempty_writable_sections'],[]);self.assertEqual(r['undefined_symbols'],[])
  self.assertEqual(inspect_elf((b/'graphics.elf').read_bytes())[0]['file_bytes'],50880)
 def test_default_profiles_byte_identity(self):
  expected={'graphics':'08d478321f5340d06eab0f7007a49741a1ee7b1d8a3f716534221672ceac0b39','scene':'cd849a72ecd662a79327d01f792ddbe6b09cd5d7a2a683aa05440301dced2bbd','input':'3f8e637dff1f9da760b8842d1041eb88579cabc1b864bb5605d21bb9205167b4'}
  for name,want in expected.items():
   r=json.loads((ROOT/f'runtime/build/flash-unchanged-{name}-001/build.json').read_text());self.assertFalse(r['flash_reader']);self.assertEqual(r['blob_sha256'],want)
if __name__=='__main__':unittest.main()
