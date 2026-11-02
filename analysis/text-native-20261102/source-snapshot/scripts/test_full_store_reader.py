"""Full3MiB explicit read-only profile: prerequisites, framed client and capture."""
import hashlib,json,struct,tempfile,unittest,subprocess,sys
from pathlib import Path
from compile_memomind_graphics import compile_graphics
from capture_memomind_flash import acquire
from memomind_flash_read import (FlashReadClient,FlashReadProtocolError,PROFILES,
                                FULL_STORE_PROFILE,PROFILE,EXTERNAL_PROFILE,DIAGNOSTIC_PROFILE,CANARY_PROFILE)
from memomind_storage_diag import StorageDiagnosticClient
from test_memomind_flash_read import WireFake
from test_memomind_storage_diag import Wire as DiagnosticWire
ROOT=Path(__file__).resolve().parents[1]
PIN='83290f4c3d300b3f479bcd60865ffb5cc29b55e5887e635fac6f0d0d208d352b'
def full_identity(reply):
 if 'ranges' in reply:
  reply['profile']=FULL_STORE_PROFILE
  reply['ranges']=[dict(device=d,start=b,end=e) for d,b,e in PROFILES[FULL_STORE_PROFILE].values()]
 return reply
class FullStoreReaderTests(unittest.TestCase):
 def test_diagnostic_capture_cli_limits_profiles(self):
  result=subprocess.run([sys.executable,str(ROOT/'scripts/capture_memomind_storage_diag.py'),'--help'],text=True,capture_output=True,check=True)
  self.assertIn('{'+DIAGNOSTIC_PROFILE+','+FULL_STORE_PROFILE+','+CANARY_PROFILE+'}',result.stdout)
  self.assertNotIn(EXTERNAL_PROFILE,result.stdout)
 def test_compile_requires_diagnostics_without_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'build'
   with self.assertRaisesRegex(ValueError,'requires the storage-diagnostics'):
    compile_graphics(out,scene_session=True,input_observer=True,flash_reader=True,external_tail_reader=True,full_store_reader=True)
   self.assertFalse(out.exists())
 def test_pinned_actual_artifact(self):
  p=ROOT/'runtime/build/full-store-read-001';b=json.loads((p/'build.json').read_text())
  self.assertEqual(hashlib.sha256((p/'graphics.bin').read_bytes()).hexdigest(),PIN);self.assertEqual(b['blob_sha256'],PIN)
  self.assertEqual(b['blob_bytes'],54016);self.assertEqual(b['undefined_symbols'],[]);self.assertEqual(b['nonempty_writable_sections'],[])
  for name in ('full_store_reader','storage_diagnostics','external_tail_reader','flash_reader','input_observer','scene_session'):self.assertTrue(b[name])
  self.assertIn('-DMM_FULL_STORE_READ=1',b['flags']);self.assertEqual(b['flash_reader_native'],'0x04329ad8')
 def test_old_profiles_cannot_admit_middle_or_full_query(self):
  for profile in (PROFILE,EXTERNAL_PROFILE,DIAGNOSTIC_PROFILE):
   w=WireFake();c=FlashReadClient(w,profile=profile)
   with self.assertRaises(ValueError):c.read(1,0x600000)
   self.assertFalse(w.messages)
   w.edit=full_identity
   with self.assertRaises(FlashReadProtocolError):c.query()
 def test_full_profile_boundaries_and_no_invalid_wire_actions(self):
  w=WireFake();w.edit=full_identity;c=FlashReadClient(w,profile=FULL_STORE_PROFILE);c.query()
  for off in (0x500000,0x50ff00,0x510000,0x5fff00,0x600000,0x6fff00,0x700000,0x7fff00):
   for length in (1,256):self.assertEqual(len(c.read(1,off,length)),length)
  before=list(w.messages)
  for args in ((1,0x4fff00,256),(1,0x800000,1),(1,0x7fff00,257),(1,0xffffff00,256),(0,0x600000,256),(2,0x600000,256),(1,0x600001,1),(1,0x600000,0)):
   with self.assertRaises(ValueError):c.read(*args)
  self.assertEqual(w.messages,before)
 def test_full_capture_complete_contiguous_header_first(self):
  w=WireFake();w.edit=full_identity;c=FlashReadClient(w,profile=FULL_STORE_PROFILE)
  with tempfile.TemporaryDirectory() as tmp:
   rows=[];out=Path(tmp)
   result=acquire(c,['managed-store'],out,rows.append,expected_app_prefix=bytes(range(32)))
   raw=(out/'managed-store.bin').read_bytes();self.assertEqual(len(raw),3*1024*1024)
   self.assertEqual(raw,bytes((i+17)&255 for i in range(256))*12288)
   self.assertEqual(w.messages[1],struct.pack('<BBIH',1,0,0x1eb000,256))
   reads=[struct.unpack('<BBIH',x) for x in w.messages[2:]]
   self.assertEqual(reads,[(1,1,off,256) for off in range(0x500000,0x800000,256)])
   self.assertEqual(result['artifacts'][1]['sha256'],hashlib.sha256(raw).hexdigest())
   self.assertTrue(result['complete'] and result['app_header_verified']);self.assertEqual(result['flash_mutations'],0)
   self.assertEqual(sum(x['kind']=='chunk' for x in rows),12289)
 def test_diagnostics_explicit_profile_keeps_strict_pinning(self):
  for profile in (DIAGNOSTIC_PROFILE,FULL_STORE_PROFILE):
   w=DiagnosticWire();c=StorageDiagnosticClient(w,profile=profile)
   if profile==FULL_STORE_PROFILE:w.edit=full_identity
   c.query();c.topology();c.badmap();self.assertEqual(w.messages,[b'\0',b'\2',b'\3'])
  for profile in (PROFILE,EXTERNAL_PROFILE,'unknown'):
   w=DiagnosticWire()
   with self.assertRaises(ValueError):StorageDiagnosticClient(w,profile=profile)
   self.assertFalse(w.messages)
  w=DiagnosticWire();c=StorageDiagnosticClient(w,profile=FULL_STORE_PROFILE)
  with self.assertRaises(FlashReadProtocolError):c.query()
  self.assertEqual(w.messages,[b'\0'])
if __name__=='__main__':unittest.main()
