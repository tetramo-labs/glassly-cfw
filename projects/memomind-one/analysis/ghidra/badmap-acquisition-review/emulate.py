#!/usr/bin/env python3
"""Actual pinned RV32 badmap loader + KV getter; synthetic read-only KV pages, RTOS locks mocked."""
from pathlib import Path
import hashlib,json,struct,zlib
import unicorn as u
from unicorn import riscv_const as r
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
BODY=(ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
assert hashlib.sha256(BODY).hexdigest()=='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
assert u.__version__=='2.1.4'
BASE=0x041eb020;KV=0x046f8000;DST=0x03001000;ACTUAL=0x03000100;SP=0x0301fff0;RET=0x05000000;MUTEX=0x06000001
CRC8=BODY[0x043988a0-BASE:0x043988a0-BASE+256]
def crc8(b):
 c=255
 for x in b:c=CRC8[c^x]
 return c^255

def record(bits=(),**changes):
 bm=bytearray(96)
 for i in bits:bm[i//8]|=1<<(i%8)
 b=bytearray(struct.pack('<4I',0x474d4231,1,0x1500000,0x300000)+bm)
 for off,value in changes.items():struct.pack_into('<I',b,int(off),value)
 return bytes(b)+struct.pack('<I',zlib.crc32(b))

def pages(payload=None,mode=1,key=0x6009,corrupt_sector=False,corrupt_kv_crc=False):
 b=bytearray(b'\xff'*0x80000)
 for off in range(0,len(b),4096):
  state=0xffffff00;h=state^0x57714b78^mode
  struct.pack_into('<IIIHBB',b,off,state,0xffffff00,0x57714b78,0,mode,(h^(h>>8)^(h>>16)^(h>>24))&255)
 if payload is not None:
  n=len(payload);h=n^key
  struct.pack_into('<IHBBHBB',b,16,0xffff0000,n,crc8(payload)^(1 if corrupt_kv_crc else 0),0,key,0,(h^(h>>8))&255)
  b[28:28+n]=payload
 if corrupt_sector:b[15]^=1
 return bytes(b)

FORBIDDEN={0x02009904,0x0434e6da,0x020099a0,0x0434e6ee,0x04234ac8,0x04234b5c,0x04329b1e,0x04329a14,0x043299aa,0x04329b90,0x042a9dd4,0x041fd196}
def call(entry,args,kv,mode=1,initialized=True):
 m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
 m.mem_map(0x041eb000,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(BASE,BODY)
 m.mem_map(0x02000000,0x100000);m.mem_write(0x02000000,BODY[0x64:0x64+0xf8b4]);o=0x04399fc8-BASE;m.mem_write(0x0200f8b8,BODY[o:o+0x1e78])
 m.mem_map(KV,0x80000,u.UC_PROT_READ);m.mem_write(KV,kv)
 m.mem_map(0x03000000,0x20000);m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(RET,bytes.fromhex('67800000'))
 m.mem_write(0x02011aec,bytes([mode]));m.mem_write(0x02011af0,struct.pack('<I',MUTEX if initialized else 0));m.mem_write(0x02011af4,b'\x01');m.mem_write(0x02011af8,struct.pack('<I',KV))
 m.mem_write(DST-16,b'\xa5'*288);m.mem_write(ACTUAL,struct.pack('<I',0xcccccccc))
 reg=lambda i:getattr(r,'UC_RISCV_REG_X'+str(i))
 saved={i:0xabc00000+i for i in (8,9,18,19,20,21,22,23,24,25,26,27)}
 for i,v in {**saved,1:RET,2:SP,3:0x02011688,4:0x12345678,**{10+j:v for j,v in enumerate(args)}}.items():m.reg_write(reg(i),v)
 done=False;steps=0;minsp=SP;locks=[];lookups=0;getters=0;kv_reads=0;writes=0
 def hook(mu,a,n,_):
  nonlocal done,steps,minsp,lookups,getters
  steps+=1;minsp=min(minsp,mu.reg_read(reg(2)))
  if a==RET:done=True;mu.emu_stop();return
  if a in FORBIDDEN:raise RuntimeError('forbidden mutation/allocation/assert/init '+hex(a))
  if a==0x0423463e:lookups+=1
  if a==0x04235032:getters+=1
  if a in (0x0200ec3a,0x0200ecb2):
   assert mu.reg_read(reg(10))==MUTEX
   locks.append('take' if a==0x0200ec3a else 'give');mu.reg_write(reg(10),0);mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(reg(1)))
 def write(mu,access,a,n,val,_):
  nonlocal writes
  writes+=1
  assert 0x03000000<=a and a+n<=0x03020000,('unexpected non-scratch write',hex(a),n)
 def read(mu,access,a,n,val,_):
  nonlocal kv_reads
  kv_reads+=1
 m.hook_add(u.UC_HOOK_CODE,hook);m.hook_add(u.UC_HOOK_MEM_WRITE,write);m.hook_add(u.UC_HOOK_MEM_READ,read,begin=KV,end=KV+0x80000-1)
 m.emu_start(entry,0,count=2000000)
 assert done,'instruction budget'
 for i,v in saved.items():assert m.reg_read(reg(i))==v,('callee register',i)
 assert m.reg_read(reg(3))==0x02011688 and m.reg_read(reg(4))==0x12345678 and m.reg_read(reg(2))==SP
 ret=m.reg_read(reg(10));ret=ret if ret<2**31 else ret-2**32
 assert bytes(m.mem_read(DST-16,16))==b'\xa5'*16 and bytes(m.mem_read(DST+256,16))==b'\xa5'*16
 return {'return':ret,'output':bytes(m.mem_read(DST,256)).hex(),'actual_length':struct.unpack('<I',m.mem_read(ACTUAL,4))[0],'locks':locks,'iterator_calls':lookups,'getter_calls':getters,'kv_memory_reads':kv_reads,'instructions':steps,'max_stack_bytes':SP-minsp,'scratch_writes':writes,'allocations':0,'flash_mutations':0,'native_init_calls':0}

results=[]
def check(name,entry,args,kv,expected,out_prefix=None,unchanged=False,**kw):
 x=call(entry,args,kv,**kw);assert x['return']==expected,(name,x)
 raw=bytes.fromhex(x['output'])
 if out_prefix is not None:assert raw[:len(out_prefix)]==out_prefix,name
 if unchanged:assert raw==b'\xa5'*256,name
 x.pop('output');x['name']=name;x['passed']=True;results.append(x);return x
loader=[0,DST,96];getter=[0x6009,DST,116,ACTUAL]
for mode in (1,2):
 empty=pages(mode=mode)
 x=check(f'getter absent mode{mode}',0x4235032,getter,empty,7,unchanged=True,mode=mode);assert x['actual_length']==0 and x['locks']==['take','give'] and x['iterator_calls']==129
 check(f'loader absent zero map mode{mode}',0x42a9d0a,loader,empty,0,bytes(96),mode=mode)
 for bits in [(),(16,511,512,767)]:
  rec=record(bits);pg=pages(rec,mode)
  x=check(f'getter present {bits} mode{mode}',0x4235032,getter,pg,0,rec,mode=mode);assert x['actual_length']==116 and x['locks']==['take','give']
  check(f'loader preserves full physical map {bits} mode{mode}',0x42a9d0a,loader,pg,0,rec[16:112],mode=mode)
 for bits in [(0,),(15,)]:check(f'directory badbit{bits} mode{mode}',0x42a9d0a,loader,pages(record(bits),mode),-1,unchanged=True,mode=mode)
 for label,rec in [('magic',record(**{'0':0})),('version',record(**{'4':2})),('base',record(**{'8':0x500000})),('reduced logical size',record(**{'12':0x200000})),('short',record()[:-1]),('long',record()+b'\0'),('CRC',record()[:-1]+bytes([record()[-1]^1]))]:
  check(f'loader rejects {label} mode{mode}',0x42a9d0a,loader,pages(rec,mode),-1,unchanged=True,mode=mode)
 check(f'corrupt KV header mode{mode}',0x4235032,getter,pages(record(),mode,corrupt_sector=True),4,unchanged=True,mode=mode)
check('KV mode2 payload integrity error',0x4235032,getter,pages(record(),2,corrupt_kv_crc=True),4,unchanged=True,mode=2)
x=check('KV mode1 invalid badmap is still copied',0x4235032,getter,pages(record(**{'0':0})),0,record(**{'0':0}));assert x['actual_length']==116
check('different key absent',0x4235032,getter,pages(record(),key=0x6008),7,unchanged=True)
check('getter uninitialized',0x4235032,getter,pages(),2,unchanged=True,initialized=False)
check('loader uninitialized fails not absent',0x42a9d0a,loader,pages(),-1,unchanged=True,initialized=False)
check('loader null output',0x42a9d0a,[0,0,96],pages(),-1,unchanged=True)
check('loader wrong map length',0x42a9d0a,[0,DST,95],pages(),-1,unchanged=True)
check('getter short capacity',0x4235032,[0x6009,DST,115,ACTUAL],pages(record()),13,unchanged=True)
check('getter zero capacity',0x4235032,[0x6009,DST,0,ACTUAL],pages(),13,unchanged=True)
check('getter null output',0x4235032,[0x6009,0,116,ACTUAL],pages(),13,unchanged=True)
check('getter null length output',0x4235032,[0x6009,DST,116,0],pages(),13,unchanged=True)
report={'passed':True,'cases':results,'case_count':len(results),'unicorn':u.__version__,'native_body_sha256':hashlib.sha256(BODY).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'max_stack_bytes':max(x['max_stack_bytes']for x in results),'actual_native_executed':['04235032 KV getter','0423463e sector iteration','04235554 cached KV base','042a9d0a badmap loader','042a9c84 CRC32','042a9cca physical bitmap validator','0434cc64/0434cc3a KV CRC8','native memcpy/memset'],'mocked':['RTOS mutex take/give; exact order checked','synthetic KV pages and initialized globals'],'limitations':['No real badmap acquired','No actual mutex contention/RTOS scheduling/XIP hardware tested','Known initialized base used; initializer/repair/write paths forbidden','No proof of cancellation or worst-case native interrupt stack'],'allocations':0,'flash_mutations':0,'global_state_writes':0}
(OUT/'emulation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'cases':len(results),'max_stack_bytes':report['max_stack_bytes']}))
