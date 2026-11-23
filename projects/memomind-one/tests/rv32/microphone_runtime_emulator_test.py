#!/usr/bin/env python3
"""Linked microphone controls and transport veneers; native audio APIs are mocks."""
import argparse, hashlib, json, struct, unittest, sys
from pathlib import Path
import graphics_runtime_emulator_test as G
from flash_canary_runtime_emulator_test import CanaryMachine, REGISTRY
G.NATIVES.update({0x0200f6e8:'mic_clock',0x042361b8:'mic_post',0x042363f4:'mic_timer',
    0x04236404:'mic_cancel',0x04209de8:'mic_format',0x0420a316:'mic_start',
    0x0420a232:'mic_stop',0x04209998:'mic_reset'})
PEER=bytes(range(1,7))
UUID=bytes.fromhex('040000000000202400001000800000805f9b34fb')
CONFIG=b'MC\1\1'+bytes([0,1,3,0,160,0,160,0,2])
class MicrophoneMachine(CanaryMachine):
    def __init__(self):
        super().__init__();self.jobs=[];self.watch=None;self.app=False;self.starts=0;self.stops=0
        self.post_error=self.timer_error=self.stop_error=0;self.delayed=False
        for page in (0x02011000,0x02012000,0x02013000):self.uc.mem_map(page,4096)
        self.uc.mem_write(0x02013c7c,b'\1\0\4\0');self.uc.mem_write(0x02013c83,PEER)
    def region(self,address,size,writing=False):
        if REGISTRY+160<=address and address+size<=REGISTRY+208:
            if writing:assert self.critical
            return 'microphone-registry'
        if any(lo<=address and address+size<=hi for lo,hi in ((0x02011968,0x0201196d),(0x020127e0,0x020127e6),(0x02013c7c,0x02013c96))):
            if writing:assert self.app
            return 'native-recording-state'
        return super().region(address,size,writing)
    def native(self,name,args):
        if name.startswith('mic_'):
            assert not self.critical
            if name=='mic_clock':return self.now
            if name=='mic_post':
                assert args[:2]==(0x13,0x290)
                if not self.post_error:self.jobs.append(self.read(args[2],args[3]))
                return self.post_error
            assert self.app
            if name=='mic_timer':
                assert args[:2]==(0x13,0x291) and args[3:5]==(8,1000)
                if not self.timer_error:self.watch=self.read(args[2],8)
                return self.timer_error
            if name=='mic_cancel':assert args[:2]==(0x13,1);return 0
            if name=='mic_format':assert args[0]==0;return 0
            if name=='mic_start':
                assert args[0]==1 and args[2]==7 and self.read(args[1],7)==PEER+b'\5'
                self.starts+=1;self.native_write(0x020127e0,PEER);self.native_write(0x02011968,b'\1')
                if not self.delayed:self.native_write(0x0201196c,b'\1')
                return 0
            if name=='mic_stop':
                self.stops+=1
                if not self.stop_error:self.native_write(0x02011968,bytes(5))
                return self.stop_error
            if name=='mic_reset':
                assert not self.read(0x0201196c,1)[0] and self.cstring(args[0])=='glassly_microphone_stop'
                self.native_write(0x02011968,b'\0');return 0
        return super().native(name,args)
    def control(self,op=2):
        data=CONFIG if op==1 else b'MC\1'+bytes([op])
        return self.service(0x77,self.request(data))[0]
    def task(self,event,data):
        p=self.allocate(len(data),'borrowed-task',data,writable=False)
        self.app=True;self.call('glassly_microphone_task_entry',event,p,len(data));self.app=False
        self.discard(p);assert not self.critical
    def flush(self):self.task(0x290,self.jobs.pop(0))
    def tick(self):self.task(0x291,self.watch)
    def start(self):
        assert self.control(1)['result']=='queued' and self.starts==0
        self.flush();assert self.control()['phase']==3
    def tx(self,uuid=UUID,peer=PEER):
        args=[self.allocate(len(x),'borrowed-tx',x,writable=False) for x in (peer,uuid,bytes.fromhex('5292000000000100000000ff')+bytes(49))]
        self.call('glassly_microphone_spp',*args,61);value=self.reg(10)
        for p in args:self.discard(p)
        return value
class Tests(unittest.TestCase):
    def test_stream_expiry_and_recovery(self):
        m=MicrophoneMachine();assert not m.tx();m.start();assert m.tx()
        s=m.control();assert s['stateHex']=='4d43010100010300a000a00002010101000000a000' and s['completed']==1
        m.now+=90000;assert not m.tx();m.tick();s=m.control()
        assert s['error']==6 and s['phase']==0 and not s['nativeActive'] and m.stops==1
        assert m.tx(UUID[:7]+b'\x26'+UUID[8:])
    def test_cancel_and_failed_stop(self):
        m=MicrophoneMachine();m.control(1);m.call('glassly_microphone_cleanup');m.flush()
        assert m.starts==0 and m.control()['error']==8
        m=MicrophoneMachine();m.start();m.stop_error=9
        m.control(3);assert not m.tx();m.flush();s=m.control()
        assert s['phase']==4 and s['nativeActive'] and s['nativeStatus']==9
        m.stop_error=0;m.tick();assert not m.control()['nativeActive']
    def test_queue_timer_and_start_failures(self):
        m=MicrophoneMachine();m.post_error=11
        assert m.control(1)['result']=='queue-failed' and not m.jobs
        m=MicrophoneMachine();m.timer_error=11;m.control(1);m.flush()
        assert m.control()['error']==11 and m.starts==0
        m=MicrophoneMachine();m.delayed=True;m.control(1);m.flush();m.now+=5000;m.tick()
        assert m.control()['error']==9 and m.read(0x02011968,1)==b'\0'
        m.delayed=False;m.control(1);m.flush();assert m.control()['phase']==3
    def test_renew_cleanup_and_foreign_owner(self):
        m=MicrophoneMachine();m.start();m.now+=80000;m.control(4);m.flush();m.now+=80000
        assert m.tx() and m.starts==1
        m.uc.mem_write(0x020127e0,b'\x99');m.tick();assert m.control()['error']==10 and m.stops==0
        m=MicrophoneMachine();m.start();m.call('glassly_microphone_cleanup');assert not m.tx();m.tick();assert m.stops==1
    def test_protocol_bounds_and_maximum_json(self):
        m=MicrophoneMachine()
        for data in (b'',CONFIG[:-1],CONFIG+b'\0',b'MC\2\2',b'MC\1\5'):
            assert m.service(0x77,m.request(data))[0]['result']=='invalid'
        bad=bytearray(CONFIG);bad[6]=0
        assert m.service(0x77,m.request(bytes(bad)))[0]['result']=='unsupported'
        m.start();m.uc.mem_write(REGISTRY+164,struct.pack('<7I',*[0xffffffff]*7))
        assert m.control()['serial']==0xffffffff

def veneers(build):
    b=json.loads((build/'build.json').read_text());blob=(build/'graphics.bin').read_bytes();cases=0
    sites=[('spp',0x0431ca9e,96,[(1,92),(8,88),(9,84)]),('iap2',0x0431b88c,48,[(1,44),(8,40),(9,36)]),('link',0x04245cf4,32,[(9,20)])]
    stock=(G.ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
    assert hashlib.sha256(stock).hexdigest()=='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
    for name,site,frame,saves in sites:
        for alignment in (0,8):
            for allowed in (0,1):
                uc=G.u.Uc(G.u.UC_ARCH_RISCV,G.u.UC_MODE_RISCV32);base=G.ENTRY&~4095
                uc.mem_map(base,((G.ENTRY+len(blob)+4095)&~4095)-base);uc.mem_write(G.ENTRY,blob)
                for page in (site&~4095,G.BT_BASE,G.RET):uc.mem_map(page,4096)
                for address in (site+8,G.RET):uc.mem_write(address,bytes.fromhex("13000000"))
                def read(i):return uc.reg_read(getattr(G.r,f'UC_RISCV_REG_X{i}'))
                def write(i,v):uc.reg_write(getattr(G.r,f'UC_RISCV_REG_X{i}'),v)
                for i in range(1,32):write(i,0xa0000000+i*0x101)
                sp=G.BT_BASE+4096-alignment;write(2,sp);write(1,G.RET)
                initial={i:read(i) for i in range(1,32)};seen=[]
                def hook(uc,address,size,_):
                    if address==b['symbols']['glassly_microphone_'+name]:
                        assert read(2)%16==0
                        assert [read(i) for i in range(10,18)]==[initial[i] for i in range(10,18)]
                        ret=read(1)
                        for i in (1,*G.CALLER):write(i,0xb0000000+i)
                        write(10,allowed);uc.reg_write(G.r.UC_RISCV_REG_PC,ret);seen.append('handler')
                    if address==site+8:
                        assert allowed or name=='link'
                        assert read(2)==sp-frame
                        for i in (1,3,4,8,*range(10,28)):
                            assert read(i)==initial[i],(name,i)
                        assert read(9)==(0x02014000 if name=='link' else initial[9])
                        for i,off in saves:assert struct.unpack('<I',uc.mem_read(sp-frame+off,4))[0]==initial[i]
                        seen.append('stock');uc.emu_stop()
                    if address==G.RET:
                        assert name!='link' and not allowed and read(10)==0
                        for i in G.CALLEE:assert read(i)==initial[i]
                        seen.append('denied');uc.emu_stop()
                uc.hook_add(G.u.UC_HOOK_CODE,hook)
                entry=b['symbols']['glassly_microphone_'+name+'_entry']
                prefix=stock[site-0x041eb020:site-0x041eb020+8]
                assert prefix in blob[entry-G.ENTRY:entry-G.ENTRY+200]
                try:uc.emu_start(entry,0,count=500)
                except Exception:
                    print(name,alignment,allowed,hex(uc.reg_read(G.r.UC_RISCV_REG_PC)),seen);raise
                assert seen==['handler','stock' if allowed or name=='link' else 'denied'];cases+=1
    sys.path.insert(0,str(G.ROOT/'scripts'))
    from build_memomind_minimal_owner import construct
    from memomind_ota import unpack_ota
    image,_=construct((G.ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes(),blob,b)
    body=unpack_ota(image)[1][3]['raw'][32:]
    assert body[0x0420a316-0x041eb020:0x0420a7ca-0x041eb020]==stock[0x0420a316-0x041eb020:0x0420a7ca-0x041eb020]
    uc=G.u.Uc(G.u.UC_ARCH_RISCV,G.u.UC_MODE_RISCV32)
    uc.mem_map(0x04209000,4096);uc.mem_map(0x02011000,4096)
    uc.mem_write(0x0420980c,body[0x0420980c-0x041eb020:0x0420981e-0x041eb020])
    uc.reg_write(G.r.UC_RISCV_REG_GP,0x02011688)
    uc.emu_start(0x0420980c,0x0420981e,count=10)
    assert uc.reg_read(G.r.UC_RISCV_REG_A0)==0x13
    assert uc.reg_read(G.r.UC_RISCV_REG_A1)==b['symbols']['glassly_microphone_task_entry']
    return cases+1

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    G.BUILD=a.build.resolve();b=json.loads((G.BUILD/'build.json').read_text());G.PINNED_SHA=b['blob_sha256'];assert b['microphone_control']
    cases=veneers(G.BUILD)
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    a.report.write_text(json.dumps(dict(passed=result.wasSuccessful(),groups=result.testsRun,veneerCases=cases,runtimeSHA256=G.PINNED_SHA,nativeAudioAPIsMocked=True,hardwareTested=False,calls=G.RESULTS),indent=2)+'\n')
    return not result.wasSuccessful()
if __name__=='__main__':raise SystemExit(main())
