#!/usr/bin/env python3
"""Reuse all original service/input gate cases with the ownership dispatch."""
import argparse,json
from pathlib import Path
import flash_canary_gate_emulator_test as C
G=C.G
class WakeGate(C.CanaryGate):
    def __init__(self,**kw):
        super().__init__(**kw)
        if self.command==0x79:self.expected_target=self.symbols['glassly_wake_command']
    def instruction(self,uc,address,size,userdata):
        if not self.csr_fixture_active and address==self.symbols['glassly_wake_command']:
            self.pcs.append(address);assert not self.display and self.command==0x79
            assert self.reg(2)==G.STACK and not self.boundary_seen
            self.assert_boundary_registers();self.boundary_seen=True;uc.emu_stop();return
        super().instruction(uc,address,size,userdata)
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',required=True,type=Path);p.add_argument('--report',required=True,type=Path);a=p.parse_args();G.BUILD=a.build.resolve()
    build=json.loads((G.BUILD/'build.json').read_text());assert build['wake_control']
    for request in (0,G.ENVELOPE):
        for command in range(256):WakeGate(command=command,request=request).run()
    for cls in range(256):
        for event in (0,*C.inputs.BUTTONS,*C.inputs.IMU,0x474c,0xffff):WakeGate(class_byte=cls,event=event).run()
    for cls in (2,3,0x42,0x43,0x82,0x83,0xc2,0xc3):
        for length in (1,255,256,65535):
            for event in (*C.inputs.BUTTONS,*C.inputs.IMU):WakeGate(class_byte=cls,event=event,length=length).run()
        for event in (9,0x1f7a,0x1f80,0x1faf,0x1fba,0xfffe):WakeGate(class_byte=cls,event=event).run()
    for cls in (2,3,63):WakeGate(class_byte=cls,event=1,null_envelope=True).run()
    a.report.write_text(json.dumps({'passed':True,'runtimeSHA256':build['blob_sha256'],'cases':len(C.inputs.RESULTS),
        'serviceGateSlotBytes':64,'inputObserverGateStackBytes':144,'nativeAndCMocked':True,'hardwareTested':False},indent=2)+'\n')
if __name__=='__main__':main()
