#!/usr/bin/env python3
"""Execute ANCS service dispatch and actual pre-stock callsite in RV32."""
import argparse,json,struct
from pathlib import Path
import wake_control_gate_emulator_test as W
G=W.G
class NotificationGate(W.WakeGate):
    def __init__(self,**kw):
        super().__init__(**kw)
        if self.command==0x78:self.expected_target=self.symbols['glassly_notification_command']
    def instruction(self,uc,address,size,userdata):
        if not self.csr_fixture_active and address==self.symbols['glassly_notification_command']:
            assert self.command==0x78 and not self.display
            self.assert_boundary_registers();self.boundary_seen=True;uc.emu_stop();return
        super().instruction(uc,address,size,userdata)
def prestock(build,alignment,event):
    data=json.loads((build/'build.json').read_text());symbols=data['symbols'];blob=(build/'graphics.bin').read_bytes()
    uc=G.u.Uc(G.u.UC_ARCH_RISCV,G.u.UC_MODE_RISCV32)
    base=G.ENTRY&~4095;uc.mem_map(base,((G.ENTRY+len(blob)+4095)&~4095)-base);uc.mem_write(G.ENTRY,blob)
    site=0x04217568;stock=0x04319792;sp=0x03001000-alignment
    for page in (site&~4095,stock&~4095,0x03000000):uc.mem_map(page,4096)
    uc.mem_write(stock,bytes.fromhex("67800000"))
    uc.mem_write(site,G.pc_relative_call(site,symbols['glassly_notification_entry']))
    def read(i):return uc.reg_read(getattr(G.r,f'UC_RISCV_REG_X{i}'))
    def write(i,n):uc.reg_write(getattr(G.r,f'UC_RISCV_REG_X{i}'),n)
    for i in range(1,32):write(i,0x10000000+i)
    write(2,sp);write(10,event);write(11,0x02060000);write(12,16)
    saved={i:read(i) for i in range(1,32)};seen=[]
    def hook(uc,address,size,_):
        if address==symbols['glassly_notification_observe']:
            assert read(2)%16==0
            assert [read(i) for i in (10,11,12)]==[saved[i] for i in (10,11,12)]
            ret=read(1)
            for i in (1,5,6,7,*range(10,18),*range(28,32)):write(i,0xb0000000+i)
            uc.reg_write(G.r.UC_RISCV_REG_PC,ret);seen.append('observe')
        if address==stock:
            assert read(1)==site+8 and read(2)==sp
            for i in (3,4,8,9,*range(10,28)):assert read(i)==saved[i],i
            seen.append('stock');uc.emu_stop()
    uc.hook_add(G.u.UC_HOOK_CODE,hook);uc.emu_start(site,0,count=1000)
    assert seen==['observe','stock']
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();G.BUILD=a.build.resolve()
    data=json.loads((G.BUILD/'build.json').read_text());assert data['notification_relay']
    for command in range(256):
        for request in (0,G.ENVELOPE):NotificationGate(command=command,request=request).run()
    for alignment in (0,8):
        for event in (0,0x258,0x259,0x25a,0x25b,0x280,0x28f):prestock(G.BUILD,alignment,event)
    a.report.write_text(json.dumps({'passed':True,'serviceCases':512,'prestockCases':14,'runtimeSHA256':data['blob_sha256'],'nativeAndObserverMocked':True,'hardwareTested':False},indent=2)+'\n')
if __name__=='__main__':main()
