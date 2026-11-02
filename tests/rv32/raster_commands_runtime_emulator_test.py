#!/usr/bin/env python3
"""Actual optional raster RV32 C/native handlers; external firmware APIs mocked."""
import argparse,hashlib,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
BUILD=G.ROOT/'runtime/build/raster-commands-001'
PINNED_SHA='4f4d211d885560a65da97c4a5d0b6a7d34231a254e7c8181507e3f2a9aaa5328'
FIXTURES=None
class RasterMachine(S.SceneMachine):
    def __init__(self):
        super().__init__(alignment_four=True)
        assert self.build['raster_commands'] and self.build['flash_canary']
    def pixels(self):return self.read(self.image_sources[-1][4]+64,105000)
class RasterTests(unittest.TestCase):
    def test_sender_full_frame_bottom_right_delta_and_identity(self):
        m=RasterMachine();identity,_=m.service(0x7e)
        self.assertEqual(identity['modes'],[3,6,11,19,20,36,37,38,39,40,41]);self.assertEqual(identity['rasterLens'],'first-left')
        self.assertEqual(identity['maxMessageBytes'],8192);self.assertEqual(identity['storeKiB'],64)
        key=(FIXTURES/'key.message').read_bytes();raw=(FIXTURES/'key.raw').read_bytes();delta=(FIXTURES/'delta.message').read_bytes()
        _,v=m.send_scene(key);self.assertEqual(v[0]['result'],'ok');self.assertEqual(len(m.image_sources),1);self.assertEqual(m.pixels(),raw)
        live=m.owned_live();n=len(m.image_sources);m.send_scene(delta);self.assertEqual(m.owned_live(),live);self.assertEqual(len(m.image_sources),n+1)
        expected=bytearray(raw);expected[348*300+298:348*300+300]=b'\x12\x34';expected[349*300+298:350*300]=b'\x56\x78'
        self.assertEqual(m.pixels(),expected)
        # Reused FID changes pixels; it is diagnostic, not replay suppression.
        duplicate=bytearray(delta);duplicate[-1]^=1;m.send_scene(duplicate);self.assertNotEqual(m.pixels(),expected)
        m.send_scene(bytes([0x86])+key[1:]);self.assertEqual(m.pixels(),raw)
        stereo=bytes([0x83,149,174,1,1,255,255,1,1,0,0,0x87]);m.send_scene(stereo)
        self.assertEqual(m.pixel(596,348),7);self.assertEqual(m.pixel(0,0),0)
        m.assert_clear()
    def test_invalid_leaves_pixels_and_presentation_unchanged(self):
        m=RasterMachine();m.send_scene((FIXTURES/'key.message').read_bytes());before=m.pixels();n=len(m.image_sources)
        packets=[bytes([3,149,174,2,1,0,0,0x87]),bytes([3,0,0,0,1,0,0,0x87]),
                 bytes([3,0,0,1,1,0,0,0,0,0,0]),bytes([6,0x87,0]),
                 bytes([0x83,149,174,1,1,0,0,2,1,0,0,0x87]),
                 (FIXTURES/'key.message').read_bytes()+b'\x11']
        for data in packets:
            _,v=m.send_scene(data);self.assertEqual(v[0]['result'],'invalid');self.assertEqual(m.pixels(),before);self.assertEqual(len(m.image_sources),n)
        m.assert_clear()
    def test_animation_takeover_validation_order_and_settled(self):
        m=RasterMachine();m.establish();m.send_scene(S.animate_packet());m.tick_at(140)
        old=m.pixels();n=len(m.image_sources)
        _,v=m.send_scene(bytes([3,149,174,2,1,0,0,0x87]));self.assertEqual(v[0]['result'],'invalid');self.assertEqual(m.pixels(),old);self.assertEqual(len(m.image_sources),n)
        m.tick_at(180);self.assertNotEqual(m.pixels(),old,'Malformed raster must not stop animation')
        n=len(m.image_sources);before=m.pixels();_,v=m.send_scene((FIXTURES/'delta.message').read_bytes())
        self.assertEqual(v[0]['result'],'ok');self.assertEqual(v[1]['result'],'settled');self.assertEqual(len(m.image_sources),n+1)
        expected=bytearray(before);expected[348*300+298:348*300+300]=b'\x12\x34';expected[349*300+298:350*300]=b'\x56\x78'
        self.assertEqual(m.pixels(),expected,'Delta must preserve displayed animated frame outside bbox')
        stable=m.pixels();n=len(m.image_sources)
        m.tick_at(220);m.tick_at(260);self.assertEqual(m.pixels(),stable);self.assertEqual(len(m.image_sources),n)
        # Same object remains cached and can be explicitly shown again.
        reply,_=m.send_scene(S.show_packet());self.assertEqual(reply[3],0);self.assertGreater(len(m.image_sources),n)
        m.assert_clear()
    def test_admission_queue_loss_cleanup_and_aliases(self):
        data=(FIXTURES/'key.message').read_bytes()
        m=RasterMachine();m.free_bytes=32000;value,_=m.service(0x7d,m.request(data));self.assertEqual(value['result'],'allocation-failed');self.assertFalse(m.queue or m.owned_live())
        m=RasterMachine();m.drop_queue=True;value,_=m.service(0x7d,m.request(data));self.assertIsNone(value);self.assertFalse(m.queue or m.owned_live())
        m=RasterMachine();value,_=m.service(0x7d,m.request(bytes([6])+bytes(8192)));self.assertEqual(value['result'],'invalid');self.assertFalse(m.queue or m.owned_live())
        m=RasterMachine();m.establish();m.send_scene(data);pix=m.image_sources[-1][4]+64;before=m.pixels()
        descriptor=m.allocate(20,'surface',struct.pack('<5I',pix,105000,600,350,300))
        for src,n in ((pix,len(data)),(descriptor,20),(0xfffffffe,8)):
            m.call('mm_raster_command_draw',descriptor,src,n,display=True);self.assertNotEqual(m.reg(10),0);self.assertEqual(m.pixels(),before)
        # Session handle aliases are rejected before reply/state writes.
        owner=m.images[next(iter(m.images))]['owner'];session=owner+32;old=m.read(session,64)
        m.call('mm_scene_session_dispatch',session,session,8,display=True);self.assertNotEqual(m.reg(10),0);self.assertEqual(m.read(session,64),old)
        # All scene-owned allocations (cache metadata/vector/undo/asset store)
        # are denied before inspecting mode or changing reply state.
        snapshots={p:m.read(p,m.allocations[p]['size']) for p in m.owned_live()}
        count=0
        for p,block in snapshots.items():
            if p==owner or p<=pix<p+len(block):continue
            self.assertEqual(m.word(p),len(block));self.assertIn(m.word(p+4),(0,1))
            m.call('mm_scene_session_dispatch',session,p+8,8,display=True);self.assertNotEqual(m.reg(10),0);count+=1
            for q,expected in snapshots.items():self.assertEqual(m.read(q,len(expected)),expected)
        self.assertGreaterEqual(count,4,'Must cover cache/vector/undo/store owned spans')
        m.tick_at(1100);self.assertFalse(m.images or m.timers or m.owned_live())
def main():
    global BUILD,FIXTURES
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--fixtures-from',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    BUILD=a.build.resolve();FIXTURES=a.fixtures_from.resolve();G.BUILD=BUILD;G.PINNED_SHA=PINNED_SHA
    assert G.u.__version__=='2.1.4';G.RESULTS.clear();S.STEPS.clear()
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(RasterTests))
    report={'format':'memomind-raster-commands-rv32-v1','build':str(BUILD),'blob_sha256':PINNED_SHA,'passed':result.wasSuccessful(),'test_groups':result.testsRun,'calls':G.RESULTS,'steps':S.STEPS,
            'fixtures':{n:hashlib.sha256((FIXTURES/n).read_bytes()).hexdigest() for n in ('key.message','key.raw','delta.message')},
            'native_stubs':{hex(k):v for k,v in G.NATIVES.items()},'hardware_tested':False,
            'limitations':['Actual compiled RV32 C/decoder/native wrappers; native allocator/LVGL/queue/timer/JSON APIs are mocked.','Synthetic4KiB BT/8KiB display stack guards and callee registers checked; no complete stock task-stack/interrupt proof.','Native input remains8192 bytes; original zlib decompression happened offline for fixture generation.','Only commands3/6 added, first/left bbox policy; no stereo display or full command parity claim.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
