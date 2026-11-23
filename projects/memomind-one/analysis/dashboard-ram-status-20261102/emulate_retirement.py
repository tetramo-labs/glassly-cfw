#!/usr/bin/env python3
"""Pinned native status/header calls after proposed in-memory boot-only entry gates.

No image/device writes. Only log-enabled predicate02003d5e is mocked (false).
Native card null guards and all status/settings/cleanup logic execute as RV32.
"""
import hashlib,json,struct,sys,re
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r
ROOT=Path(__file__).resolve().parents[2];BASE=0x041eb020;GP=0x02011688
APP=ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin'
PIN='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
PATCHES=((0x0426f2c2,'411122c4'),(0x04268336,'011106ce'),(0x042683f0,'411122c6'),(0x04264f26,'011122cc'),(0x04265060,'011122cc'),(0x042652e8,'83a7416a'))
REMOVED=(0x02011d84,0x02011d50,0x02011d74,0x02011d58,0x02011d24,
         0x02015890,0x02015894,0x02011d44,0x02011d48,0x02011d4c,0x02015750,0x02011d2c)
RET=0x05000000;STACK=0x03000000;TOP=STACK+8192

def main():
 out=Path(sys.argv[1]);assert not out.exists()
 body=APP.read_bytes();assert hashlib.sha256(body).hexdigest()==PIN
 m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
 m.mem_map(0x041eb000,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(BASE,body)
 m.mem_map(0x02000000,0x100000);m.mem_write(0x02000000,body[0x64:0x64+0xf8b4])
 offset=0x04399fc8-BASE;m.mem_write(0x0200f8b8,body[offset:offset+0x1e78])
 # All omitted subsystem globals are in native startup's BSS clear interval.
 assert all(0x02011878<=a<a+4<=0x0205e128 for a in REMOVED)
 m.mem_map(STACK,8192);m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(RET,b'\x13\x00\x00\x00')
 for a,before in PATCHES:
  assert body[a-BASE:a-BASE+4].hex()==before;m.mem_write(a,bytes.fromhex('01458280'))
 allowed=set()
 for folder in ('native','status','status-rest','status-settings','header'):
  for path in (Path(__file__).parent/folder).glob('*.asm'):
   allowed.update(int(x,16) for x in re.findall(r'^ram:([0-9a-f]+)  ',path.read_text(),re.M))
 for a in (0x0426502a,0x04265042):
  path=ROOT/f'analysis/dashboard-ram-card-20261102/native/function-{a:08x}.asm'
  allowed.update(int(x,16) for x in re.findall(r'^ram:([0-9a-f]+)  ',path.read_text(),re.M))
 path=ROOT/'analysis/dashboard-reclaim-20261102/external-boundary/function-0426fc4c.asm'
 allowed.update(int(x,16) for x in re.findall(r'^ram:([0-9a-f]+)  ',path.read_text(),re.M))
 for a,_ in PATCHES:allowed.update((a,a+2))
 scalar_addresses={0x02011d28,0x02011d29,0x02011d54,0x02011d55,0x02011d5c,0x02011d5d,0x02011d78,0x02011d79,0x02011d88,0x02011d89}
 reg=lambda i:getattr(r,'UC_RISCV_REG_X'+str(i));state={};results=[]
 forbidden={0x0434e6da,0x02009904,0x0433c294,0x0434e6ee,0x042b3a3c,0x042a4f0e,0x042cf7ee,0x042cf61c,
            0x042b27ca,0x04329ad8,0x04329b1e,0x04329a14,0x04234b5c}
 def code(mu,a,n,_):
  state['instructions']+=1;state['min_sp']=min(state['min_sp'],mu.reg_read(reg(2)))
  if a==RET:state['returned']=True;mu.emu_stop();return
  assert a not in forbidden,('unexpected allocation/free/LVGL/resource/timer/flash operation',hex(a))
  if a==0x02003d5e:
   state['log_predicates']+=1;mu.reg_write(reg(10),0);mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(reg(1)));return
  assert a in allowed,('unreviewed executed instruction',hex(a))
 def write(mu,access,a,n,value,_):
  assert STACK<=a and a+n<=TOP or a in scalar_addresses and n==1,('unexpected native write',hex(a),n)
  if not STACK<=a<TOP:state['global_writes'].append([hex(a),n,value])
 m.hook_add(u.UC_HOOK_CODE,code);m.hook_add(u.UC_HOOK_MEM_WRITE,write)
 def call(entry,args=(),alignment=0):
  state.clear();state.update(instructions=0,min_sp=TOP-alignment,returned=False,log_predicates=0,global_writes=[])
  saved={i:0xabc00000+i for i in (8,9,*range(18,28))};saved.update({2:TOP-alignment,3:GP,4:0x12345678})
  for i,v in {**saved,1:RET,**{10+j:v for j,v in enumerate(args)}}.items():m.reg_write(reg(i),v)
  previous_depth=m.mem_read(0x02011d88,1)[0]
  previous_pending=m.mem_read(0x02011d89,1)[0]
  m.emu_start(entry,0,count=100000)
  assert state['returned']
  if entry in dict(PATCHES):
   assert state['instructions']==3 and not state['global_writes'] and state['min_sp']==TOP-alignment
   assert m.reg_read(reg(10))==0
   assert all(m.reg_read(reg(10+i))==v for i,v in enumerate(args) if i)
  assert all(m.reg_read(reg(i))==v for i,v in saved.items()),('ABI',hex(entry))
  if entry in (0x0426f3c0,0x0426f3ea):
   addresses=(0x02011d28,0x02011d54,0x02011d5c,0x02011d78)
   delta=int(entry==0x0426f3ea)
   assert all(m.mem_read(a+delta,1)[0]==(args[0]&255) for a in addresses)
  if entry==0x0426f998:assert m.mem_read(0x02011d88,1)[0]==(previous_depth+1)&255
  if entry==0x0426f96e and previous_depth:assert m.mem_read(0x02011d89,1)[0]==1
  if entry==0x0426f9b2:
   assert m.mem_read(0x02011d88,1)[0]==max(0,previous_depth-1)
   if previous_depth==1 and previous_pending:assert m.mem_read(0x02011d89,1)[0]==0
  assert all(bytes(m.mem_read(a,4))==bytes(4) for a in REMOVED),('removed owner state populated',hex(entry))
  results.append(dict(entry=hex(entry),args=list(args),sp_mod16=alignment,**state,max_stack=TOP-alignment-state['min_sp']))
 for alignment in (0,8):
  for a,_ in PATCHES:call(a,(0xdeadbeef,0x12345678,0xabcdef01,0x76543210),alignment)
  # Real init/selection/update/cleanup sequence, every style selector includinginvalid.
  for value in (0,1,2,3,4,5,255,0xffffffff):
   for a in (0x0426f3c0,0x0426f3ea,0x0426f320,0x0426fb4a,0x0426f414,0x0426f56e):call(a,(value,),alignment)
  for a in (0x0426f492,0x0426f4c8,0x0426f5bc,0x0426f60c,0x0426f73c,0x0426f78c,
            0x0426fa20,0x0426f8ee,0x0426f96e,0x0426fc40,0x0426fc4c,0x0426fc4c):call(a,(0,0,0,0),alignment)
  for a in (0x0426f998,0x0426f96e,0x0426f9b2,0x0426f9b2):call(a,(),alignment)
 report=dict(passed=True,native_calls=len(results),stock_body_sha256=PIN,device_actions=False,firmware_file_writes=False,
             patches=[dict(address=hex(a),before=b,after='01458280') for a,b in PATCHES],
             startup_assumption='Normal boot BSS zero [02011878,0205e128); initialized data copied from pinned image',
             mocked_native_calls={'02003d5e':'logging predicate returns0'},no_allocations_or_resources_or_LVGL_calls=True,
             removed_globals_remain_zero=[hex(a) for a in REMOVED],results=results,
             permitted_scalar_writes=[hex(a) for a in sorted(scalar_addresses)],
             limitations=['No full app-manager/task/scheduler/hardware emulation.','Known entry closure only; not proof against unknown arithmetic/indirect references.',
                          'Native card helpers execute with zero cardowner; status removal does not itself retirecard.'])
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=True,native_calls=len(results),report=str(out))))
if __name__=='__main__':main()
