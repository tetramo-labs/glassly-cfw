#!/usr/bin/env python3
"""Real optional diagnostics/cleanup RV32; nested native LVGL deletion is mocked."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import input_runtime_emulator_test as I
import command_bundle_runtime_emulator_test as B
import text_command_runtime_emulator_test as T
import rect_copy_runtime_emulator_test as R
BUILD=G.ROOT/'runtime/build/diagnostic-commands-001'
PINNED_SHA='c1d8a1ffdd4f2799de4149d2e113527b29716886f6530549e56f68f61333d3b3'
G.NATIVES[0x042cd8e4]='diagnostic_unhide'
def decode(value):
    assert value['glassly']=='diagnostics' and value['abi']==1 and value['result']=='ok' and value['presentation']=='unchanged'
    b=bytes.fromhex(value['stateHex']);assert len(b)==20 and b[17]==0
    return dict(flags=b[0],hidden=b[1],seen=b[2],resync=b[3],last=int.from_bytes(b[4:6],'little'),high=int.from_bytes(b[6:8],'little'),worker=int.from_bytes(b[8:12],'little'),allocation=int.from_bytes(b[12:16],'little'),mode=b[16],epoch=int.from_bytes(b[18:20],'little'))
def delta(fid,high=False,bad=False):
    box=bytes([0,0,1,1]);return bytes([131 if high else 3])+box+(box if high else b'')+struct.pack('<H',fid)+(b'\0\0' if bad else b'\x8f')
class DiagnosticMachine(T.TextMachine,I.InputMachine):
    def __init__(self,*,alignment_four=True,four_aligned=True):
        self.deletion=[];self.parents={};self.overlay_sources=[];super().__init__();assert self.build['diagnostic_commands']
    def native(self,name,args):
        a0,a1,a2,a3,a4=args[:5]
        if name in ('input_hide','diagnostic_unhide'):
            assert a0 in self.images and a1==1
            if name=='input_hide':self.hidden.add(a0)
            else:self.hidden.discard(a0)
            self.native_write(a0+36,struct.pack('<I',1 if a0 in self.hidden else 0));return 0
        if name=='image_create':
            assert a0==self.parent or a0 in self.images
            if self.fail_image:return 0
            image=self.allocate(64,'native-image');self.images[image]={'callback':0,'owner':0,'extra':[]};self.parents[image]=a0
            if a0==self.parent:self.children.append(image)
            return image
        if name=='on_delete':
            assert a0 in self.images and a1 in [self.symbols[n] for n in ('deleted','diagnostic_deleted','overlay_deleted','input_deleted')] and a2==0x21
            if self.fail_event:return 0
            spec=self.allocate(40,'native-spec');record=self.allocate(12,'native-event-record',struct.pack('<IIB3x',a1,a3,a2))
            self.native_write(a0+8,struct.pack('<I',spec));self.native_write(spec+12,struct.pack('<I',record));self.native_write(spec+34,struct.pack('<H',1))
            self.images[a0].update(callback=a1,owner=a3,extra=[spec,record]);return record
        if name=='image_source':
            header,length,pixels=struct.unpack('<III',self.read(a1,12))
            if header==((18<<21)|(80<<10)|9):
                assert length==784 and self.parents[a0] in self.images and self.images[a0]['callback']==self.symbols['overlay_deleted']
                self.read(pixels,length);self.overlay_sources.append((a0,a1,header,length,pixels));return 0
        if name=='size' and (a1,a2)==(80,18):assert a0 in self.images;return 0
        if name=='image_delete':self.begin_delete(a0,False);return None
        return super().native(name,args)
    def begin_delete(self,image,internal):
        assert image in self.images
        saved={i:self.reg(i) for i in range(1,32)};info=self.images[image]
        frame={'saved':saved,'image':image,'event':0,'internal':internal};self.deletion.append(frame)
        self.events.append(('image_delete_begin',image,info['callback']))
        if info['callback']:
            event=self.allocate(16,'native-delete-event');self.native_write(event+12,struct.pack('<I',info['owner']));frame['event']=event
            self.set(10,event);self.set(1,G.CALLBACK_RET);self.uc.reg_write(G.r.UC_RISCV_REG_PC,info['callback'])
        else:self.continue_delete()
    def continue_delete(self):
        while self.deletion:
            f=self.deletion[-1];image=f['image'];children=[p for p,parent in self.parents.items() if parent==image]
            if children:self.begin_delete(children[0],True);return
            self.finish_image_delete(image);self.deletion.pop()
            for index,value in f['saved'].items():self.set(index,value)
            if not f['internal']:self.return_native();return
    def instruction(self,uc,address,size,userdata):
        if address!=G.CALLBACK_RET:return super().instruction(uc,address,size,userdata)
        self.instructions+=1;sp=self.reg(2);assert self.stack_base<=sp<=self.stack_top and sp%16==0;self.min_sp=min(self.min_sp,sp)
        f=self.deletion[-1];assert f['event']
        for i in G.CALLEE:assert self.reg(i)==(G.CALLBACK_RET if i==1 else f['saved'][i]),f'DELETE callee x{i}'
        self.discard(f['event']);f['event']=0;self.continue_delete()
    def finish_image_delete(self,image):
        assert not any(p==image for p in self.parents.values())
        info=self.images.pop(image);self.parents.pop(image);self.hidden.discard(image)
        if image in self.children:self.children.remove(image)
        for p in info['extra']:self.discard(p)
        self.discard(image);self.events.append(('image_delete_end',image))
    def delete(self,image):
        # Execute the actual native-call wrapper using its callable address.
        name='_native_delete_test';self.symbols[name]=0x042cf61c
        self.call(name,image,display=True);assert not self.deletion
    def metadata(self):return [p for p,v in self.images.items() if v['callback']==self.symbols['diagnostic_deleted']]
    def overlay(self):return [p for p,v in self.images.items() if v['callback']==self.symbols['overlay_deleted']]
    def graphics(self):return [p for p,v in self.images.items() if v['callback']==self.symbols['deleted']]
    def diagnostic(self,sub=None,high=False,trailing=b''):
        _,v=self.send_scene(bytes([135 if high else 7])+(b'' if sub is None else bytes([sub]))+trailing);return decode(v[0])
    def assert_clear(self):
        self.send_scene(b'\x0b');assert not self.graphics() and not self.overlay() and not self.timers
        meta=self.metadata();assert len(meta)<=1
        if meta:
            assert len(self.images)==1 and meta[0] in self.hidden
            owner=self.images[meta[0]]['owner'];assert self.owned_live()==[owner]
            self.delete(meta[0])
        assert not self.images and not self.owned_live() and not self.deletion
class DiagnosticTests(unittest.TestCase):
    def test_snapshot_fid_exact_edges_and_bundles(self):
        m=DiagnosticMachine();identity,_=m.service(0x7e);self.assertIn(7,identity['modes']);self.assertEqual(identity['diagnostics'],'native-v1');self.assertEqual(identity['snapshotBytes'],20)
        s=m.diagnostic(0);self.assertEqual((s['flags'],s['hidden'],s['resync']),(0,1,0))
        m.send_scene(delta(65535));s=m.diagnostic();self.assertEqual((s['flags'],s['last'],s['seen']),(4,0,1))
        m.diagnostic(0);m.send_scene(R.keyframe());m.send_scene(delta(10));m.send_scene(delta(12,True));m.send_scene(delta(11));s=m.diagnostic();self.assertEqual((s['flags'],s['last'],s['high']),(3,11,12))
        m.send_scene(delta(12));s=m.diagnostic();self.assertEqual((s['flags'],s['last']),(7,11))
        m.send_scene(R.keyframe());m.send_scene(delta(12));s=m.diagnostic();self.assertEqual(s['resync'],1)
        m.send_scene(delta(30000));self.assertEqual(m.diagnostic()['last'],30000)
        m.diagnostic(0);m.bundle(B.wire([R.keyframe(),delta(1),delta(3),delta(2)]));s=m.diagnostic();self.assertEqual((s['flags'],s['last']),(3,2))
        m.diagnostic(0);m.send_scene(R.keyframe());m.send_scene(delta(0));m.send_scene(delta(32768));self.assertEqual(m.diagnostic()['flags'],2)
        m.assert_clear()
    def test_controls_deferred_overlay_clean_copy_and_deletion_orders(self):
        for reverse in (False,True):
            m=DiagnosticMachine();m.send_scene(R.keyframe());original=m.pixels();n=len(m.image_sources)
            s=m.diagnostic(2,high=True,trailing=b'ignored');self.assertEqual(s['hidden'],0);self.assertFalse(m.overlay());self.assertEqual(len(m.image_sources),n)
            m.send_scene(bytes([36,0]));self.assertEqual(len(m.overlay()),1,'empty shapes take over and present the frame')
            self.assertEqual(m.pixels(),original);self.assertEqual(len(m.image_sources),n+1)
            m.send_scene(R.packet(99,99,301,99,129,115));expected=R.snapshot_copy(original,99,99,301,99,129,115)
            self.assertEqual(m.pixels(),expected);overlay=m.overlay()[0];self.assertNotIn(overlay,m.hidden);self.assertEqual(m.parents[overlay],m.graphics()[0])
            self.assertNotEqual(m.read(m.overlay_sources[-1][4]+64,720),bytes(720))
            m.diagnostic(1);self.assertNotIn(overlay,m.hidden);m.send_scene(R.packet(0,0,4,0,20,10));expected=R.snapshot_copy(expected,0,0,4,0,20,10)
            self.assertEqual(m.pixels(),expected);self.assertIn(overlay,m.hidden)
            m.diagnostic(2);m.send_scene(T.text());self.assertNotIn(overlay,m.hidden)
            order=[m.graphics()[0],m.metadata()[0]]
            if reverse:order.reverse()
            for image in order:m.delete(image)
            self.assertFalse(m.images or m.timers or m.owned_live() or m.deletion)
    def test_cleanup_button_epoch_history_and_idempotence(self):
        m=DiagnosticMachine();m.establish();epoch=m.epoch;m.send_scene(delta(5));m.send_scene(delta(7));before=m.diagnostic();m.execute(I.subscribe(nonce=123,mask=1));m.observe(2,0x1f7b)
        _,v=m.send_scene(b'\x8btrailing');self.assertEqual(v[0]['result'],'cleared');self.assertFalse(m.graphics() or m.overlay() or m.timers)
        s=m.diagnostic();self.assertEqual(s['flags'],before['flags']);self.assertEqual(s['epoch'],epoch+1);self.assertEqual(s['hidden'],1)
        self.assertFalse(m.execute(bytes([1,0]))['active']);m.send_scene(b'\x0bmore');self.assertEqual(m.diagnostic()['epoch'],s['epoch'])
        reply,_=m.send_scene(bytes([40])+bytes(8),patch_epoch=False);self.assertEqual(int.from_bytes(reply[4:6],'little'),s['epoch'])
        reply,_=m.send_scene(bytes([41,0,0,1,0,0]),patch_epoch=False);self.assertEqual(int.from_bytes(reply[4:6],'little'),s['epoch']+1)
        m.assert_clear()
    def test_refusal_counters_control_noops_and_failure_cleanup(self):
        m=DiagnosticMachine();m.diagnostic(0);initial=m.diagnostic()
        # BT structural rejection never reaches frame tracking/worker counter.
        value,_=m.service(0x7d,m.request(b'\x03'));self.assertEqual(value['result'],'invalid');self.assertEqual(m.diagnostic(),initial)
        m.send_scene(delta(9,bad=True));s=m.diagnostic();self.assertEqual((s['worker'],s['mode'],s['last']),(1,3,9))
        m.fail_alloc_sizes={1028};m.send_scene(T.text(b'A'*255));m.fail_alloc_sizes=set();s=m.diagnostic();self.assertEqual((s['worker'],s['allocation'],s['mode']),(2,1,15))
        for sub in [3,127,254,255]:self.assertEqual(m.diagnostic(sub,high=True,trailing=b'xyz'),s)
        m.diagnostic(2);m.fail_event=True;m.send_scene(R.keyframe());m.fail_event=False;self.assertFalse(m.overlay());m.send_scene(R.keyframe());self.assertEqual(len(m.overlay()),1)
        m.assert_clear()
def main():
    global BUILD
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args();BUILD=a.build.resolve();G.BUILD=BUILD;G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();S.STEPS.clear()
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticTests))
    report={'format':'memomind-diagnostic-command-rv32-v1','build':str(BUILD),'blob_sha256':PINNED_SHA,'passed':result.wasSuccessful(),'test_groups':result.testsRun,'calls':G.RESULTS,'steps':S.STEPS,'hardware_tested':False,'limits':['Native APIs and LVGL object tree/callback scheduling mocked; actual RV32 ownership/parser/render code executes.','Metadata persists only for current screenobject; cleanup epoch preservation best-effort ifmetadataallocationfails.','Counters are executed scene-dispatch failures and token-workspace allocation refusals, notG2transport/timing.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
