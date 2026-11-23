#!/usr/bin/env python3
"""Actual diagnostic RV32 code; fixed RAM values and firmware APIs are synthetic."""
import argparse,json,struct,unittest,zlib
from pathlib import Path
import flash_read_runtime_emulator_test as F
G=F.G
BUILD=F.ROOT/'runtime/build/storage-diag-001'
PINNED_SHA='265f8837b2b939930434253f7be63a1155190fef701c57d8c123d482a66725eb'
G.NATIVES.update({0x04235032:'badmap_get',0x042a9c84:'badmap_crc',0x042a9cca:'badmap_valid'})
def record():
 raw=bytearray(struct.pack('<4I',0x474d4231,1,0x01500000,0x00300000)+bytes(96));raw[80]=1;raw[111]=128
 return bytes(raw)+struct.pack('<I',zlib.crc32(raw))
SLOTS=((0x0201234c,1),(0x0201234d,1),(0x02012330,4),(0x02012334,4),
       (0x02012338,1),(0x02012339,1),(0x0205c8e0,1),(0x0205c8e4,4),
       (0x02012350,1),(0x020124d0,4),(0x020124d4,1),(0x020124d8,4),
       (0x020124dc,4),(0x0205c2ac,1),(0x0205c26c,4),(0x0205c270,4),
       (0x0205c274,4),(0x0205c278,4),(0x0205c27c,1),(0x02011e48,4),(0x02011e50,1))
KNOWN=(1,1,0x020107f0,0x02010898,1,1,1,0x851712ab,1,0x02010c6c,1,
       0x12345678,0x87654321,3,5,102,3,4,0,0xdeadbeef,255)
class DiagnosticMachine(F.FlashMachine):
 def __init__(self,values=KNOWN):
  super().__init__();assert self.build['storage_diagnostics']
  self.slot_reads=[];self.change=None
  self.record=record();self.kv_status=0;self.actual=116;self.kv_reads=0;self.crc_calls=0;self.valid_calls=0
  for page in sorted({a&~4095 for a,n in SLOTS}):self.uc.mem_map(page,4096,G.u.UC_PROT_READ)
  for (a,n),v in zip(SLOTS,values):self.uc.mem_write(a,int(v).to_bytes(n,'little'))
 def native(self,name,args):
  if name=='badmap_get':
   key,dst,capacity,actual=args[:4];assert (key,capacity)==(0x6009,116)
   assert self.read(dst,116)==bytes(116) and self.read(actual,4)==bytes(4)
   assert self.allocations[dst]['tag']=='owned' and self.allocations[dst]['size']==1024
   assert len(self.request_releases)==1;self.kv_reads+=1
   self.native_write(dst,self.record);self.native_write(actual,struct.pack('<I',self.actual));return self.kv_status&0xffffffff
  if name=='badmap_crc':self.crc_calls+=1;return zlib.crc32(self.read(args[0],112))
  if name=='badmap_valid':self.valid_calls+=1;return int(self.read(args[0],2)==bytes(2))
  return super().native(name,args)
 def region(self,address,size,writing=False):
  if not writing and (address,size) in SLOTS:return 'fixed-passive-slot'
  return super().region(address,size,writing)
 def memory_read(self,uc,access,address,size,value,userdata):
  if (address,size) in SLOTS:
   if self.change is not None and len(self.slot_reads)==len(SLOTS):
    a,n=SLOTS[self.change];raw=int.from_bytes(self.uc.mem_read(a,n),'little')^1;self.uc.mem_write(a,raw.to_bytes(n,'little'))
   self.slot_reads.append((address,size))
  return super().memory_read(uc,access,address,size,value,userdata)

class DiagnosticTests(unittest.TestCase):
 def test_single_record_and_native_default_are_distinct(self):
  m=DiagnosticMachine();reply,_=m.execute(b'\3');self.assertEqual(m.kv_reads,1);self.assertFalse(m.flash_calls or m.slot_reads)
  self.assertEqual(reply['recordState'],'present');self.assertEqual(reply['recordHex'],record().hex());self.assertEqual(reply['mapHex'],record()[16:112].hex())
  self.assertEqual((m.crc_calls,m.valid_calls),(1,1))
  m=DiagnosticMachine();m.kv_status=7;m.actual=0;reply,_=m.execute(b'\3');self.assertEqual(m.kv_reads,1)
  self.assertEqual(reply['recordState'],'absent');self.assertEqual(reply['mapHex'],'00'*96);self.assertEqual(reply['recordHex'],'');self.assertEqual((m.crc_calls,m.valid_calls),(0,0))
 def test_invalid_record_never_exposes_a_map(self):
  for byte in (0,4,8,12,16,80,111,112,115):
   m=DiagnosticMachine();raw=bytearray(m.record);raw[byte]^=1;m.record=bytes(raw);reply,_=m.execute(b'\3')
   self.assertEqual(reply['recordState'],'invalid');self.assertEqual(reply['mapHex'],'');self.assertEqual(reply['recordHex'],'');self.assertEqual(m.kv_reads,1)
  m=DiagnosticMachine();raw=bytearray(m.record);raw[16]=1;raw[112:]=struct.pack('<I',zlib.crc32(raw[:112]));m.record=bytes(raw);reply,_=m.execute(b'\3');self.assertEqual(reply['recordState'],'invalid');self.assertEqual(m.valid_calls,1)
  for n in (0,115,117,0xffffffff):
   m=DiagnosticMachine();m.actual=n;reply,_=m.execute(b'\3');self.assertEqual(reply['recordState'],'invalid');self.assertEqual((m.crc_calls,m.valid_calls),(0,0))
  for status in (2,4,13,-1):
   m=DiagnosticMachine();m.kv_status=status;m.actual=0;reply,_=m.execute(b'\3');self.assertEqual(reply['recordState'],'unavailable');self.assertEqual(reply['kvStatus'],status&0xffffffff);self.assertEqual(reply['mapHex'],'');self.assertEqual(m.kv_reads,1)
 def test_fixed_reads_and_normalized_snapshot(self):
  m=DiagnosticMachine();reply,_=m.execute(b'\2');self.assertEqual(m.slot_reads,list(SLOTS)*2);self.assertFalse(m.flash_calls)
  self.assertEqual(reply['diagnostic'],'topology');self.assertEqual(reply['consistent'],1)
  self.assertEqual(reply['xip1LegacyId'],0x8517);self.assertEqual(reply['xip0Driver'],2);self.assertEqual(reply['xip1Driver'],1)
  self.assertEqual(reply['generalSpiPinsMatch'],1);self.assertEqual(reply['cus8ValidatedPackageState'],255)
  encoded=json.dumps(reply);self.assertNotIn(str(0x851712ab),encoded);self.assertNotIn(str(0xdeadbeef),encoded)
 def test_changed_snapshot_is_not_consistent(self):
  for n in range(len(SLOTS)):
   m=DiagnosticMachine();m.change=n;reply,_=m.execute(b'\2');self.assertEqual(reply['consistent'],0)
 def test_unknown_uninitialized_and_invalid_probe(self):
  for d in (0,0x020107f0,0x12345678):
   v=list(KNOWN);v[3]=d;m=DiagnosticMachine(v);reply,_=m.execute(b'\2');self.assertEqual(reply['xip1ProbeValid'],0);self.assertEqual(reply['xip1LegacyId'],0)
  m=DiagnosticMachine((0,)*len(SLOTS));reply,_=m.execute(b'\2');self.assertEqual(reply['generalSpiReady'],0);self.assertEqual(reply['cus8ContextPresent'],0)
 def test_request_and_failure_paths_do_not_read_slots(self):
  for data in (b'\2\0',b'\2'+bytes(7),b'\3\0',b'\3'+bytes(7),b'\xff'):
   m=DiagnosticMachine();reply,_=m.execute(data);self.assertEqual(reply['result'],'invalid');self.assertFalse(m.slot_reads)
  for amount in (0,34815):
   m=DiagnosticMachine();m.free_bytes=amount;reply,_=m.execute(b'\2');self.assertEqual(reply['result'],'allocation-failed');self.assertFalse(m.slot_reads)
  m=DiagnosticMachine();m.fail_alloc_sizes={1024};reply,_=m.execute(b'\2');self.assertEqual(reply['result'],'allocation-failed');self.assertFalse(m.slot_reads)
  for bad in ({'kind':5},{'next_node':0x12345678},{'data_null':True},{'declared':2}):
   m=DiagnosticMachine();reply,_=m.execute(b'\2',**bad);self.assertEqual(reply['result'],'invalid');self.assertFalse(m.slot_reads)
  for status in (False,True):
   m=DiagnosticMachine();m.fail_json=True;m.fail_status=status;reply,_=m.execute(b'\2');self.assertEqual(reply,None if status else {'status':4});self.assertEqual(len(m.slot_reads),42)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path);p.add_argument('--build',type=Path,default=BUILD);a=p.parse_args()
 G.BUILD=a.build.resolve();G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();F.REPLIES.clear();assert G.u.__version__=='2.1.4'
 F.RANGES=(*F.RANGES,(1,0x700000,0x800000));F.FlashMachine=DiagnosticMachine
 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(F.FlashRuntimeTests),unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticTests)])
 result=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
 report={'passed':result.wasSuccessful(),'build':str(G.BUILD),'blob_sha256':PINNED_SHA,'test_groups':result.testsRun,'handler_calls':len(G.RESULTS),'calls':G.RESULTS,'replies':F.REPLIES,'fixed_RAM_slots':SLOTS,'native_RAM_and_KV_mocked':True,'device_actions':False,'limitations':['Actual RV32 scalar loads, fixed-key native veneers and serializers execute against synthetic RAM/KV; hardware topology remains unmeasured.','Double sampling detects changed scalars but cannot prove atomicity or absence of ABA changes.','Native allocator/JSON/read/KV/CRC/bitmap APIs are mocked; no native wait or worst-case interrupt stack proof.']}
 if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('calls','replies','fixed_RAM_slots')}));raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
