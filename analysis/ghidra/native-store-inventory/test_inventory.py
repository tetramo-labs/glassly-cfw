#!/usr/bin/env python3
import json,struct,unittest,zlib
from pathlib import Path
from inventory import native_mount,inventory,entries_from_context,ROOT,COMMIT
HERE=Path(__file__).resolve().parent
RESULTS=[]
def entry(name=b'test',offset=0x2c0000,state=2,flags=1):
 b=bytearray(144);b[:len(name)]=name;b[64:96]=bytes(range(32))
 struct.pack_into('<7I',b,0x60,1,4096,0x100,offset,4096 if state==2 else 0,flags,state)
 return b

def snapshot(entries=(),generation=1,use=0,move=(0,0,0)):
 b=bytearray(0xff8);struct.pack_into('<12I',b,0,0x47534331,4,generation,0,use,0,0x300000,0x10000,*move,0)
 for i,e in enumerate(entries):b[48+i*144:48+(i+1)*144]=e
 struct.pack_into('<I',b,0xff0,zlib.crc32(b[:0xff0]));return b

def directory(snap,committed=True,journal=()):
 b=bytearray(b'\xff'*65536);b[:len(snap)]=snap
 if committed:struct.pack_into('<I',b,0x1ffc,COMMIT)
 for i,r in enumerate(journal):
  raw=struct.pack('<4I',*r);b[0xff8+i*24:0xff8+(i+1)*24]=raw+struct.pack('<2I',zlib.crc32(raw),COMMIT)
 return bytes(b)

class NativeInventoryTests(unittest.TestCase):
 def run_case(self,data,expected,**kw):
  r,c=native_mount(data,**kw);self.assertEqual(r['return_code'],expected);self.assertEqual(r['mutating_callbacks'],0)
  RESULTS.append({'scenario':self.id().split('.')[-1],'expected_return':expected,**r});return c
 def test_recorded_erased_both_captures(self):
  a=(ROOT/'captures/flash-read-runtime-20261031/metadata/plugin-directory.bin').read_bytes()
  b=(ROOT/'captures/flash-read-runtime-20261031/metadata-repeat/plugin-directory.bin').read_bytes()
  self.assertEqual(a,b);self.assertEqual(a,b'\xff'*65536);self.run_case(a,-1)
 def test_valid_empty_snapshot(self):
  c=self.run_case(directory(snapshot()),0);self.assertEqual(entries_from_context(c),[])
 def test_complete_protected_tail_overlap(self):
  c=self.run_case(directory(snapshot([entry()])),0);e=entries_from_context(c)[0]
  self.assertTrue(e['protected']);self.assertTrue(e['overlaps_last_256k']);self.assertEqual(e['relative_end_exclusive'],0x2c1000)
 def test_candidate_extent(self):
  c=self.run_case(directory(snapshot([entry(state=1)])),0);self.assertEqual(entries_from_context(c)[0]['state'],1)
 def test_successful_use_journal_replay(self):
  c=self.run_case(directory(snapshot([entry()]),journal=[(3,0,1,0)]),0)
  self.assertEqual(entries_from_context(c)[0]['use_counter'],1)
 def test_move_progress_journal_needs_recovery(self):
  self.run_case(directory(snapshot([entry()],move=(1,0x2b0000,0)),journal=[(2,0,4096,0)]),-6)
 def test_bad_committed_snapshot_is_not_ignored(self):
  d=bytearray(directory(snapshot()));d[0x30]^=1;self.run_case(bytes(d),-8)
 def test_newer_uncommitted_snapshot_needs_recovery(self):
  d=bytearray(directory(snapshot()));d[0x2000:0x2ff8]=snapshot(generation=2);self.run_case(bytes(d),-6)
 def test_invalid_committed_journal_crc(self):
  d=bytearray(directory(snapshot([entry()]),journal=[(3,0,1,0)]));d[0xff8+16]^=1;self.run_case(bytes(d),-8)
 def test_duplicate_complete_names(self):
  self.run_case(directory(snapshot([entry(),entry(offset=0x2d0000)])),-8)
 def test_badmap_overlap_rejects_complete_entry(self):
  bm=bytearray(96);bm[704//8]|=1<<(704%8)
  self.run_case(directory(snapshot([entry()])),-8,badmap=bytes(bm))
 def test_badmap_directory_sector_rejected(self):
  self.run_case(b'\xff'*65536,-3,badmap=b'\x01'+bytes(95))
 def test_capture_length_and_hash_guards(self):
  with self.assertRaises(ValueError):inventory(b'\xff')
  with self.assertRaises(ValueError):inventory(b'\xff'*65536,'0'*64)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeInventoryTests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 (HERE/'tests.json').write_text(json.dumps({'tests_run':result.testsRun,'successful':result.wasSuccessful(),'native_cases':RESULTS,'hardware_emulation':False,'badmap_is_mocked':True},indent=2)+'\n')
 raise SystemExit(not result.wasSuccessful())
