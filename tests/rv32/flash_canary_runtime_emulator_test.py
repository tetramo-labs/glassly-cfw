#!/usr/bin/env python3
"""Actual canary+native binding RV32. Scheduler/flash/KV are explicit mocks."""
import argparse,json,struct,unittest,zlib
from pathlib import Path
import graphics_runtime_emulator_test as G
R=G.r
BUILD=G.ROOT/'runtime/build/flash-canary-004'
PINNED_SHA='c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992'
REGISTRY,POOL,WORKER_BASE,WORKER_RET=0x0205e128,0x0205d5f8,0x020e0000,0x05002000
G.HEAP=0x02060000
G.NATIVES.update({0x0200a23a:'critical_enter',0x0200a264:'critical_leave',0x0200f168:'create_task',0x04235032:'badmap_get',0x042a9c84:'badmap_crc',0x042a9cca:'badmap_valid',0x04329ad8:'flash_read',0x04329b1e:'flash_program',0x04329a14:'flash_erase',0x04324bea:'alias_cache'})
REPLIES=[];WORKERS=[]
def packet(op):return struct.pack('<BI',op,0x43414e31)
class CanaryMachine(G.Machine):
 def __init__(self):
  self.critical=0;self.in_worker=False;self.registry_reads=0;self.pool_reads=0
  super().__init__();assert self.build['flash_canary'] and self.build['full_store_reader']
  for p in (POOL&~4095,REGISTRY&~4095):self.uc.mem_map(p,4096,G.u.UC_PROT_READ|G.u.UC_PROT_WRITE)
  self.uc.mem_write(POOL,struct.pack('<4I',2,0x0205e228,0x020fedc0,0x0205e228))
  self.uc.mem_map(WORKER_RET,4096,G.u.UC_PROT_READ|G.u.UC_PROT_EXEC);self.uc.mem_write(WORKER_RET,b'\x13\0\0\0')
  self.flash=bytearray(b'\xff'*8192);self.flash_events=[];self.boundaries=0;self.fail_at=0;self.pending=None
  self.early=True;self.create_fail=False;self.worker_context=None;self.worker_alignment=8;self.task_creates=0;self.collateral=False;self.service_alignment=0
  raw=struct.pack('<4I',0x474d4231,1,0x01500000,0x00300000)+bytes(96)
  self.map_record=raw+struct.pack('<I',zlib.crc32(raw));self.kv_status=0;self.kv_length=116
 def region(self,address,size,writing=False):
  if POOL<=address and address+size<=POOL+16:
   assert not writing;self.pool_reads+=1;return 'native-pool-descriptor'
  if REGISTRY<=address and address+size<=REGISTRY+40:
   assert self.critical,'Registry outside critical section';self.registry_reads+=1;return 'explicit-private-registry'
  return super().region(address,size,writing)
 def native(self,name,args):
  a0,a1,a2,a3,a4=args[:5]
  if name=='critical_enter':assert not self.critical;self.critical=1;return 0
  if name=='critical_leave':assert self.critical==1;self.critical=0;return 0
  assert not self.critical,'Blocking/native operation under critical section'
  if name=='create_task':
   assert not self.in_worker and a0==self.symbols['glassly_flash_canary_entry'] and (a2,a3)==(5,0x800)
   assert self.cstring(a4)=='glassly_canary';assert self.allocations[a1]['tag']=='owned';self.task_creates+=1
   if self.create_fail:return 0
   if self.early:self.begin_worker(a1);return None
   self.pending=a1;return 0xdead0000
  if name=='badmap_get':
   assert self.in_worker and (a0,a2)==(0x6009,116);assert self.read(a1,116)==bytes(116) and self.read(a3,4)==bytes(4)
   self.native_write(a1,self.map_record);self.native_write(a3,struct.pack('<I',self.kv_length));return self.kv_status
  if name=='badmap_crc':assert self.in_worker;return zlib.crc32(self.read(a0,112))
  if name=='badmap_valid':assert self.in_worker;return int(self.read(a0,2)==bytes(2))
  if name in ('flash_read','flash_program','flash_erase'):
   assert self.in_worker and a0==1;self.boundaries+=1;self.flash_events.append((name,a1))
   if name=='flash_erase':assert (a1,a2)==(0x7ff000,4096)
   elif name=='flash_program':assert (a1,a3)==(0x7ff000,256)
   else:assert 0x7fe000<=a1<=0x7fff00 and a1%256==0 and a3==256
   if self.fail_at==self.boundaries:
    if name=='flash_read':self.native_write(a2,b'\x77'*256)
    return 19
   off=a1-0x7fe000
   if name=='flash_read':self.native_write(a2,bytes(self.flash[off:off+256]))
   elif name=='flash_program':
    data=self.read(a2,256)
    assert data==bytes(((i*37)^0xa5)&255 for i in range(256));assert self.flash[4096:4352]==b'\xff'*256;self.flash[4096:4352]=data
    if self.collateral:self.flash[4352]=0
   else:self.flash[4096:]=b'\xff'*4096
   return 0
  if name=='alias_cache':assert self.in_worker and a0==0 and a1==0x057ff000 and a2 in (256,4096);self.flash_events.append((name,a1));return 0
  if self.in_worker:assert name=='free','Worker must not allocate, respond, post, or use LVGL'
  return super().native(name,args)
 def begin_worker(self,job):
  assert not self.in_worker
  saved={i:self.reg(i) for i in range(1,32)}
  fp={i:self.uc.reg_read(getattr(R,f'UC_RISCV_REG_F{i}')) for i in range(32)}
  self.worker_context=(saved,fp,(self.stack_base,self.stack_top,self.min_sp))
  self.stack_base=WORKER_BASE;self.stack_top=WORKER_BASE+8192;self.min_sp=self.stack_top
  self.uc.mem_write(WORKER_BASE,b'\xcc'*8192);self.in_worker=True
  for i in range(1,32):self.set(i,0xb0000000+i*0x101)
  for i,v in {1:WORKER_RET,2:self.stack_top-self.worker_alignment,3:0x02011688,4:0x0200abcd,10:job}.items():self.set(i,v)
  self.worker_initial={i:self.reg(i) for i in G.CALLEE};self.worker_fp={i:self.uc.reg_read(getattr(R,f'UC_RISCV_REG_F{i}')) for i in G.FP_CALLEE}
  self.uc.reg_write(R.UC_RISCV_REG_PC,self.symbols['glassly_flash_canary_entry'])
 def end_worker(self):
  for i,v in self.worker_initial.items():assert self.reg(i)==v,f'Worker corrupted x{i}'
  for i,v in self.worker_fp.items():assert self.uc.reg_read(getattr(R,f'UC_RISCV_REG_F{i}'))==v
  assert not self.critical and not self.owned_live(),'Worker must free argument before terminal publication'
  WORKERS.append({'initial_sp_mod16':self.worker_initial[2]%16,'observed_stack_bytes':self.stack_top-self.min_sp,'callee_ra_sp_gp_tp_fp_preserved':True,'native_boundaries':self.boundaries})
  saved,fp,stack=self.worker_context;self.worker_context=None;self.in_worker=False
  for i,v in saved.items():self.set(i,v)
  for i,v in fp.items():self.uc.reg_write(getattr(R,f'UC_RISCV_REG_F{i}'),v)
  self.stack_base,self.stack_top,self.min_sp=stack
 def instruction(self,uc,address,size,userdata):
  if address==WORKER_RET:self.end_worker();self.return_native(0xdead0000);return
  veneers=[self.symbols[n] for n in ('glassly_flash_canary_entry','glassly_flash_canary_command_entry')]
  gates=((G.ENTRY,G.ENTRY+64),(self.symbols['glassly_flash_canary_dispatch'],self.symbols['glassly_flash_canary_dispatch']+12))
  allowed=any(v<=address<v+32 for v in veneers) or (not self.in_worker and any(lo<=address<hi for lo,hi in gates))
  if allowed and self.reg(2)%16:
   assert self.reg(2)%16==8 and self.stack_base<=self.reg(2)<=self.stack_top
   self.instructions+=1;self.min_sp=min(self.min_sp,self.reg(2));return
  super().instruction(uc,address,size,userdata)
 def call(self,symbol,*args,display=False):
  if not self.service_alignment:return super().call(symbol,*args,display=display)
  assert symbol=='service_entry' and args[0]==0x7a and not display
  self.stack_base,self.stack_top=G.BT_BASE,G.BT_BASE+4096;self.min_sp=self.stack_top
  self.uc.mem_write(self.stack_base,b'\xcc'*4096)
  for i in range(1,32):self.set(i,0xa0000000+i*0x101)
  for i,v in {1:G.RET,2:self.stack_top-8,3:0x02011688,4:0x0200abcd}.items():self.set(i,v)
  for i,v in enumerate(args):self.set(10+i,v)
  initial={i:self.reg(i) for i in G.CALLEE}
  for i in G.FP_CALLEE:self.uc.reg_write(getattr(R,f'UC_RISCV_REG_F{i}'),0x3f800000+i)
  fp={i:self.uc.reg_read(getattr(R,f'UC_RISCV_REG_F{i}')) for i in G.FP_CALLEE}
  old=self.instructions;self.uc.emu_start(G.ENTRY,G.RET,count=3000000);assert self.uc.reg_read(R.UC_RISCV_REG_PC)==G.RET
  for i,v in initial.items():assert self.reg(i)==v,f'Unaligned BT corrupted x{i}'
  for i,v in fp.items():assert self.uc.reg_read(getattr(R,f'UC_RISCV_REG_F{i}'))==v
  result={'entry':symbol,'task':'BT','incoming_sp_mod16':8,'stack_capacity':4096,'observed_stack_bytes':self.stack_top-self.min_sp,'instructions':self.instructions-old,'callee_gp_tp_fp_preserved':True}
  G.RESULTS.append(result);return result
 def execute(self,data,**kw):
  req=self.request(data,**kw);reply,measurement=self.service(0x7a,req);assert req in self.request_releases
  if reply is not None:REPLIES.append(reply)
  assert not self.queue and not self.sent and not self.timers and not self.images
  return reply,measurement
 def finish(self):
  job=self.pending;self.pending=None;self.begin_worker(job)
  self.uc.emu_start(self.symbols['glassly_flash_canary_entry'],WORKER_RET,count=3000000)
  assert self.uc.reg_read(R.UC_RISCV_REG_PC)==WORKER_RET;self.end_worker()
class CanaryTests(unittest.TestCase):
 def test_identity_declares_explicit_registry(self):
  m=CanaryMachine();r,_=m.service(0x7e);self.assertEqual((r['flashCanary'],r['registryBytes'],r['writableStaticBytes']),(122,256,256));self.assertFalse(m.owned_live());self.assertEqual(m.registry_reads,0)
 def test_program_collateral_is_detected_before_restore(self):
  m=CanaryMachine();m.collateral=True;r,_=m.execute(packet(2));self.assertEqual((r['state'],r['phase'],r['error']),('failed',5,-19718));self.assertFalse(r['restored']);self.assertEqual(sum(n=='flash_erase' for n,o in m.flash_events),1)
 def test_canary_service_thunk_at_eight_byte_alignment(self):
  for operation in (0,1,2):
   for worker_alignment in (0,8):
    m=CanaryMachine();m.service_alignment=8;m.worker_alignment=worker_alignment
    r,_=m.execute(b'\0' if not operation else packet(operation));self.assertEqual(r['state'],'idle' if not operation else 'passed');self.assertFalse(m.owned_live())
 def test_early_completion_realigned_stack_and_saved_state(self):
  for alignment in (0,8):
   for op in (1,2):
    m=CanaryMachine();m.worker_alignment=alignment;reply,_=m.execute(packet(op))
    self.assertEqual(reply['state'],'passed');self.assertEqual(reply['operation'],op);self.assertEqual(reply['mutationStarted'],op==2)
    self.assertEqual(reply['restored'],op==2);self.assertTrue(reply['neighborVerified']);self.assertFalse(m.owned_live())
    self.assertEqual(m.boundaries,32 if op==1 else 100);self.assertEqual(m.flash,b'\xff'*8192)
    reply,_=m.execute(packet(op));self.assertEqual(reply['result'],'already-used');self.assertEqual(m.task_creates,1)
 def test_delayed_worker_status_and_screen_independence(self):
  m=CanaryMachine();m.early=False;reply,_=m.execute(packet(2));self.assertEqual(reply['state'],'starting');self.assertEqual(len(m.owned_live()),1)
  m.screen_present=False;m.active_launcher=False
  reply,_=m.execute(b'\0');self.assertEqual(reply['state'],'starting');self.assertEqual(m.task_creates,1)
  m.finish();reply,_=m.execute(b'\0');self.assertEqual(reply['state'],'passed');self.assertFalse(m.owned_live())
 def test_every_native_boundary_error_stops_without_retry(self):
  for n in range(1,101):
   m=CanaryMachine();m.fail_at=n;r,_=m.execute(packet(2));self.assertEqual(r['state'],'failed');self.assertEqual(m.boundaries,n)
   self.assertEqual(r['nativeStatus'],19);self.assertFalse(m.owned_live());m.execute(b'\0');self.assertEqual(m.boundaries,n)
 def test_reply_failures_preserve_terminal_state_without_retry(self):
  for failure in ('workspace','json','status'):
   m=CanaryMachine()
   if failure=='workspace':m.fail_alloc_sizes={768}
   else:m.fail_json=True;m.fail_status=failure=='status'
   r,_=m.execute(packet(2));self.assertEqual(r,{'glassly':'flash-canary','abi':1,'result':'allocation-failed'} if failure=='workspace' else None if failure=='status' else {'status':4})
   self.assertFalse(m.owned_live());self.assertEqual(m.task_creates,1)
   m.fail_alloc_sizes=set();m.fail_json=m.fail_status=False;r,_=m.execute(b'\0');self.assertEqual(r['state'],'passed');self.assertEqual(m.task_creates,1)
 def test_registry_guard_before_access_and_corruption(self):
  for index in range(4):
   m=CanaryMachine();raw=bytearray(m.uc.mem_read(POOL,16));raw[index*4]^=1;m.uc.mem_write(POOL,bytes(raw));r,_=m.execute(packet(2))
   self.assertEqual(r['result'],'wrong-image');self.assertEqual(m.registry_reads,0);self.assertEqual(m.task_creates,0)
  m=CanaryMachine();m.uc.mem_write(REGISTRY,struct.pack('<I',1));r,_=m.execute(packet(2));self.assertEqual(r['result'],'registry-invalid');self.assertEqual(m.task_creates,0)
 def test_native_badmap_absence_bits_invalid_and_preimage(self):
  m=CanaryMachine();m.kv_status=7;m.kv_length=0;r,_=m.execute(packet(2));self.assertEqual((r['state'],r['mapSource']),('passed',2))
  for bit in (6,7):
   m=CanaryMachine();raw=bytearray(m.map_record);raw[111]|=1<<bit;raw[112:]=struct.pack('<I',zlib.crc32(raw[:112]));m.map_record=bytes(raw);r,_=m.execute(packet(2));self.assertEqual(r['state'],'failed');self.assertFalse(m.flash_events)
  for bad in ('status','length','crc','absent-length'):
   m=CanaryMachine()
   if bad=='status':m.kv_status=2
   elif bad=='length':m.kv_length=115
   elif bad=='crc':m.map_record=m.map_record[:-1]+bytes([m.map_record[-1]^1])
   else:m.kv_status=7
   r,_=m.execute(packet(2));self.assertEqual(r['state'],'failed');self.assertFalse(m.flash_events)
  for off in (0,4095,4096,8191):
   m=CanaryMachine();m.flash[off]=0;r,_=m.execute(packet(2));self.assertEqual(r['state'],'failed');self.assertFalse(r['mutationStarted'])
 def test_allocator_create_and_TLV_failures(self):
  for kind in ('headroom','job','task'):
   m=CanaryMachine()
   if kind=='headroom':m.free_bytes=96*1024-1
   elif kind=='job':m.fail_alloc_sizes={676}
   else:m.create_fail=True
   r,_=m.execute(packet(2));self.assertEqual(r['state'],'failed');self.assertFalse(m.flash_events);self.assertFalse(m.owned_live())
  for data,kw in ((b'',{}),(b'\0\0',{}),(packet(3),{}),(b'\2'+bytes(4),{}),(packet(2),{'kind':5}),(packet(2),{'next_node':0x12345678}),(packet(2),{'data_null':True})):
   m=CanaryMachine();r,_=m.execute(data,**kw);self.assertEqual(r['result'],'invalid');self.assertEqual(m.registry_reads,0);self.assertFalse(m.owned_live())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path);a=p.parse_args();G.BUILD=a.build.resolve();G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();REPLIES.clear();WORKERS.clear()
 result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(CanaryTests))
 report={'passed':result.wasSuccessful(),'build':str(G.BUILD),'blob_sha256':PINNED_SHA,'test_groups':result.testsRun,'calls':G.RESULTS,'workers':WORKERS,'replies':REPLIES,'device_actions':False,'limitations':['Actual RV32 command, worker, registry guard, stack veneer and native flash adapter execute; scheduler/native flash/KV/cache/allocator are mocked.','No native task wrapper/reaper execution here, no physical flash or timing/cumulative stack guarantee.']}
 if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('calls','workers','replies')}));raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
