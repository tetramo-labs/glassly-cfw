#!/usr/bin/env python3
"""Real RV32 startup memset + pool ctor/TLSF with proposed in-memory carve.

No image is written. Two short critical-section functions are explicit mocks;
allocator, memset, metadata, lookup, allocation and free remain pinned native code.
"""
import argparse, hashlib, json, struct, traceback, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin'
EXPECTED='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
BASE=0x041eb020; GP=0x02011688; BSS=0x02011878; OLD=0x0205e128; NEW=OLD+256
END=0x020fedc0; TABLE=0x0205d5f8; SP=0x0301fff0; RET=0x05000000
EDITS=((0x041fb238,'93878712','93878722'),
       (0x04399550,'28e10502','28e20502'),
       (0x04399554,'980c0a00','980b0a00'))
def digest(b):return hashlib.sha256(b).hexdigest()
def inside(ranges,a,n):return any(lo<=a and a+n<=hi for lo,hi in ranges)

class Machine:
 def __init__(self,u,r,body,carved):
  self.u,self.r=u,r;self.carved=carved;self.start=NEW if carved else OLD
  self.m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
  m=self.m;m.mem_map(0x041eb000,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(BASE,body)
  m.mem_map(0x02000000,0x100000);m.mem_write(0x02000000,body[0x64:0x64+0xf8b4])
  o=0x04399fc8-BASE;m.mem_write(0x0200f8b8,body[o:o+0x1e78])
  m.mem_write(BSS,b'\xa5'*(END-BSS));m.mem_write(BSS-16,b'\x69'*16);m.mem_write(END,b'\x7e'*32)
  m.mem_map(0x03000000,0x20000);m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC)
  m.mem_write(RET,bytes.fromhex('67800000')) # decoded stop sentinel, never executed
  self.stage='clear';self.stop=0x041fb252;self.done=False;self.depth=0;self.count=0;self.min_sp=SP
  self.calls=[];self.takes=0;self.gives=0;self.writes=0
  self.reg=lambda i:getattr(r,'UC_RISCV_REG_X'+str(i))
  self.allowed=[(BSS,self.start),(0x03000000,0x03020000)]
  def code(mu,a,n,_):
   self.count+=1;self.min_sp=min(self.min_sp,mu.reg_read(self.reg(2)))
   if a==self.stop:self.done=True;mu.emu_stop();return
   assert a not in {0x041fd196,0x041fd1ae,0x041fe86e,0x0433c174,0x02009904,
                    0x04329ad8,0x04329b1e,0x04329a14,0x043299aa,0x04329b90,
                    0x04234b5c,0x04235032},('forbidden assert/OOM/generic alloc/flash/KV',hex(a))
   if a==0x0200a23a:
    self.depth+=1;self.takes+=1;mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(self.reg(1)));return
   if a==0x0200a264:
    assert self.depth>0;self.depth-=1;self.gives+=1
    mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(self.reg(1)));return
   assert inside([(BASE,BASE+len(body)),(0x02000000,0x0200f8b4)],a,n),('unexpected code',hex(a))
  def write(mu,access,a,n,value,_):
   self.writes+=1
   assert inside(self.allowed,a,n),('outside permitted native writes',self.stage,hex(a),n)
  def read(mu,access,a,n,value,_):
   assert inside([(0x02000000,END),(0x03000000,0x03020000),(BASE,BASE+len(body))],a,n),('unexpected data read',hex(a),n)
  m.hook_add(u.UC_HOOK_CODE,code);m.hook_add(u.UC_HOOK_MEM_WRITE,write);m.hook_add(u.UC_HOOK_MEM_READ,read)
 def bytes(self,a,n):return bytes(self.m.mem_read(a,n))
 def word(self,a):return struct.unpack('<I',self.bytes(a,4))[0]
 def call(self,entry,args=(),stop=RET,preserve=True):
  m=self.m;self.done=False;self.stop=stop;self.count=0;self.min_sp=SP;self.writes=0
  saved={i:0xabc00000+i for i in (8,9,*range(18,28))}
  for i,v in {**saved,1:RET,2:SP,3:GP,4:0x12345678,**{10+j:v for j,v in enumerate(args)}}.items():m.reg_write(self.reg(i),v)
  try:m.emu_start(entry,0,count=2000000)
  except Exception as exc:raise RuntimeError(f'{self.stage} entry {entry:08x} pc {m.reg_read(self.r.UC_RISCV_REG_PC):08x}: {exc}') from exc
  assert self.done and self.depth==0,'budget or unbalanced critical section'
  assert m.reg_read(self.reg(3))==GP and m.reg_read(self.reg(4))==0x12345678
  if preserve:
   assert m.reg_read(self.reg(2))==SP
   for i,v in saved.items():assert m.reg_read(self.reg(i))==v,('callee register',i)
  result=m.reg_read(self.reg(10));self.calls.append(dict(stage=self.stage,entry=hex(entry),arguments=list(args),result=result,instructions=self.count,max_stack=SP-self.min_sp,native_writes=self.writes))
  self.guards();return result
 def guards(self):
  assert self.bytes(BSS-16,16)==b'\x69'*16,'pre-BSS sentinel changed'
  assert self.bytes(END,32)==b'\x7e'*32,'heap-end sentinel changed'
  if self.stage!='clear' and self.carved:assert self.bytes(OLD,256)==bytes(range(256)),'registry overwritten'
 def run(self):
  self.call(0x041fb234,stop=0x041fb252,preserve=False)
  assert self.bytes(BSS,self.start-BSS)==bytes(self.start-BSS)
  assert self.bytes(self.start,32)==b'\xa5'*32,'BSS clear crossed new heap front'
  assert self.bytes(OLD,256)==(bytes(256) if self.carved else b'\xa5'*256)
  assert self.bytes(0x0205e124,4)==bytes(4),'last original BSS word not zero'
  if self.carved:self.m.mem_write(OLD,bytes(range(256)))
  self.stage='pool_constructor';self.allowed=[(TABLE,TABLE+16),(self.start,END),(0x03000000,0x03020000)]
  bss_before=self.bytes(BSS,OLD-BSS)
  assert self.call(0x0433c5a8)==0
  assert [self.word(TABLE+i) for i in (0,4,8,12)]==[2,self.start,END,self.start]
  # Outside the existing first pool-registration slot, original globals unchanged.
  bss_after=self.bytes(BSS,OLD-BSS)
  assert all(a==b or TABLE<=BSS+i<TABLE+16 for i,(a,b) in enumerate(zip(bss_before,bss_after)))
  assert self.bytes(TABLE+16,64)==bytes(64),'additional pool registered'
  assert self.word(self.start+12)==self.start+16,'TLSF control pointer did not move with pool'
  initial_free=self.word(self.start);assert self.word(self.start+4)==initial_free
  self.stage='allocator';self.allowed=[(self.start,END),(0x03000000,0x03020000)]
  assert self.call(0x0433c460)==initial_free
  for pointer in [OLD-1,OLD,NEW-1,NEW,self.start,END-1,END]:
   assert self.call(0x0433c190,[pointer])==(TABLE if self.start<=pointer<END else 0)
  allocations=[]
  for size in [1,12,124,256,4096,8192,65536]:
   pointer=self.call(0x0433c294,[size,0]);assert pointer%4==0 and self.start+16+2000<=pointer and pointer+size<=END
   assert self.call(0x0433c190,[pointer])==TABLE
   pattern=bytes([size%251+1])*size;self.m.mem_write(pointer,pattern);allocations.append((pointer,size,pattern))
  assert self.call(0x0433c294,[0x100000,0])==0,'ordinary no-fit did not fail'
  assert self.call(0x0433c294,[128,1])==0,'mask1 unexpectedly selected pool'
  extra=self.call(0x0433c294,[128,2]);assert extra>=self.start+2016 and extra+128<=END
  self.call(0x020099a0,[extra])
  for pointer,size,pattern in reversed(allocations):
   assert self.bytes(pointer,size)==pattern,'allocation payload corruption'
   self.call(0x020099a0,[pointer])
  assert self.word(self.start)==initial_free,'free accounting did not restore'
  assert self.call(0x0433c460)==initial_free
  assert self.call(0x0433c4a4)<=initial_free
  assert self.takes==self.gives and self.takes>0
  self.guards()
  return dict(carved=self.carved,passed=True,pool_start=self.start,pool_end=END,raw_size=END-self.start,
              initial_free=initial_free,registry_cleared=self.carved,registry_guarded_after_clear=self.carved,
              old_native_globals_preserved_except_pool_slot=True,critical_calls=self.takes,
              calls=self.calls,native_calls=len(self.calls),max_observed_stack=max(c['max_stack'] for c in self.calls))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve()
 if any(out==ROOT/x or ROOT/x in out.parents for x in ('analysis/ghidra','analysis/flash-worker-lifecycle-20261101')):p.error('Do not overwrite frozen native evidence')
 out.mkdir(parents=True,exist_ok=False)
 report=dict(passed=False,device_actions=False,firmware_images_written=False,variants=[],limitations=['Actual startup clear span, not whole boot.','Critical enter/exit mocked and checked; no IRQ, RTOS, other-core or hardware behavior emulated.','Original and proposed bytes run in separate emulators; no firmware image persisted.','Native allocator invariants/selected operations, not exhaustive exhaustion or concurrent allocation proof.'])
 status=1
 try:
  if not __debug__:raise RuntimeError('Assertions must be enabled')
  import unicorn as u
  from unicorn import riscv_const as r
  assert u.__version__=='2.1.4'
  sys.path.insert(0,str(ROOT/'scripts'))
  import build_memomind_flash_canary as constructor
  assert EDITS==tuple((a,b,c) for a,b,c,_ in constructor.REGISTRY_PATCHES),'Constructor registry edits differ'
  original=APP.read_bytes();assert digest(original)==EXPECTED
  report['constructor_sha256']=digest(Path(constructor.__file__).read_bytes())
  changed=bytearray(original)
  for address,before,after in EDITS:
   offset=address-BASE;b=bytes.fromhex(before);n=bytes.fromhex(after);assert len(b)==len(n)==4
   assert changed[offset:offset+4]==b;changed[offset:offset+4]=n
  assert len(changed)==len(original)
  report.update(unicorn=u.__version__,source_sha256=EXPECTED,proposed_in_memory_sha256=digest(changed),script_sha256=digest(Path(__file__).read_bytes()),edits=[dict(address=hex(addr),before=b,after=n) for addr,b,n in EDITS])
  for carved,body in [(False,original),(True,bytes(changed))]:
   report['active_variant']='carved' if carved else 'original';report['variants'].append(Machine(u,r,body,carved).run())
  old,new=report['variants'];assert old['pool_end']==new['pool_end'] and old['raw_size']-new['raw_size']==256 and old['initial_free']-new['initial_free']==256
  report.pop('active_variant');report.update(passed=True,total_native_calls=sum(v['native_calls'] for v in report['variants']),initial_free_delta=256);status=0
 except Exception as exc:report.update(error=str(exc),traceback=traceback.format_exc())
 finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(passed=report['passed'],variants=len(report['variants']),output=str(out))));return status
if __name__=='__main__':raise SystemExit(main())
