#!/usr/bin/env python3
"""Analysis-only in-memory native patch experiments. Emits no firmware image."""
import hashlib,importlib.util,json,struct,sys
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('inventory',ROOT/'analysis/ghidra/native-store-inventory/inventory.py');inv=importlib.util.module_from_spec(spec);spec.loader.exec_module(inv)
BASE=0x041eb020;ORIGINAL=inv.APP.read_bytes();assert inv.sha(ORIGINAL)==inv.APP_SHA
SITES={0x042a44d8:'primary mount capacity',0x042a4516:'repair mount capacity',0x042a452a:'format capacity',0x042a4572:'advisory empty-context capacity',0x042a3e20:'read callback bound',0x042a40c4:'program callback bound',0x042a411e:'erase callback bound',0x042a41ae:'package verifier bound',0x0423e9be:'whole-store wipe end',0x0423ea4a:'whole-store wipe block remainder'}

def patched(cap):
 assert cap in (0x200000,0x280000)
 b=bytearray(ORIGINAL);rows=[]
 for a,why in SITES.items():
  w=struct.unpack_from('<I',b,a-BASE)[0];assert w&0x7f==0x37 and w&0xfffff000==0x300000
  n=(w&0xfff)|cap;old=b[a-BASE:a-BASE+4];b[a-BASE:a-BASE+4]=struct.pack('<I',n)
  rows.append({'address':hex(a),'before':old.hex(),'after':struct.pack('<I',n).hex(),'purpose':why})
 a=0x042a0998;old=b[a-BASE:a-BASE+4];assert old.hex()=='63ee2701'
 # Skip bit check for sectors16..767; directory-sector guard and physical96B map remain.
 new=bytes.fromhex('6f00c001');b[a-BASE:a-BASE+4]=new
 rows.append({'address':hex(a),'before':old.hex(),'after':new.hex(),'purpose':'physical badmap validity independent of reduced logical capacity; JAL zero,+28'})
 return bytes(b),rows

class Bytes:
 def __init__(self,b):self.b=b
 def read_bytes(self):return self.b

def mount(data,cap,bm=bytes(96),change=True):
 old=(inv.APP,inv.APP_SHA,inv.CAPACITY)
 body=patched(cap)[0] if change else ORIGINAL
 try:
  inv.APP,inv.APP_SHA,inv.CAPACITY=Bytes(body),inv.sha(body),cap
  return inv.native_mount(data,bm)[0]['return_code']
 finally:inv.APP,inv.APP_SHA,inv.CAPACITY=old

def directory(cap,offset=None):
 b=bytearray(b'\xff'*65536);s=bytearray(0xff8)
 struct.pack_into('<12I',s,0,0x47534331,4,1,0,0,0,cap,0x10000,0,0,0,0)
 if offset is not None:
  s[48:53]=b'test\0';struct.pack_into('<7I',s,48+0x60,1,4096,0x100,offset,4096,0,2)
 import zlib
 struct.pack_into('<I',s,0xff0,zlib.crc32(s[:0xff0]));b[:len(s)]=s;struct.pack_into('<I',b,0x1ffc,0x434f4d54)
 return bytes(b)

def machine_call(body,entry,args,stubs,setup=None):
 m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32);m.mem_map(0x041eb000,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(BASE,body)
 m.mem_map(0x02000000,0x100000);m.mem_write(0x02000000,body[0x64:0x64+0xf8b4]);o=0x4399fc8-BASE;m.mem_write(0x0200f8b8,body[o:o+0x1e78])
 m.mem_map(0x03000000,0x10000);m.mem_map(0x05000000,4096,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(0x05000000,bytes.fromhex('67800000'))
 reg=lambda i:getattr(r,'UC_RISCV_REG_X'+str(i))
 for i,v in {1:0x05000000,2:0x0300fff0,3:0x02011688,**{10+j:v for j,v in enumerate(args)}}.items():m.reg_write(reg(i),v)
 if setup:setup(m)
 calls=[];done=False;steps=0
 def hook(mu,a,n,_):
  nonlocal done,steps
  steps+=1
  if a==0x05000000:done=True;mu.emu_stop();return
  if a in stubs:
   vals=[mu.reg_read(reg(i)) for i in range(10,14)];calls.append({'address':hex(a),'args':vals})
   status=stubs[a](mu,vals);mu.reg_write(reg(10),status&0xffffffff);mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(reg(1)))
 
 for address in (0x05000000,*stubs):m.hook_add(u.UC_HOOK_CODE,hook,begin=address,end=address)
 m.emu_start(entry,0,count=40000000)
 assert done,'instruction budget';ret=m.reg_read(reg(10));return ret if ret<2**31 else ret-2**32,calls,steps

RESULTS=[]
def check(name,condition,**detail):
 assert condition,name;RESULTS.append({'case':name,'passed':True,**detail})

def run(cap):
 body,rows=patched(cap);prefix=hex(cap)
 erased=b'\xff'*65536
 check(prefix+' erased mount',mount(erased,cap)==-1)
 check(prefix+' reduced valid directory',mount(directory(cap),cap)==0)
 check(prefix+' old3MiB directory fails',mount(directory(0x300000),cap)==-8)
 check(prefix+' last plugin page valid',mount(directory(cap,cap-4096),cap)==0)
 check(prefix+' first reserved page rejected',mount(directory(cap,cap),cap)==-8)
 bm=bytearray(96);bm[95]=0x80
 check(prefix+' stock rejects reserved genuine badbit',mount(erased,cap,bytes(bm),False)==-3)
 check(prefix+' patch preserves reserved genuine badbit',mount(erased,cap,bytes(bm))==-1)
 bm[0]=1;check(prefix+' directory badbit still rejected',mount(erased,cap,bytes(bm))==-3)
 bm=bytearray(96);idx=(cap-4096)//4096;bm[idx//8]|=1<<(idx%8)
 check(prefix+' active badbit still rejects entry',mount(directory(cap,cap-4096),cap,bytes(bm))==-8)
 for entry,target,kind in [(0x042a3e20,0x04329ad8,'read'),(0x042a40c4,0x04329b1e,'program'),(0x042a411e,0x04329a14,'erase')]:
  for off,n,ok in [(cap-4096,4096,True),(cap,4096,False),(cap-256,512,False),(0xffffffff,4096,False)]:
   args=[0,off,n] if kind=='erase' else [0,off,0x03001000,n]
   ret,calls,steps=machine_call(body,entry,args,{target:lambda m,a:0,0x04324bea:lambda m,a:0})
   io=[x for x in calls if int(x['address'],16)==target]
   check(prefix+f' {kind} {off:x}+{n}',(ret==0)==ok and bool(io)==ok,calls=io)
 # Full native reset dry run. Every external operation is an explicit local stub.
 for badpage in (None,0x10000):
  bitmap=bytearray(96)
  if badpage is not None:bitmap[badpage//4096//8]|=1<<(badpage//4096%8)
  def bad(m,a):assert a[2]==96;m.mem_write(a[1],bytes(bitmap));return 0
  def read(m,a):assert a[0]==1 and 0x500000<=a[1] and a[3]<=0x500000+cap-a[1];m.mem_write(a[2],b'\xff'*a[3]);return 0
  def erase(m,a):assert a[0]==1 and 0x500000<=a[1] and a[2]<=0x500000+cap-a[1];return 0
  def kv(m,a):assert a[0]==0x6008 and a[2]==12;return 0
  stubs={0x0200a23a:lambda m,a:0,0x0200a264:lambda m,a:0,0x0429bd4c:lambda m,a:0,0x0423e7f4:lambda m,a:1,0x0423e75a:lambda m,a:1,0x042a9d0a:bad,0x04234b5c:kv,0x04329a14:erase,0x04329ad8:read,0x04324bea:lambda m,a:0}
  ret,calls,steps=machine_call(body,0x0423e8b4,[1],stubs)
  erases=[x['args'][1:3] for x in calls if x['address']=='0x4329a14'];total=sum(x[1] for x in erases)
  check(prefix+f' wipe boundary badpage{badpage}',ret==0 and total==cap-(4096 if badpage is not None else 0) and max(a+n for a,n in erases)==0x500000+cap,erase_ranges=erases,steps=steps)
 return {'logical_native_capacity':cap,'reserved_bytes':0x300000-cap,'patch_sites':rows,'in_memory_patched_body_sha256':inv.sha(body)}

if __name__=='__main__':
 profiles=[run(c) for c in (0x280000,0x200000)]
 (HERE/'candidate-recipes.json').write_text(json.dumps({'stock_body_sha256':inv.APP_SHA,'not_applied_to_any_firmware':True,'profiles':profiles},indent=2)+'\n')
 (HERE/'boundary-tests.json').write_text(json.dumps({'unicorn':u.__version__,'cases':RESULTS,'all_passed':True,'no_hardware_calls':True,'native_image_output_written':False},indent=2)+'\n')
 print('Passed',len(RESULTS),'in-memory native boundary checks')
