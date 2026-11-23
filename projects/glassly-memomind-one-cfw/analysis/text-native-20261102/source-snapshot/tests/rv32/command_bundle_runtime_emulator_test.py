#!/usr/bin/env python3
"""Actual RV32 bundle/session/collector/native adapters, external APIs mocked."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import rect_copy_runtime_emulator_test as R
BUILD=G.ROOT/'runtime/build/bundle-commands-001'
PINNED_SHA='deeddff1533fc36c5468394a1fbbd612d3a2ec096dc864d963fa3cc30148f450'
def wire(children,high=False,trailing=b''):
    assert len(children)<=255
    return bytes([0x88 if high else 8,len(children)])+b''.join(struct.pack('<H',len(p))+p for p in children)+trailing

def epoch_packet(p,epoch,request=None):
    p=bytearray(p);struct.pack_into('<H',p,1,epoch)
    if request is not None:struct.pack_into('<H',p,3,request)
    return bytes(p)

def hide(epoch,tag):return struct.pack('<BHHBB',39,epoch,tag,4,0)
def asset(epoch,request,aid,kind,data,high=False):
    return struct.pack('<BHHBIIBIIH',0xa5 if high else 37,epoch,request,0,aid,1,kind,len(data),0,len(data))+data

class BundleMachine(S.SceneMachine):
    def __init__(self):
        super().__init__(alignment_four=True);assert self.build['command_bundles'] and self.build['rect_copy']
    def pixels(self):return self.read(self.image_sources[-1][4]+64,105000)
    def bundle(self,data):
        self.sequence_number=(self.sequence_number+1)&255
        start=len(self.sent);immediate,_=self.service(0x7d,self.request(data),self.sequence_number)
        assert immediate is None and self.queue
        job=self.queue.pop(0);assert job==bytes([1,self.sequence_number])+struct.pack('<H',len(data))+data
        raw=bytes([0,63,0,0])+struct.pack('<HH',0x474c,len(job))+job
        envelope=self.allocate(len(raw),'worker-envelope',raw,writable=False)
        self.call('glassly_graphics_display',envelope,display=True)
        assert self.allocations[envelope]['live'];values=self.sent[start:]
        assert values and all(event==self.sequence_number for event,_ in values)
        replies=[v for _,v in values];cache=None
        if 'replyHex' in replies[0]:
            cache=bytes.fromhex(replies[0]['replyHex']);assert 37<=cache[0]<=41
            self.epoch=struct.unpack_from('<H',cache,4)[0]
        self.core_bytes();S.STEPS.append({'bundle_count':data[1],'responses':replies,'core_peak_bytes':self.peak_core_bytes})
        return cache,replies

class BundleTests(unittest.TestCase):
    def test_identity_raster_mixture_single_present_and_partial_failure(self):
        m=BundleMachine();identity,_=m.service(0x7e)
        self.assertEqual(identity['modes'],[3,6,8,9,11,19,20,36,37,38,39,40,41]);self.assertEqual(identity['bundleModes'],[3,6,9,19,20,36,37,38,39,40,41]);self.assertEqual(identity['bundleMaxSegments'],255)
        key=R.keyframe();delta=bytes([0x83,25,90,16,16,255,255,16,16,0,0])+bytes([0x8f if (x+y)%2 else 0x81 for y in range(32) for x in range(8)])
        copy=R.packet(100,180,101,181,63,31,True)
        _,values=m.bundle(wire([bytes([0x86])+key[1:],delta,copy],high=True,trailing=b'ignored'))
        self.assertEqual(values,[{'glassly':'graphics','abi':1,'result':'ok','presentation':'scheduled'}]);self.assertEqual(len(m.image_sources),1)
        expected=bytearray(b''.join(bytes([(y%16)*17])*300 for y in range(350)))
        for y in range(32):
            for x in range(64):
                value=15 if (x//8+y)%2 else 1;at=(180+y)*300+(100+x)//2;shift=0 if (100+x)&1 else 4;expected[at]=(expected[at]&~(15<<shift))|(value<<shift)
        self.assertEqual(m.pixels(),R.snapshot_copy(expected,100,180,101,181,63,31))
        old=m.pixels();n=len(m.image_sources);copy=R.packet(99,99,301,99,129,115)
        _,values=m.bundle(wire([copy,R.packet(599,349,0,0,2,2)]));self.assertEqual(values[0]['result'],'invalid');self.assertEqual(len(m.image_sources),n)
        self.assertEqual(m.pixels(),R.snapshot_copy(old,99,99,301,99,129,115),'Late failure retains earlier copy effects')
        m.assert_clear()
    def test_all_cache_modes_highbits_and_final_scratch(self):
        m=BundleMachine();reset=bytes([0xa9,23,0,1,0,0]);put=bytearray(epoch_packet(S.put_packet(),23,2));put[0]|=128
        show=bytearray(epoch_packet(S.show_packet(),23,3));show[0]|=128
        hide_no_tag=bytes([0xa7,23,0,4,0,0,0]);state=bytes([0xa8,23,0])+bytes(6)
        # Render SHOW into shared shadow without intermediate native presentation.
        cache,v=m.bundle(wire([reset,bytes(put),bytes(show),hide_no_tag,state,bytes([0xa4,0])]))
        self.assertEqual(len(m.image_sources),1);self.assertEqual(m.pixel(6,6),7);self.assertEqual(cache[0],40);self.assertEqual(len(v),1)
        # Two assetPUTs, image19 and cachedfont20 use normalized highbit opcodes.
        image=bytes([1,1,0x17]);font=struct.pack('<96I',*([384]*96))+image
        image_draw=bytes([0x93])+struct.pack('<IhhB',1,10,10,15)
        text_draw=bytes([0x94])+struct.pack('<IhhBB',2,20,20,15,1)+b' '
        n=len(m.image_sources);cache,v=m.bundle(wire([asset(23,5,1,0,image,True),asset(23,6,2,1,font,True),image_draw,text_draw]))
        self.assertEqual(cache[0],37);self.assertEqual(len(v),1);self.assertEqual(len(m.image_sources),n+1);self.assertEqual(m.pixel(10,10),7);self.assertEqual(m.pixel(20,20),7)
        # Late failure suppresses scratch response but does not roll back assetPUT.
        cache,v=m.bundle(wire([asset(23,7,3,0,image),R.packet(599,349,0,0,2,2)]));self.assertIsNone(cache);self.assertEqual(v[0]['result'],'invalid')
        m.send_scene(bytes([19])+struct.pack('<IhhB',3,30,30,15));self.assertEqual(m.pixel(30,30),7)
        m.assert_clear()
    def test_255_segments_preserve_256_settled_tags_and_order(self):
        m=BundleMachine();m.establish();m.send_scene(S.animate_packet());initial=m.request_number
        tags=[11+i%2 for i in range(255)];old=m.owned_live();n=len(m.image_sources)
        cache,v=m.bundle(wire([hide(m.epoch,tag) for tag in tags]))
        self.assertEqual(cache[0],39);self.assertEqual(len(v),257);self.assertEqual([x['tag'] for x in v[1:]],[initial,*tags])
        self.assertEqual(len(m.image_sources),n+1);self.assertEqual(m.owned_live(),old)
        # Successful flush leaves neither borrowed collector pointer nor heap live.
        m.assert_clear()
    def test_single_segment_fills_exact_two_tag_capacity(self):
        m=BundleMachine();m.establish();m.send_scene(S.animate_packet());pending=m.request_number
        owned=m.owned_live();cache,v=m.bundle(wire([hide(m.epoch,pending+1)]))
        self.assertEqual(cache[0],39);self.assertEqual([x['tag'] for x in v[1:]],[pending,pending+1])
        self.assertEqual(m.owned_live(),owned);m.assert_clear()
    def test_empty_does_not_settle_pending_and_late_failure_flushes(self):
        m=BundleMachine();m.establish();m.send_scene(S.animate_packet());pending=m.request_number;n=len(m.image_sources)
        cache,v=m.bundle(wire([],high=True,trailing=b'\xffgarbage'));self.assertIsNone(cache);self.assertEqual(len(v),1);self.assertEqual(len(m.image_sources),n+1)
        start=len(m.sent);m.tick_at(500);self.assertEqual([v['tag'] for _,v in m.sent[start:] if v.get('result')=='settled'],[pending])
        n=len(m.image_sources);cache,v=m.bundle(wire([hide(m.epoch,17),R.packet(599,349,0,0,2,2)]))
        self.assertIsNone(cache);self.assertEqual(v[0]['result'],'invalid');self.assertEqual([x['tag'] for x in v[1:]],[17]);self.assertEqual(len(m.image_sources),n)
        m.assert_clear()
    def test_collector_admission_and_json_failure_cleanup(self):
        for failure in ('allocation','reserve'):
            m=BundleMachine();m.establish();m.send_scene(S.animate_packet());old=m.pixels();owned=m.owned_live();count=len(m.image_sources)
            if failure=='allocation':m.fail_alloc_sizes={1020}
            else:m.free_values=[0x80000,32768+1019]
            cache,v=m.bundle(wire([hide(m.epoch,11+i%2) for i in range(255)]));self.assertIsNone(cache);self.assertEqual(v[0]['result'],'allocation-failed')
            self.assertEqual(m.pixels(),old);self.assertEqual(m.owned_live(),owned);self.assertEqual(len(m.image_sources),count)
            m.fail_alloc_sizes=set();m.tick_at(200);self.assertNotEqual(m.pixels(),old);m.assert_clear()
        m=BundleMachine();m.establish();owned=m.owned_live();m.fail_json=True
        _,v=m.bundle(wire([hide(m.epoch,17)]));self.assertEqual(v,[{'status':4},{'status':4}]);self.assertEqual(m.owned_live(),owned)
        m.fail_json=False;m.assert_clear()
    def test_malformed_nesting_controls_mode15_and_owned_aliases(self):
        m=BundleMachine();m.send_scene(R.keyframe());old=m.pixels();n=len(m.image_sources)
        malformed=[b'\x08\x01',b'\x08\x01\0\0',b'\x08\x01\xff\xff\x24',wire([b'\x08\0']),wire([b'\x88\0']),wire([b'\x0b']),wire([b'\x0f'+bytes(6)]),wire([b'\x85\0'])]
        for data in malformed:
            _,v=m.bundle(data);self.assertEqual(v[0]['result'],'invalid');self.assertEqual(m.pixels(),old);self.assertEqual(len(m.image_sources),n)
        # Every existing core-owned span is rejected before prepare/collector use
        # when invoking the public session API directly.
        m.establish();owner=m.images[next(iter(m.images))]['owner'];session=owner+32;pixels=m.image_sources[-1][4]+64
        snapshots={p:m.read(p,m.allocations[p]['size']) for p in m.owned_live()};count=0
        for p,data in snapshots.items():
            src=session if p==owner else pixels if p<=pixels<p+len(data) else p+8
            m.call('mm_scene_session_dispatch',session,src,8,display=True);self.assertNotEqual(m.reg(10),0);count+=1
            for q,value in snapshots.items():self.assertEqual(m.read(q,len(value)),value)
        self.assertGreaterEqual(count,6);m.assert_clear()

def main():
    global BUILD
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args();BUILD=a.build.resolve();G.BUILD=BUILD;G.PINNED_SHA=PINNED_SHA
    assert G.u.__version__=='2.1.4';G.RESULTS.clear();S.STEPS.clear()
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(BundleTests))
    report={'format':'memomind-command-bundles-rv32-v1','build':str(BUILD),'blob_sha256':PINNED_SHA,'passed':result.wasSuccessful(),'test_groups':result.testsRun,'calls':G.RESULTS,'steps':S.STEPS,'hardware_tested':False,'native_stubs':{hex(k):v for k,v in G.NATIVES.items()},'limits':['Actual RV32 code; external firmware/LVGL/heap/queue/send APIs mocked.','Finalcache scratch only, not per-segment reply collection.','Partialfailure may mutate sharedLVGL pixels despite no finalpresent call; no rollback/invisibility guarantee.','Ordered P.send calls do not prove end-to-end radio delivery.','Mode15 unsupported; native8192 ingress,64KiB cache and lease unchanged.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
