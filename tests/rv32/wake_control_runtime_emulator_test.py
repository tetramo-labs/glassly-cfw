#!/usr/bin/env python3
"""Actual RV32 ownership, scene lifetime and button routing; native APIs mocked."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
from minimal_owner_flash_runtime_emulator_test import FlashMachine
G.NATIVES.update({0x042a88a8:'wake_on',0x0425f99e:'wake_on_state',0x0425f9f8:'wake_blocked'})
class WakeMachine(FlashMachine):
    def __init__(self):
        self.power_on=False;self.power_blocked=False;self.wake_calls=0;self.ownership_replies=[]
        super().__init__()
    def native(self,name,args):
        a0,a1,a2,a3,a4=args[:5]
        if name=='wake_on':
            self.wake_calls+=1
            if not self.power_blocked:self.power_on=True
            return 0
        if name=='wake_on_state':return int(self.power_on)
        if name=='wake_blocked':return int(self.power_blocked)
        if name=='post' and self.region(a2,a3)=='stack':
            assert (a0,a1,a3,a4)==(63,0x474c,10,2)
            copied=self.read(a2,a3);assert copied[0]==3
            if not self.drop_queue:self.queue.append(copied)
            return 0
        if name=='send' and a2==0x79:
            assert (a1,a4)==(15,1) and self.allocations[a3]['live']
            self.ownership_replies.append((a0,self.replies[a3]));return 1
        if name=='on_delete' and a1==self.symbols['wake_deleted']:
            assert a0 in self.hidden and a2==0x21
            if self.fail_event:return 0
            spec=self.allocate(40,'native-spec');record=self.allocate(12,'native-event-record',struct.pack('<IIB3x',a1,a3,a2))
            self.native_write(a0+8,struct.pack('<I',spec));self.native_write(spec+12,struct.pack('<I',record));self.native_write(spec+34,struct.pack('<H',1))
            self.images[a0].update(callback=a1,owner=a3,extra=[spec,record]);return record
        if name=='timer_create' and a0==self.symbols['wake_tick']:
            assert a1==20
            if self.fail_timer:return 0
            timer=self.allocate(16,'native-timer');self.native_write(timer+12,struct.pack('<I',a2))
            self.timers[timer]={'callback':a0,'owner':a2};return timer
        return super().native(name,args)
    def control(self,op,nonce=0,result='ok'):
        data=b'FC\x01'+bytes([op])+struct.pack('<H',nonce)
        before=len(self.ownership_replies);reply,_=self.service(0x79,self.request(data),0x68)
        assert reply is None
        job=self.queue.pop(0);assert job==bytes([3,0x68,6,0])+data
        raw=bytes([0,63,0,0])+struct.pack('<HH',0x474c,10)+job
        env=self.allocate(len(raw),'borrowed-wake',raw,writable=False)
        self.call('glassly_graphics_display',env,display=True);assert self.allocations[env]['live'];self.discard(env)
        assert len(self.ownership_replies)==before+1
        event,value=self.ownership_replies[-1];assert event==0x68 and value['result']==result,value
        state=bytes.fromhex(value['stateHex']);assert len(state)==9
        return state
    def button(self,id):
        raw=bytes([0,2,0,0])+struct.pack('<HH',id,0)
        env=self.allocate(8,'borrowed-button',raw,writable=False)
        self.call('glassly_input_observe',env,display=True);assert self.allocations[env]['live'];self.discard(env)
    def timer(self,name,now):
        self.now=now&0xffffffff
        timer=next(t for t,v in self.timers.items() if v['callback']==self.symbols[name])
        self.call(name,timer,display=True)
    def cleanup(self):
        self.call('glassly_launcher_destroy_entry',display=True)
        assert not (self.images or self.timers or self.owned_live())
class Tests(unittest.TestCase):
    def test_admission_power_guard_and_failure_cleanup(self):
        m=WakeMachine();assert m.control(0)==bytes(9);assert not m.owned_live()
        m.power_blocked=True;assert m.control(5,result='busy')[6]==1;assert not m.owned_live() and not m.wake_calls
        m.power_blocked=False;m.active_launcher=False;m.control(1,result='busy');assert not m.owned_live()
        for flag in ('fail_image','fail_event','fail_timer'):
            m=WakeMachine();setattr(m,flag,True);m.control(5,result='allocation-failed');assert not (m.images or m.timers or m.owned_live())
        m=WakeMachine();reply,_=m.service(0x79,m.request(b'FC\x01\x07\0\0'));assert reply['result']=='invalid' and not m.queue and not m.owned_live()
    def test_frame_renewal_expiry_and_fresh_acquisition(self):
        m=WakeMachine();m.establish();assert m.graphics()
        assert m.control(6)[1]==0 and not m.graphics()
        m.establish()
        state=m.control(5);assert state[1]==1 and state[5]==1 and not m.graphics() and m.wake_calls==1
        m.establish();assert m.control(0)[7]==1
        start=m.now;m.timer('tick',start+30000);assert m.graphics() and m.pixel(6,6)==7
        m.control(5);assert m.graphics() and m.control(0)[7]==1
        m.timer('wake_tick',m.now+89999);assert m.graphics()
        m.timer('wake_tick',m.now+1);assert not m.graphics() and not m.timers
        assert m.control(0)[1]==0;m.cleanup()
    def test_button_claim_ready_and_fallback(self):
        m=WakeMachine();m.control(1);m.control(5);m.establish()
        m.button(0x1f7c);event,response=m.ownership_replies[-1];state=bytes.fromhex(response['stateHex'])
        assert event==0 and response['result']=='event' and state[2]==1 and state[8]==1
        nonce=int.from_bytes(state[3:5],'little');assert nonce
        m.control(3,nonce);assert m.control(4,nonce+1)[2]==1
        assert m.control(4,nonce)[2]==0 and m.graphics()
        for id,event in ((0x1f7b,2),(0x1f7d,3),(0x1f7f,4)):
            m.button(id);assert bytes.fromhex(m.ownership_replies[-1][1]['stateHex'])[8]==event
        m.button(0x1f7c);m.timer('wake_tick',m.now+399);assert m.graphics()
        m.timer('wake_tick',m.now+1);assert not m.graphics() and not m.control(0)[2]
        m.establish();m.button(0x1f7c);m.button(0x1f7c);assert not m.graphics() and not m.control(0)[2]
        m.cleanup()
    def test_cleanup_launcher_loss_and_wrap(self):
        for action in ('mode11','destroy','inactive','lease'):
            m=WakeMachine();m.now=0xfffffff0;m.control(1);m.control(5);m.establish()
            if action=='mode11':m.send_scene(b'\x0b');assert not m.timers
            elif action=='destroy':m.cleanup()
            elif action=='inactive':m.active_launcher=False;m.timer('wake_tick',20);assert not m.timers and not m.graphics()
            else:
                m.timer('wake_tick',0xfffffff0+89999);assert m.graphics()
                m.timer('wake_tick',0xfffffff0+90000);assert not m.timers and not m.graphics()
            m.cleanup()
    def test_frame_lease_does_not_extend_partial_message(self):
        m=WakeMachine();m.control(5)
        m.send_scene(struct.pack('<BBIH',127,0,99,65535),patch_epoch=False)
        assert any(v['size']==65535 and v['live'] for v in m.allocations.values())
        m.timer('tick',m.now+30000)
        assert not any(v['size']==65535 and v['live'] for v in m.allocations.values())
        assert m.control(0)[1]==1
        m.cleanup()
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',required=True,type=Path);p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    G.BUILD=a.build.resolve();G.PINNED_SHA=json.loads((G.BUILD/'build.json').read_text())['blob_sha256']
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    a.report.write_text(json.dumps({'passed':result.wasSuccessful(),'groups':result.testsRun,'runtimeSHA256':G.PINNED_SHA,'hardwareTested':False,'calls':G.RESULTS},indent=2)+'\n')
    return not result.wasSuccessful()
if __name__=='__main__':raise SystemExit(main())
