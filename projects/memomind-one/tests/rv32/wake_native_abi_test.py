#!/usr/bin/env python3
"""Execute stock wake guards/getters through the new native wrappers."""
import argparse,json,struct,sys
from pathlib import Path
import graphics_runtime_emulator_test as G
sys.path.insert(0,str(G.ROOT/'scripts'))
from memomind_ota import unpack_ota,sha
from build_memomind_graphics import BODY_BASE as BASE
RANGES=((0x042a88a8,0x042a88d0),(0x0425f99e,0x0425f9e8),(0x0425f9f8,0x0425fa08))
G.NATIVES.update({0x042604ea:'wake_delay',0x0425f91c:'driver_wake',0x042ae15a:'driver_off',0x0200ec3a:'display_lock',0x0200ecb2:'display_unlock'})
BODY=b''
class Machine(G.Machine):
    def __init__(self):
        super().__init__();self.power_on=False;self.power_calls=[]
        pages={p for low,high,_ in self.uc.mem_regions() for p in range(low,high+1,4096)}
        for p in range(BASE&~4095,(BASE+len(BODY)+4095)&~4095,4096):
            if p not in pages:self.uc.mem_map(p,4096,G.u.UC_PROT_READ|G.u.UC_PROT_EXEC)
        self.uc.mem_write(BASE,BODY)
        for p in (0x0200f000,0x02011000):
            if p not in pages:self.uc.mem_map(p,4096,G.u.UC_PROT_READ|G.u.UC_PROT_WRITE)
    def region(self,address,size,writing=False):
        if any(lo<=address and address+size<=hi for lo,hi in ((0x0200fb64,0x0200fb68),(0x02011cf9,0x02011cfa))):return 'native-display-state'
        if not writing and BASE<=address and address+size<=BASE+len(BODY):return 'stock-code'
        return super().region(address,size,writing)
    def return_native(self,value=0):
        continuation=self.reg(1)
        assert any(lo<=continuation<hi for lo,hi in RANGES) or G.ENTRY<=continuation<G.ENTRY+len(self.blob) or continuation==G.RET
        for index in G.CALLER:self.set(index,0xd0000000+index*0x101)
        self.set(10,value);self.uc.reg_write(G.r.UC_RISCV_REG_PC,continuation)
    def instruction(self,uc,address,size,userdata):
        if any(lo<=address<hi for lo,hi in RANGES):
            self.instructions+=1;sp=self.reg(2)
            assert self.stack_base<=sp<=self.stack_top and sp%16==0
            self.min_sp=min(self.min_sp,sp);return
        return super().instruction(uc,address,size,userdata)
    def native(self,name,args):
        if name=='wake_delay':assert args[0]==200;self.power_calls.append(name);return 0
        if name=='driver_wake':self.power_on=True;self.power_calls.append(name);return 0
        if name=='driver_off':self.power_calls.append(name);return int(not self.power_on)
        if name in ('display_lock','display_unlock'):assert args[0]==0x1234;self.power_calls.append(name);return 1
        return super().native(name,args)
def main():
    global BODY
    p=argparse.ArgumentParser();p.add_argument('--build',required=True,type=Path);p.add_argument('--image',required=True,type=Path);p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    G.BUILD=a.build.resolve();G.PINNED_SHA=json.loads((G.BUILD/'build.json').read_text())['blob_sha256']
    _,parts=unpack_ota(a.image.read_bytes());BODY=parts[3]['raw'][32:]
    stock=(G.ROOT/'captures/firmware/ota-1.0.3.127-jhv3_release.bin').read_bytes();assert sha(stock)=='08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712'
    original=unpack_ota(stock)[1][3]['raw'][32:]
    for lo,hi in RANGES:assert BODY[lo-BASE:hi-BASE]==original[lo-BASE:hi-BASE]
    cases=0
    for blocked in (0,1,255):
        for mutex in (0,0x1234):
            for power in (False,True):
                m=Machine();m.uc.mem_write(0x02011cf9,bytes([blocked]));m.uc.mem_write(0x0200fb64,struct.pack('<I',mutex));m.power_on=power
                m.call('glassly_wake_native_blocked',display=True);assert m.reg(10)==int(bool(blocked))
                m.call('glassly_wake_native_on_state',display=True);assert m.reg(10)==int(power)
                assert m.power_calls==(['display_lock','driver_off','display_unlock'] if mutex else ['driver_off'])
                m.power_calls=[];m.call('glassly_wake_native_on',display=True)
                assert m.power_calls==([] if blocked else ['wake_delay','driver_wake']);cases+=1
    a.report.write_text(json.dumps({'passed':True,'cases':cases,'runtimeSHA256':G.PINNED_SHA,'actualStockRanges':RANGES,
        'stockRangesSHA256':[sha(BODY[lo-BASE:hi-BASE]) for lo,hi in RANGES],'hardwareTested':False,
        'mockBoundaries':['Display driver state/wake','Display mutex','Wake delay request'],'calls':G.RESULTS},indent=2)+'\n')
if __name__=='__main__':main()
