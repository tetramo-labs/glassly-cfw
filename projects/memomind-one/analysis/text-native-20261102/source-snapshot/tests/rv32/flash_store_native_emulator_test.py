#!/usr/bin/env python3
"""Execute the built production RV32 adapter; only four native calls are mocked."""
import argparse,hashlib,json,struct,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
BASE,END=0x700000,0x800000
CTX,MAP,DATA,DEST,CB,SP,RET=0x02080000,0x02081000,0x02082000,0x02083000,0x02084000,0x020ffe00,0x05000000
ARG,STATE,RANGE,BAD,ALIAS,VERIFY,BUSY=range(-19713,-19720,-1)
NATIVES={0x04329ad8:'read',0x04329b1e:'program',0x04329a14:'erase',0x04324bea:'cache'}
RESULTS=[]
def require(name,value):
 if not value:raise AssertionError(name)
 RESULTS.append(name)
class Machine:
 def __init__(self,build):
  self.layout=build['layout'];self.symbols=build['symbols']
  self.m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
  self.m.mem_map(0x04300000,0x100000,u.UC_PROT_READ|u.UC_PROT_EXEC)
  self.m.mem_write(0x043b0000,(BUILD/'adapter.bin').read_bytes())
  for address in NATIVES:self.m.mem_write(address,bytes.fromhex('67800000'))
  self.m.mem_map(0x02000000,0x100000)
  self.m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC);self.m.mem_write(RET,bytes.fromhex('67800000'))
  self.flash=bytearray(b'\xff'*0x100000);self.calls=[];self.fail_kind=None;self.fail_status=0;self.fail_read_at=0;self.read_count=0;self.corrupt=False;self.done=False
  self.m.hook_add(u.UC_HOOK_CODE,self.hook,begin=RET,end=RET)
  for address in NATIVES:self.m.hook_add(u.UC_HOOK_CODE,self.hook,begin=address,end=address)
  self.m.hook_add(u.UC_HOOK_MEM_WRITE,self.write_guard)
 def reg(self,i):return getattr(r,'UC_RISCV_REG_X'+str(i))
 def write_guard(self,mu,access,a,n,value,_):
  allowed=[(CTX,CTX+self.layout['context_bytes']),(DEST,DEST+256),(CB,CB+16),(SP-4096,SP)]
  if not any(lo<=a and n<=hi-a for lo,hi in allowed):raise AssertionError(('unexpected target write',hex(a),n))
 def hook(self,m,a,n,_):
  if a==RET:self.done=True;m.emu_stop();return
  kind=NATIVES[a];args=[m.reg_read(self.reg(i)) for i in range(10,14)];self.calls.append((kind,args))
  status=0
  if kind=='cache':
   assert args[0]==0 and 0x05700000<=args[1] and args[2]<=0x05800000-args[1]
  else:
   d,off=args[:2];size=args[2] if kind=='erase' else args[3]
   assert d==1 and BASE<=off<END and 0<size<=END-off
   local=off-BASE
   if kind=='read':
    assert args[2]==DEST or args[2]==CTX+self.layout['verification_offset']
    assert size<=256 and size<=256-(off&255)
    self.read_count+=1;raw=bytes(self.flash[local:local+size])
    if self.corrupt:raw=raw[:-1]+bytes([raw[-1]^1])
    m.mem_write(args[2],raw)
   elif kind=='program':
    assert args[2]==DATA
    assert size==256 and off%256==0
    data=bytes(m.mem_read(args[2],size));self.flash[local:local+size]=bytes(a&b for a,b in zip(self.flash[local:local+size],data))
   else:
    assert size==4096 and off%4096==0
    self.flash[local:local+size]=b'\xff'*size
   if kind==self.fail_kind and (kind!='read' or not self.fail_read_at or self.read_count==self.fail_read_at):status=self.fail_status
  m.reg_write(self.reg(10),status&0xffffffff);m.reg_write(r.UC_RISCV_REG_PC,m.reg_read(self.reg(1)))
 def clear(self):
  self.calls=[];self.fail_kind=None;self.fail_status=0;self.fail_read_at=0;self.read_count=0;self.corrupt=False
 def call(self,name,*args):
  self.done=False
  saved={i:0xabc00000+i for i in (8,9,18,19,20,21,22,23,24,25,26,27)}
  for i,v in {**saved,1:RET,2:SP,3:0x02011688,4:0x12345678,**{10+j:v for j,v in enumerate(args)}}.items():self.m.reg_write(self.reg(i),v)
  self.m.emu_start(self.symbols[name],0,count=500000)
  assert self.done,'instruction budget'
  for i,v in {**saved,2:SP,3:0x02011688,4:0x12345678}.items():assert self.m.reg_read(self.reg(i))==v,('preserved register',i)
  ret=self.m.reg_read(self.reg(10));return ret if ret<2**31 else ret-2**32
 def init(self,bitmap=bytes(32)):
  self.clear();self.m.mem_write(CTX,bytes(self.layout['context_bytes']));self.m.mem_write(MAP,bitmap)
  assert self.call('mm_flash_native_init',CTX,MAP)==0 and not self.calls
 def status(self):
  b=self.m.mem_read(CTX,self.layout['context_bytes'])
  return struct.unpack_from('<i',b,self.layout['status_offset'])[0],b[self.layout['phase_offset']],b[self.layout['busy_offset']]
def test(build):
 m=Machine(build);m.init();require('init-no-io',not m.calls)
 require('callback-bind',m.call('mm_flash_native_callbacks',CTX,CB)==0)
 require('callback-addresses',struct.unpack('<4I',m.m.mem_read(CB,16))==(CTX,m.symbols['mm_flash_native_read'],m.symbols['mm_flash_native_erase'],m.symbols['mm_flash_native_program']))
 for name,args,want in [
  ('mm_flash_native_init',(CTX,CTX+8),ALIAS),('mm_flash_native_init',(CTX,0),ARG),
  ('mm_flash_native_init',(CTX+1,MAP),ARG),('mm_flash_native_init',(0x05700000,MAP),ARG),
  ('mm_flash_native_init',(CTX,0x05700000),ARG),('mm_flash_native_init',(CTX,0x020ffff0),ARG),
  ('mm_flash_native_callbacks',(CTX,CTX),ALIAS),('mm_flash_native_callbacks',(CTX,0x05700000),ARG),
  ('mm_flash_native_read',(0,BASE,DEST,1),STATE)]:
  before=bytes(m.m.mem_read(CTX,300));require(name+str(args),m.call(name,*args)==want and not m.calls and bytes(m.m.mem_read(CTX,300))==before)
 for ptr in (0,0x01fffffc,0x02100000,0x020fff80,0x05700000,0x01700000,0xfffffffc):
  for name in ('mm_flash_native_read','mm_flash_native_program'):
   require('SRAM-'+name+hex(ptr),m.call(name,CTX,BASE,ptr,256)==ARG and not m.calls)
 for name in ('mm_flash_native_read','mm_flash_native_program'):
  require('context-alias-'+name,m.call(name,CTX,BASE,CTX+40,256)==ALIAS and not m.calls)
 for off in (0,BASE-1,END,0xffffffff):
  for name,n in [('mm_flash_native_read',1),('mm_flash_native_program',256),('mm_flash_native_erase',4096)]:
   args=(CTX,off,n) if name.endswith('erase') else (CTX,off,DATA,n)
   require('range-'+name+hex(off),m.call(name,*args)==RANGE and not m.calls)
 for off,n in [(BASE,0),(BASE,257),(BASE,0xffffffff),(BASE+255,2),(END-1,2)]:require('read-shape-'+str((off,n)),m.call('mm_flash_native_read',CTX,off,DEST,n)==RANGE and not m.calls)
 for name,off,n in [('mm_flash_native_program',BASE+1,256),('mm_flash_native_program',BASE,255),('mm_flash_native_erase',BASE+256,4096),('mm_flash_native_erase',BASE,8192)]:
  args=(CTX,off,n) if name.endswith('erase') else (CTX,off,DATA,n)
  require('shape-'+str(args),m.call(name,*args)==RANGE and not m.calls)
 for bit in range(256):
  bm=bytearray(32);bm[bit//8]=1<<(bit%8);m.init(bytes(bm));m.m.mem_write(MAP,bytes(32))
  off=BASE+bit*4096
  require('badbit-'+str(bit),m.call('mm_flash_native_read',CTX,off,DEST,1)==BAD and m.call('mm_flash_native_program',CTX,off,DATA,256)==BAD and m.call('mm_flash_native_erase',CTX,off,4096)==BAD and not m.calls)
 m.init();m.m.mem_write(DATA,bytes(range(256)))
 for sector in range(256):
  off=BASE+4096*sector;m.clear()
  require('erase-'+str(sector),m.call('mm_flash_native_erase',CTX,off,4096)==0)
  require('erase-order-'+str(sector),[x[0] for x in m.calls]==['erase','cache']+['read']*16 and m.calls[1][1][:3]==[0,0x05000000+off,4096])
  for page in (0,15):
   m.clear();o=off+page*256
   require('program-'+str((sector,page)),m.call('mm_flash_native_program',CTX,o,DATA,256)==0)
   require('program-order-'+str((sector,page)),[x[0] for x in m.calls]==['program','cache','read'] and m.calls[1][1][:3]==[0,0x05000000+o,256])
 m.clear();require('last-byte',m.call('mm_flash_native_read',CTX,END-1,DEST,1)==0 and bytes(m.m.mem_read(DEST,1))==b'\xff')
 for kind,name,args in [('read','mm_flash_native_read',(CTX,BASE,DEST,256)),('program','mm_flash_native_program',(CTX,BASE,DATA,256)),('erase','mm_flash_native_erase',(CTX,BASE,4096))]:
  for status in (-7,13):
   m.clear();m.fail_kind=kind;m.fail_status=status
   require('native-error-'+kind+str(status),m.call(name,*args)==status and m.status()[0]==status and m.status()[2]==0)
   require('error-order-'+kind+str(status),[x[0] for x in m.calls]==([kind] if kind=='read' else [kind,'cache']))
 for page in range(1,17):
  m.clear();m.fail_kind='read';m.fail_status=29;m.fail_read_at=page
  require('readback-error-'+str(page),m.call('mm_flash_native_erase',CTX,BASE,4096)==29 and m.read_count==page and m.status()==(29,4,0))
 for kind,name,args in [('program','mm_flash_native_program',(CTX,BASE,DATA,256)),('erase','mm_flash_native_erase',(CTX,BASE,4096))]:
  m.clear();m.corrupt=True
  require('mismatch-'+kind,m.call(name,*args)==VERIFY and m.status()==(0,4,0) and len(m.calls)==3)
 m.clear();m.m.mem_write(CTX+m.layout['busy_offset'],b'\1')
 for name,args in [('mm_flash_native_init',(CTX,MAP)),('mm_flash_native_callbacks',(CTX,CB)),('mm_flash_native_read',(CTX,BASE,DEST,1)),('mm_flash_native_program',(CTX,BASE,DATA,256)),('mm_flash_native_erase',(CTX,BASE,4096))]:require('busy-'+name,m.call(name,*args)==BUSY and not m.calls)
 return {'case_count':len(RESULTS),'all_sector_bits':256,'erase_sectors':256,'program_pages':512,'readback_faults':16}
def main():
 global u,r,BUILD
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();BUILD=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 report={'passed':False,'device_actions':False,'cases':RESULTS,'mocked_native_addresses':{hex(k):v for k,v in NATIVES.items()},'command':[sys.executable,*sys.argv]}
 status=1
 try:
  if not __debug__:raise RuntimeError('Assertions must be enabled')
  import unicorn
  from unicorn import riscv_const
  u,r=unicorn,riscv_const
  if u.__version__!='2.1.4':raise RuntimeError('Unicorn2.1.4 required')
  build=json.loads((BUILD/'build.json').read_text());report['build']=build
  for name,digest in build['source_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
  assert hashlib.sha256((BUILD/'adapter.bin').read_bytes()).hexdigest()==build['binary_sha256']
  report.update(test(build));report['passed']=True;report['unicorn']=u.__version__;status=0
 except Exception as exc:report.update(error=str(exc),traceback=traceback.format_exc())
 finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'passed':status==0,'checks':len(RESULTS),'report':str(out/'report.json')}));return status
if __name__=='__main__':raise SystemExit(main())
