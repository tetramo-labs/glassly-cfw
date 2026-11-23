#!/usr/bin/env python3
"""Run patched stock manager/calibration entry points and actual RV32 veneers."""
import argparse,json,struct,sys,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
from minimal_owner_flash_runtime_emulator_test import FlashMachine
sys.path.insert(0,str(G.ROOT/'scripts'))
from memomind_ota import unpack_ota,sha
from build_memomind_minimal_owner import CALLBACKS,BOUNDARIES,BODY_BASE
G.NATIVES.update({0x04282764:'calibration',0x0425e07c:'leave_app',0x042c8832:'local_style'})
BODY=b''
STOCK_RANGES=((0x0425db94,0x0425dcb6),(0x0427253a,0x04272542),(0x04272664,0x04272698),(0x04272960,0x04272968),(0x04273ee6,0x04273f3a),(0x042c8fe2,0x042c900c))
class Machine(FlashMachine):
 def __init__(self):
  self.calibration_result=0;self.calibrations=[];self.leaves=0
  super().__init__()
  existing={p for lo,hi,_ in self.uc.mem_regions() for p in range(lo,hi+1,4096)}
  for p in range(BODY_BASE&~4095,(BODY_BASE+len(BODY)+4095)&~4095,4096):
   if p not in existing:self.uc.mem_map(p,4096,G.u.UC_PROT_READ|G.u.UC_PROT_EXEC)
  self.uc.mem_write(BODY_BASE,BODY)
  existing={p for lo,hi,_ in self.uc.mem_regions() for p in range(lo,hi+1,4096)}
  for p in range(0x0200f000,0x02016000,4096):
   if p not in existing:self.uc.mem_map(p,4096,G.u.UC_PROT_READ|G.u.UC_PROT_WRITE)
  self.uc.mem_write(0x0200fc7c,BODY[0x0439a38c-BODY_BASE:0x0439a3c8-BODY_BASE])
  # Deliberately poison the old root/header object pointers. No path may read
  # or forward them to LVGL after the cold-boot lifecycle replacement.
  self.uc.mem_write(0x0200fc40,struct.pack('<II',0xdeadbeef,0xdeaddead))
  for a,v in [(0x02011ce8,0x0200fc7c),(0x02011cec,0x0200fc7c),(0x02011650,0),(0x020155fc,0x0200fc7c)]:self.uc.mem_write(a,struct.pack('<I',v))
  self.uc.mem_write(0x0200fcb0,b'\x01');self.uc.mem_write(0x02011cf0,b'\x01')
 def region(self,address,size,writing=False):
  if 0x0200f000<=address and address+size<=0x02016000:
   assert not (address<0x0200fc48 and address+size>0x0200fc40),'Old dashboard object access'
   return 'reviewed-native-state'
  if not writing and BODY_BASE<=address and address+size<=BODY_BASE+len(BODY):return 'patched-app'
  return super().region(address,size,writing)
 def return_native(self,value=0):
  continuation=self.reg(1)
  if any(lo<=continuation<hi for lo,hi in STOCK_RANGES):
   for i in G.CALLER:self.set(i,0xd0000000+i*0x101)
   self.set(10,value);self.uc.reg_write(G.r.UC_RISCV_REG_PC,continuation);return
  return super().return_native(value)
 def instruction(self,uc,address,size,userdata):
  if any(lo<=address<hi for lo,hi in STOCK_RANGES):
   assert self.stack_base<=self.reg(2)<=self.stack_top and self.reg(2)%8==0
   self.instructions+=1;self.min_sp=min(self.min_sp,self.reg(2));return
  entries=[self.symbols['glassly_launcher_'+n+'_entry'] for n in ('init','destroy','tick','event','message','home','suspend')]
  if self.reg(2)%16==8 and any(a<=address<a+32 for a in entries):
   assert self.stack_base<=self.reg(2)<=self.stack_top;self.instructions+=1;return
  return super().instruction(uc,address,size,userdata)
 def native(self,name,args):
  if name=='local_style':
   assert args[:4]==(self.parent,0x20,0,0),args[:4]
   self.background=0;self.background_calls+=1;return 0
  if name=='calibration':
   assert args[0] in (0x5000,0x5001) and args[2]==0 and args[3]==0x0427253a
   self.calibrations.append(args[:4]);return self.calibration_result
  if name=='leave_app':self.leaves+=1;return 0
  return super().native(name,args)
class Tests(unittest.TestCase):
 def test_manager_routes_calibration_and_poisoned_old_objects(self):
  m=Machine()
  for name,a in [('manager_tick',0x0425db94),('manager_event',0x0425dbfc),('home',0x0427253a),('calibration',0x04273ee6),('status',0x04272664),('overlay',0x0427267a)]:m.symbols[name]=a
  for address,_,name in CALLBACKS:
   target=int.from_bytes(BODY[address-BODY_BASE:address-BODY_BASE+4],'little');self.assertEqual(target,m.symbols['glassly_launcher_'+name+'_entry'])
   m.call(target,0x0200fc7c,0x8877,0xdeaddead,0,display=True)
  self.assertEqual(m.background_calls,1);self.assertEqual(m.background,0)
  for _ in range(2):
   m.call('manager_tick',display=True)
   for kind in (0,1,2,3,0xffff):
    m.call('manager_event',kind,0xdeadbeef,display=True);self.assertEqual(m.reg(10),0)
   m.call('home',123,display=True)
   for n in ('status','overlay'):m.call(n,display=True);self.assertEqual(m.reg(10),0)
   for status in (0,1):
    m.calibration_result=status
    for kind in (0x5000,0x5001):m.call('calibration',kind,0x8888,display=True)
   m.call('calibration',0x5002,0x8888,display=True)
  self.assertEqual(len(m.calibrations),8);self.assertEqual(m.leaves,4)
  self.assertFalse(m.images or m.timers or m.owned_live())
  m.welcome=True;m.call('home',77,display=True);self.assertEqual(m.welcomes,[77])
def main():
 global BODY
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 G.BUILD=a.build.resolve();b=json.loads((G.BUILD/'build.json').read_text());G.PINNED_SHA=b['blob_sha256'];G.RESULTS.clear()
 image=a.image.read_bytes();BODY=unpack_ota(image)[1][3]['raw'][32:]
 assert BODY[G.ENTRY-BODY_BASE:G.ENTRY-BODY_BASE+b['blob_bytes']]==(G.BUILD/'graphics.bin').read_bytes()
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 a.report.write_text(json.dumps({'passed':result.wasSuccessful(),'image_sha256':sha(image),'calls':G.RESULTS,'old_objects_poisoned':True,'hardware_tested':False,'limitations':['Native calibration operation and app exit mocked; actual manager, flag getters, patched external entries and veneers executed.']},indent=2)+'\n');return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
