#!/usr/bin/env python3
"""Pinned full-store RV32 reader and diagnostics; all native hardware APIs mocked."""
import argparse,json,unittest
from pathlib import Path
import flash_read_runtime_emulator_test as F
import storage_diag_runtime_emulator_test as D
G=F.G
BUILD=F.ROOT/'runtime/build/full-store-read-001'
PINNED_SHA='83290f4c3d300b3f479bcd60865ffb5cc29b55e5887e635fac6f0d0d208d352b'
PROFILE='H001Y-1.0.3.127-full-store-read-v1'
class FullMachine(D.DiagnosticMachine):
 def __init__(self):
  super().__init__();assert self.build['full_store_reader'] and self.build['storage_diagnostics']
class FullTests(F.FlashRuntimeTests):
 def test_newly_admitted_middle_and_exact_profile(self):
  m=FullMachine();q,_=m.execute(b'\0');self.assertEqual(q['profile'],PROFILE)
  for offset in (0x50ff00,0x510000,0x5fff00,0x600000,0x6fff00,0x700000,0x7fff00):
   m=FullMachine();r,_=m.execute(F.read_request(1,offset,256));self.assertEqual(r['offset'],offset);self.assertEqual(len(bytes.fromhex(r['hex'])),256)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path);a=p.parse_args()
 G.BUILD=a.build.resolve();G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();F.REPLIES.clear();assert G.u.__version__=='2.1.4'
 F.RANGES=(*F.RANGES[:3],(1,0x500000,0x800000));F.FlashMachine=FullMachine
 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(FullTests),unittest.defaultTestLoader.loadTestsFromTestCase(D.DiagnosticTests)])
 result=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
 report={'passed':result.wasSuccessful(),'build':str(G.BUILD),'blob_sha256':PINNED_SHA,'profile':PROFILE,'test_groups':result.testsRun,'handler_calls':len(G.RESULTS),'calls':G.RESULTS,'replies':[r for r in F.REPLIES if 'diagnostic' not in r],'diagnostic_replies':[r for r in F.REPLIES if 'diagnostic' in r],'native_stubs':{hex(a):n for a,n in G.NATIVES.items()},'device_actions':False,'limitations':['Actual RV32 handler, gates, TLV extraction, serializers and native read wrapper execute against mocked APIs and fixed RAM.','Synthetic4KiB stack excludes native frames/interrupts; no hardware driver progress, timeout or ownership proof.']}
 if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('calls','replies','diagnostic_replies','native_stubs')}));raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
