#!/usr/bin/env python3
"""Pinned actual RV32 flash command/extraction/native wrapper; external APIs mocked."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'runtime/build/flash-read-001'
PINNED_SHA='d162d7c2f93ac57618f7756260e2b9c945313c160e6874517f98a8202777ca1b'
RANGES=((0,0,0x10000),(0,0x1eb000,0x1eb100),(0,0x7fc000,0x7fe000),(1,0x500000,0x510000))
G.NATIVES[0x04329ad8]='flash_read'
REPLIES=[]
def read_request(device,offset,length):return bytes([1,device])+struct.pack('<IH',offset,length)
class FlashMachine(G.Machine):
 def __init__(self):
  super().__init__();assert self.build['flash_reader'] and self.build['scene_session'] and self.build['input_observer']
  self.flash_calls=[];self.flash_result=0
 def native(self,name,args):
  if name=='flash_read':
   device,offset,dst,length=args[:4]
   assert 0<length<=256 and not offset%256
   assert any(device==d and b<=offset<e and length<=e-offset for d,b,e in RANGES)
   assert len(self.request_releases)==1 and all(not self.allocations[p]['live'] for parts in self.requests.values() for p in parts)
   assert self.allocations[dst]['tag']=='owned' and self.allocations[dst]['size']==1024
   assert self.read(dst,256)==bytes(256),'Raw buffer was not zero initialized'
   self.flash_calls.append((device,offset,length));self.events.append(('flash_read',dst))
   self.native_write(dst,bytes((offset+i+device*17)&255 for i in range(length)))
   return self.flash_result&0xffffffff
  if name=='try_alloc':
   assert self.request_releases and args[0]==1024
  result=super().native(name,args)
  if name=='try_alloc' and result:self.native_write(result,b'\xa5'*1024)
  return result
 def execute(self,data,**kwargs):
  request=self.request(data,**kwargs);reply,measurement=self.service(0x7b,request)
  assert self.request_releases==[request] and not self.owned_live()
  assert not self.queue and not self.sent and not self.images and not self.timers
  if reply is not None:REPLIES.append(reply)
  return reply,measurement
class FlashRuntimeTests(unittest.TestCase):
 def test_identity_query_and_boundaries(self):
  m=FlashMachine();identity,_=m.service(0x7e);self.assertEqual(identity['flashRead'],123)
  m=FlashMachine();q,_=m.execute(b'\0');self.assertEqual(q['ranges'],[{'device':d,'start':b,'end':e} for d,b,e in RANGES]);self.assertFalse(m.flash_calls);self.assertEqual(q['maxRead'],256)
  for d,b,e in RANGES:
   for off in (b,e-256):
    for length in (1,2,255,256):
     m=FlashMachine();reply,_=m.execute(read_request(d,off,length));self.assertEqual(m.flash_calls,[(d,off,length)])
     self.assertEqual(reply,{'glassly':'flash-read','abi':1,'result':'ok','device':d,'offset':off,'length':length,'hex':bytes((off+i+d*17)&255 for i in range(length)).hex()})
     events=[x[0] for x in m.events];self.assertLess(events.index('release_request'),events.index('try_alloc'));self.assertLess(events.index('flash_read'),events.index('json'))
 def test_invalid_no_driver_no_allocation(self):
  bad=[b'',b'\0\0',b'\xff',b'\1',bytes(8),read_request(0,0,0),read_request(0,0,257),read_request(0,0,65535)]
  for d,b,e in RANGES:
   bad.extend(read_request(d,b+i,1) for i in (1,2,127,255))
   bad.extend([read_request(d,e,1),read_request(d,e-256,257)])
   if b:bad.append(read_request(d,b-256,256))
  bad.extend(read_request(d,0,1) for d in (1,2,3,127,255))
  bad.extend([read_request(0,0x500000,256),read_request(1,0x1eb000,256),read_request(0,0xffffff00,256),read_request(1,0xffffffff,65535)])
  for data in bad:
   m=FlashMachine();reply,_=m.execute(data);self.assertEqual(reply['result'],'invalid');self.assertFalse(m.flash_calls);self.assertNotIn('try_alloc',m.calls)
 def test_actual_native_TLV_extraction_and_request_release(self):
  for kw in ({'kind':5},{'next_node':0x12345678},{'header_null':True},{'data_null':True},{'declared':0},{'declared':9}):
   m=FlashMachine();reply,_=m.execute(read_request(0,0,1),**kw);self.assertEqual(reply['result'],'invalid');self.assertFalse(m.flash_calls)
  m=FlashMachine();req=m.request(b'\0');reply,_=m.service(0x7b,req,sequence=None);self.assertEqual(reply['result'],'invalid');self.assertEqual(m.request_releases,[req])
  m=FlashMachine();reply,_=m.service(0x7b);self.assertEqual(reply['result'],'invalid');self.assertFalse(m.flash_calls)
 def test_read_failure_leaks_no_data_and_no_retry(self):
  for code in (1,-1,0x7fffffff):
   m=FlashMachine();m.flash_result=code;reply,_=m.execute(read_request(1,0x500000,256));self.assertEqual(len(m.flash_calls),1)
   self.assertEqual(reply,{'glassly':'flash-read','abi':1,'result':'read-failed'})
   events=[x[0] for x in m.events];self.assertGreater(events.index('json'),max(i for i,x in enumerate(events) if x=='free'))
 def test_low_memory_exact_bound_alloc_and_JSON_failures(self):
  for amount,expected in ((34815,'allocation-failed'),(34816,'ok')):
   m=FlashMachine();m.free_bytes=amount;reply,_=m.execute(read_request(0,0,256));self.assertEqual(reply['result'],expected);self.assertEqual(bool(m.flash_calls),expected=='ok')
  m=FlashMachine();m.free_bytes=33791;reply,_=m.execute(b'\0');self.assertEqual(reply['result'],'allocation-failed');self.assertFalse(m.flash_calls)
  m=FlashMachine();m.fail_alloc_sizes={1024};reply,_=m.execute(read_request(0,0,1));self.assertEqual(reply['result'],'allocation-failed');self.assertFalse(m.flash_calls)
  for fail_status in (False,True):
   m=FlashMachine();m.fail_json=True;m.fail_status=fail_status;reply,_=m.execute(read_request(0,0,256));self.assertEqual(reply,None if fail_status else {'status':4});self.assertEqual(len(m.flash_calls),1)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path);a=p.parse_args();G.BUILD=a.build.resolve();G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();REPLIES.clear();assert G.u.__version__=='2.1.4'
 result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(FlashRuntimeTests))
 report={'passed':result.wasSuccessful(),'build':str(G.BUILD),'blob_sha256':PINNED_SHA,'test_groups':result.testsRun,'handler_calls':len(G.RESULTS),'calls':G.RESULTS,'replies':REPLIES,'native_stubs':{hex(a):n for a,n in G.NATIVES.items()},'device_actions':False,'limitations':['Actual RV32 handler, TLV extraction and four-argument native wrapper execute; native read/allocator/JSON APIs are mocked.','Synthetic4KiB BT stack measurements exclude native frames/interrupts and are not cumulative stack or busy-loop timeout proof.','Physical flash contents and driver progress are not hardware-tested.']}
 if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('calls','replies','native_stubs')}));raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
