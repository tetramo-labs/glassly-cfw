#!/usr/bin/env python3
"""Actual canary service/display/input gates; C entry bodies are mocked."""
import argparse,hashlib,json
from pathlib import Path
import flash_read_gate_emulator_test as F
inputs=F.inputs;G=F.G
BUILD=F.ROOT/'runtime/build/flash-canary-004'
PINNED_SHA='c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992'
class CanaryGate(F.FlashGate):
 def __init__(self,**kw):
  super().__init__(**kw)
  if self.command==0x7a:self.expected_target=self.symbols['glassly_flash_canary_command_entry']
 def instruction(self,uc,address,size,userdata):
  if not self.csr_fixture_active and address==self.symbols['glassly_flash_canary_command_entry']:
   self.pcs.append(address);assert not self.display and self.command==0x7a
   assert self.reg(2)==G.STACK and not self.boundary_seen
   self.assert_boundary_registers();self.boundary_seen=True;uc.emu_stop();return
  super().instruction(uc,address,size,userdata)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path);a=p.parse_args();G.BUILD=a.build.resolve()
 b=json.loads((G.BUILD/'build.json').read_text());assert b['flash_canary'] and b['full_store_reader'];assert hashlib.sha256((G.BUILD/'graphics.bin').read_bytes()).hexdigest()==PINNED_SHA
 assert G.u.__version__=='2.1.4';inputs.RESULTS.clear()
 for req in (0,G.ENVELOPE):
  for cmd in range(256):CanaryGate(command=cmd,request=req).run()
 for cls in range(256):
  for event in (0,*inputs.BUTTONS,*inputs.IMU,0x474c,0xffff):CanaryGate(class_byte=cls,event=event).run()
 for cls in (2,3,0x42,0x43,0x82,0x83,0xc2,0xc3):
  for length in (1,255,256,65535):
   for event in (*inputs.BUTTONS,*inputs.IMU):CanaryGate(class_byte=cls,event=event,length=length).run()
  for event in (9,0x1f7a,0x1f80,0x1faf,0x1fba,0xfffe):CanaryGate(class_byte=cls,event=event).run()
 for cls in (2,3,63):CanaryGate(class_byte=cls,event=1,null_envelope=True).run()
 report={'passed':True,'build':str(G.BUILD),'blob_sha256':PINNED_SHA,'cases':len(inputs.RESULTS),'service_gate_bytes':60,'ordinary_service_stack_bytes':0,'input_observer_gate_stack_bytes':144,'architecture':'actual RV32 Unicorn2.1.4','native_and_C_mocked':True,'device_actions':False,'results':inputs.RESULTS}
 if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='results'}))
if __name__=='__main__':main()
