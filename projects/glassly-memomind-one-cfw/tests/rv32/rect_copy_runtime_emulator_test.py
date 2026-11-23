#!/usr/bin/env python3
"""Actual mode9 machine code and native queue adapter; native firmware mocked."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
BUILD=G.ROOT/'runtime/build/rect-copy-001'
PINNED_SHA='c2c702f42d92e0b1dccc99e647f4038c391305e0b1ec642ded205c1a6c30dca7'
def packet(sx,sy,dx,dy,w,h,stereo=False):
    p=bytes([0x89 if stereo else 9])+struct.pack('<8H',sx,sy,w,h,dx,dy,w,h)
    return p+b'\xff'*16 if stereo else p

def keyframe():
    return b'\6'+b''.join(bytes([y%16,0])+struct.pack('<H',600) for y in range(350))

def snapshot_copy(raw,sx,sy,dx,dy,w,h):
    old=bytes(raw);out=bytearray(raw)
    for y in range(h):
        for x in range(w):
            source=old[(sy+y)*300+(sx+x)//2];value=source&15 if (sx+x)&1 else source>>4
            at=(dy+y)*300+(dx+x)//2;shift=0 if (dx+x)&1 else 4
            out[at]=(out[at]&~(15<<shift))|(value<<shift)
    return bytes(out)

class RectMachine(S.SceneMachine):
    def __init__(self):
        super().__init__(alignment_four=True);assert self.build['rect_copy'] and self.build['raster_commands'] and self.build['flash_canary']
    def pixels(self):return self.read(self.image_sources[-1][4]+64,105000)
    def checker(self):
        # Actual mode3 execution seeds an8x8 checker in a64x32 box for odd copies.
        runs=bytes([0x8f if (x+y)%2 else 0x81 for y in range(32) for x in range(8)])
        self.send_scene(bytes([3,25,90,16,16,0,0])+runs)
class RectTests(unittest.TestCase):
    def test_identity_and_odd_overlap_snapshot(self):
        m=RectMachine();identity,_=m.service(0x7e);self.assertEqual(identity['modes'],[3,6,9,11,19,20,36,37,38,39,40,41]);self.assertEqual(identity['rasterLens'],'first-left')
        m.send_scene(keyframe());m.checker()
        rects=[(99,99,301,99,129,115),(100,180,101,181,63,31),(101,181,100,180,63,31),
               (100,180,101,180,63,31),(101,180,100,180,63,31),(0,0,0,0,600,350),(599,349,0,0,1,1)]
        for rect in rects:
            old=m.pixels();expected=snapshot_copy(old,*rect);calls=len(m.image_sources);allocs=m.owned_live()
            _,values=m.send_scene(packet(*rect));self.assertEqual(values[0]['result'],'ok')
            self.assertEqual(len(m.image_sources),calls+1);self.assertEqual(m.owned_live(),allocs);self.assertEqual(m.pixels(),expected)
        expected=snapshot_copy(m.pixels(),0,0,597,347,3,3)
        m.send_scene(packet(0,0,597,347,3,3,True)+b'ignored');self.assertEqual(m.pixels(),expected)
        m.assert_clear()
    def test_invalid_preserves_frame_and_animated_scene(self):
        m=RectMachine();m.establish();m.send_scene(S.animate_packet());m.tick_at(140)
        old=m.pixels();count=len(m.image_sources)
        bad=[packet(599,349,0,0,2,2),packet(0,0,0,0,0,1),packet(0,0,65535,0,1,1),packet(0,0,0,65535,1,1)]
        mismatch=bytearray(packet(0,0,1,1,3,3));mismatch[13]=4;bad.append(bytes(mismatch))
        for data in bad:
            _,v=m.send_scene(data);self.assertEqual(v[0]['result'],'invalid');self.assertEqual(m.pixels(),old);self.assertEqual(len(m.image_sources),count)
        for data in (packet(0,0,0,0,1,1)[:16],packet(0,0,0,0,1,1,True)[:32]):
            value,_=m.service(0x7d,m.request(data));self.assertEqual(value['result'],'invalid');self.assertFalse(m.queue)
        m.tick_at(180);self.assertNotEqual(m.pixels(),old,'Malformed copy must leave timer/active scene running')
        before=m.pixels();n=len(m.image_sources);_,v=m.send_scene(packet(0,0,1,1,160,30))
        self.assertEqual(v[0]['result'],'ok');self.assertEqual(v[1]['result'],'settled');self.assertEqual(len(m.image_sources),n+1)
        self.assertEqual(m.pixels(),snapshot_copy(before,0,0,1,1,160,30))
        stable=m.pixels();count=len(m.image_sources);m.tick_at(220);m.tick_at(260);self.assertEqual(m.pixels(),stable);self.assertEqual(len(m.image_sources),count)
        reply,_=m.send_scene(S.show_packet());self.assertEqual(reply[3],0);m.assert_clear()
    def test_aliases_queue_loss_oom_lease_cleanup(self):
        m=RectMachine();m.establish();m.send_scene(keyframe());pixels=m.image_sources[-1][4]+64
        descriptor=m.allocate(20,'surface',struct.pack('<5I',pixels,105000,600,350,300));before=m.pixels()
        for p,n in ((pixels,17),(descriptor,20),(0xfffffffe,17)):
            m.call('mm_rect_copy_draw',descriptor,p,n,display=True);self.assertNotEqual(m.reg(10),0);self.assertEqual(m.pixels(),before)
        owner=m.images[next(iter(m.images))]['owner'];session=owner+32
        snapshots={p:m.read(p,m.allocations[p]['size']) for p in m.owned_live()};count=0
        for p,block in snapshots.items():
            if p==owner or p<=pixels<p+len(block):continue
            m.call('mm_scene_session_dispatch',session,p+8,17,display=True);self.assertNotEqual(m.reg(10),0);count+=1
            for address,value in snapshots.items():self.assertEqual(m.read(address,len(value)),value)
        self.assertGreaterEqual(count,4);m.assert_clear()
        data=packet(0,0,1,1,3,3)
        m=RectMachine();m.free_bytes=32000;v,_=m.service(0x7d,m.request(data));self.assertEqual(v['result'],'allocation-failed');self.assertFalse(m.queue or m.owned_live())
        m=RectMachine();m.drop_queue=True;v,_=m.service(0x7d,m.request(data));self.assertIsNone(v);self.assertFalse(m.queue or m.owned_live())
        m=RectMachine();m.send_scene(data);m.tick_at(1100);self.assertFalse(m.images or m.timers or m.owned_live())

def main():
    global BUILD
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args();BUILD=a.build.resolve();G.BUILD=BUILD;G.PINNED_SHA=PINNED_SHA
    assert G.u.__version__=='2.1.4';G.RESULTS.clear();S.STEPS.clear()
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(RectTests))
    report={'format':'memomind-rect-copy-rv32-v1','build':str(BUILD),'blob_sha256':PINNED_SHA,'passed':result.wasSuccessful(),'test_groups':result.testsRun,'calls':G.RESULTS,'steps':S.STEPS,'hardware_tested':False,'native_stubs':{hex(k):v for k,v in G.NATIVES.items()},'limits':['Actual RV32 C/native wrappers; native firmware APIs mocked.','Single first-left rectangle pair, native8192-byte admission and64KiB RAM scene unchanged.','4KiBBT/8KiBdisplay synthetic guards and callee registers; not complete native/task interrupt stack proof.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
