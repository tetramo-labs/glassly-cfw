#!/usr/bin/env python3
"""Execute 46 reviewed external-store reservation checks on pinned native RV32 code.

All flash/KV/controller effects are mocked; no firmware or hardware is changed.
The 1 MiB profile must equal the production constructor; 512 KiB is reference
coverage only. Requires Unicorn 2.1.4 and a new --output directory.
"""
import argparse, hashlib, json, struct, sys, traceback
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin'
APP_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
RECIPE = ROOT / 'analysis/ghidra/external-reservation-review/candidate-recipes.json'
RECIPE_SHA = '74d8bcd758289f246113b8593e91c42899640f8fedd8236de977396cd8553bd0'
BASELINE = ROOT / 'analysis/ghidra/external-reservation-review/boundary-tests.json'
BASELINE_SHA = '20fc9bbd9d867d5b0edf224b4deb64ec507996df530c7e40acc8127e7a1e0db2'
BASE = 0x041eb020
ORIGINAL = None
CONSTRUCTOR_PATCHES = None

def sha(data): return hashlib.sha256(data).hexdigest()

def mount(data, cap, bm=bytes(96), change=True):
 body = patched(cap)[0] if change else ORIGINAL
 return native_mount(data, body, cap, bm)[0]['return_code']

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
 if cap == 0x200000:
  actual = tuple((int(row['address'], 16), row['before'], row['after'], row['purpose']) for row in rows)
  assert actual == CONSTRUCTOR_PATCHES, 'source-derived edits differ from constructor PATCHES'
 return bytes(b),rows

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
  check(prefix+f' wipe boundary badpage{badpage}',ret==0 and total==cap-(4096 if badpage is not None else 0) and max(a+n for a,n in erases)==0x500000+cap,erase_ranges=erases,callback_hook_events=steps)
 return {'logical_native_capacity':cap,'reserved_bytes':0x300000-cap,'patch_sites':rows,'in_memory_patched_body_sha256':sha(body)}

def main():
 global ORIGINAL, CONSTRUCTOR_PATCHES, u, r, native_mount
 parser = argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output', required=True, type=Path, help='New output directory; existing paths are rejected')
 args = parser.parse_args()
 out = args.output.resolve()
 frozen = ROOT / 'analysis/ghidra'
 if out == frozen or frozen in out.parents:
  parser.error('Output must be outside frozen analysis/ghidra evidence')
 try:
  out.mkdir(parents=True, exist_ok=False)
 except FileExistsError:
  parser.error('Output directory already exists; choose a new path')
 report = dict(format='memomind-external-reservation-emulation-v1', all_passed=False,
               no_hardware_calls=True, native_image_output_written=False,
               command=[sys.executable, *sys.argv], python=sys.version,
               expected_cases=46, cases=RESULTS, provenance={},
               limitations=[
                'Synthetic directory, badmap, flash, KV, cache and synchronization callbacks; no physical hardware, concurrency or power-loss proof.',
                '512 KiB profile is reviewed reference coverage, not constructor eligibility.',
                'All eleven instruction witnesses are checked; these cases do not exercise every mount/format/compaction/package-verifier path.',
                'Passing tests do not reserve storage or prove OTA/recovery survival.'])
 status = 1
 try:
  if not __debug__: raise RuntimeError('Assertions must be enabled (do not use python -O)')
  import unicorn
  from unicorn import riscv_const
  u, r = unicorn, riscv_const
  report['unicorn'] = u.__version__
  if u.__version__ != '2.1.4': raise RuntimeError('Required Unicorn version is exactly 2.1.4')
  from native_store_mount import native_mount as mount_impl
  native_mount = mount_impl
  for path, expected in [(APP, APP_SHA), (RECIPE, RECIPE_SHA), (BASELINE, BASELINE_SHA)]:
   digest = sha(path.read_bytes())
   report['provenance'][str(path.relative_to(ROOT))] = digest
   if digest != expected: raise RuntimeError('Pinned source mismatch: ' + str(path))
  ORIGINAL = APP.read_bytes()
  sys.path.insert(0, str(ROOT / 'scripts'))
  import build_memomind_storage as constructor
  if constructor.FORMAT != 'memomind-external-store-runtime-v1':
   raise RuntimeError('Unexpected constructor format')
  CONSTRUCTOR_PATCHES = constructor.PATCHES
  reviewed = json.loads(RECIPE.read_text())
  one_mib = next(p for p in reviewed['profiles'] if p['logical_native_capacity'] == 0x200000)
  expected = tuple((int(p['address'], 16), p['before'], p['after'], p['purpose']) for p in one_mib['patch_sites'])
  if CONSTRUCTOR_PATCHES != expected or len(expected) != 11:
   raise RuntimeError('Constructor PATCHES differ from reviewed eleven-site recipe')
  report['constructor_format'] = constructor.FORMAT
  for path in [Path(__file__).resolve(), Path(__file__).with_name('native_store_mount.py'), Path(constructor.__file__)]:
   report['provenance'][str(path.relative_to(ROOT))] = sha(path.read_bytes())
  profiles = []
  for capacity in (0x280000, 0x200000):
   profile = run(capacity)
   profile['role'] = 'constructor-required' if capacity == 0x200000 else 'reviewed-reference'
   original_profile = next(p for p in reviewed['profiles'] if p['logical_native_capacity'] == capacity)
   if profile['patch_sites'] != original_profile['patch_sites'] or profile['in_memory_patched_body_sha256'] != original_profile['in_memory_patched_body_sha256']:
    raise RuntimeError('Patched native bytes differ from reviewed profile')
   profiles.append(profile)
  names = [case['case'] for case in RESULTS]
  baseline_names = [case['case'] for case in json.loads(BASELINE.read_text())['cases']]
  if len(names) != 46 or len(set(names)) != 46 or names != baseline_names:
   raise RuntimeError('Original 46-case coverage/order changed')
  report.update(all_passed=True, case_count=len(RESULTS), profiles=profiles,
                constructor_cases=23, reference_cases=23, original_case_inventory_preserved=True)
  status = 0
 except Exception as exc:
  report.update(error=str(exc), traceback=traceback.format_exc(), case_count=len(RESULTS))
 finally:
  (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
 print(('PASS' if status == 0 else 'FAIL') + ': ' + str(len(RESULTS)) + '/46 external reservation cases; ' + str(out / 'report.json'))
 return status

if __name__ == '__main__':
 raise SystemExit(main())
