#!/usr/bin/env python3
"""Actual optional mode15 RV32 instructions; native resource APIs are mocks."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import command_bundle_runtime_emulator_test as B
BUILD=G.ROOT/'runtime/build/text-commands-001'
PINNED_SHA='ab0f32b5a96264b8ee1c9f5faa4122a09b52c0d48d9f6404394c3ed927feded7'
def text(data=b'AB',x=10,y=10,options=15,high=False):
    return bytes([143 if high else 15])+struct.pack('<hhBB',x,y,options,len(data))+data
class TextMachine(B.BundleMachine):
    def __init__(self):
        super().__init__();assert self.build['text_commands'];self.font_bad_bpp=False;self.font_bad_bitmap=False
    def native(self,name,args):
        if name=='font_metrics':
            font,glyph,cp,following=args[:4];assert font==S.FONT and 32<=cp<=0x10ffff
            self.font_metrics_calls.append((cp,following))
            if cp==self.font_missing:return 0
            self.native_write(glyph,struct.pack('<IHHHhhBB',S.FONT,3,3,2,0,0,4 if self.font_bad_bpp else 2,0));return 1
        if name=='font_bitmap':return 0 if self.font_bad_bitmap else self.font_bits
        return super().native(name,args)
class TextTests(unittest.TestCase):
    def test_identity_255_utf8_controls_clipping_and_options(self):
        m=TextMachine();identity,_=m.service(0x7e)
        self.assertIn(15,identity['modes']);self.assertIn(15,identity['bundleModes']);self.assertEqual(identity['textMaxBytes'],255)
        self.assertEqual(identity['textFont'],'native-resource');self.assertEqual(identity['missingGlyph'],'reject')
        m.send_scene(text(b'A'*255,high=True));self.assertEqual(len(m.font_metrics_calls),510)
        owned=m.owned_live();n=len(m.image_sources)
        for opt in range(256):
            m.send_scene(text(b'AB',x=10,y=10,options=opt));self.assertEqual(m.owned_live(),owned)
            for row,values in enumerate(((0,5,10),(15,10,5))):
                for x,v in enumerate(values):
                    if not v and opt&16:continue
                    self.assertEqual(m.pixel(10+x,11+row),(15-v if opt&32 else v)*(opt&15)//15)
        self.assertEqual(len(m.image_sources),n+256)
        m.font_metrics_calls=[];m.send_scene(text(b'A\x0a\x0dB\x7f\xc2\x80\xe2\x98\x85\xf0\x9f\x98\x80',x=-1,y=-1))
        self.assertEqual(m.font_metrics_calls[:6],[(65,66),(66,127),(127,128),(128,0x2605),(0x2605,0x1f600),(0x1f600,0)])
        m.send_scene(text(bytes([11])*255));m.send_scene(text(b'',x=-32768,y=32767));m.assert_clear()
    def test_exact_length_and_syntax_errors_no_partial_draw(self):
        m=TextMachine();m.send_scene(text());old=m.pixels();count=len(m.image_sources);owned=m.owned_live()
        for data in [text()+b'!',text()[:-1],b'\x0f',b'\x8f'+bytes(5)]:
            before=len(m.queue);value,_=m.service(0x7d,m.request(data),17)
            self.assertEqual(value['result'],'invalid');self.assertEqual(len(m.queue),before)
        for bad in [b'\0',b'\x80',b'\xc0\xaf',b'\xed\xa0\x80',b'\xf4\x90\x80\x80',b'\xe2\x82']:
            _,values=m.send_scene(text(b'A'+bad));self.assertEqual(values[0]['result'],'invalid')
            self.assertEqual(m.pixels(),old);self.assertEqual(len(m.image_sources),count);self.assertEqual(m.owned_live(),owned)
        m.assert_clear()
    def test_missing_unsupported_resources_and_scratch_failures_preserve_animation(self):
        for failure in ['missing','bpp','bitmap','alloc','headroom']:
            m=TextMachine();m.establish();m.send_scene(S.animate_packet());old=m.pixels();n=len(m.image_sources);owned=m.owned_live()
            if failure=='missing':m.font_missing=66
            if failure=='bpp':m.font_bad_bpp=True
            if failure=='bitmap':m.font_bad_bitmap=True
            if failure=='alloc':m.fail_alloc_sizes={1028}
            if failure=='headroom':m.free_values=[0x80000,48*1024+1027]
            _,v=m.send_scene(text(b'A'*254+b'B'))
            self.assertEqual(v[0]['result'],'allocation-failed' if failure in ('alloc','headroom') else 'invalid')
            self.assertEqual(m.pixels(),old);self.assertEqual(len(m.image_sources),n);self.assertEqual(m.owned_live(),owned)
            m.fail_alloc_sizes=set();m.font_missing=None;m.font_bad_bpp=m.font_bad_bitmap=False
            m.tick_at(200);self.assertNotEqual(m.pixels(),old);m.assert_clear()
    def test_takeover_bundle_cache_and_late_failure(self):
        m=TextMachine();m.establish();m.send_scene(S.animate_packet());pending=m.request_number
        expected=bytearray(m.pixels())
        for left in (10,13):
            for row,values in enumerate(((0,5,10),(15,10,5))):
                for dx,value in enumerate(values):
                    x=left+dx;at=(11+row)*300+x//2;shift=0 if x&1 else 4
                    expected[at]=(expected[at]&~(15<<shift))|(value<<shift)
        _,v=m.send_scene(text());self.assertEqual(v[0]['result'],'ok');self.assertEqual(v[1]['tag'],pending)
        self.assertEqual(m.pixels(),bytes(expected),'Text preserves the retained displayed background outside glyphs')
        old=m.pixels();m.tick_at(200);self.assertEqual(m.pixels(),old)
        n=len(m.image_sources);reset=B.epoch_packet(bytes([41,0,0,1,0,0]),m.epoch)
        cache,v=m.bundle(B.wire([reset,text(b'AB',x=50,high=True)]));self.assertEqual(cache[0],41);self.assertEqual(len(m.image_sources),n+1)
        old=m.pixels();n=len(m.image_sources);_,v=m.bundle(B.wire([text(b'A',x=80),text(b'B\0',x=90)]))
        self.assertEqual(v[0]['result'],'invalid');self.assertNotEqual(m.pixels(),old);self.assertEqual(len(m.image_sources),n)
        owned=m.owned_live();_,v=m.bundle(B.wire([text(b'',high=True)]*255));self.assertEqual(v[0]['result'],'ok');self.assertEqual(m.owned_live(),owned);m.assert_clear()
    def test_owned_aliases_queue_drop_and_lease_cleanup(self):
        m=TextMachine();m.establish();m.send_scene(text());owner=m.images[next(iter(m.images))]['owner'];session=owner+32;pixels=m.image_sources[-1][4]+64
        snapshots={p:m.read(p,m.allocations[p]['size']) for p in m.owned_live()}
        for p,value in snapshots.items():
            src=session if p==owner else pixels if p<=pixels<p+len(value) else p+8
            m.call('mm_scene_session_dispatch',session,src,8,display=True);self.assertNotEqual(m.reg(10),0)
            for q,old in snapshots.items():self.assertEqual(m.read(q,len(old)),old)
        m.drop_queue=True;owned=m.owned_live();v,_=m.service(0x7d,m.request(text()),51);self.assertIsNone(v);self.assertFalse(m.queue);self.assertEqual(m.owned_live(),owned);m.drop_queue=False
        m.assert_clear()
def main():
    global BUILD
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args();BUILD=a.build.resolve();G.BUILD=BUILD;G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();S.STEPS.clear()
    assert G.u.__version__=='2.1.4'
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(TextTests))
    report={'format':'memomind-text-commands-rv32-v1','build':str(BUILD),'blob_sha256':PINNED_SHA,'passed':result.wasSuccessful(),'test_groups':result.testsRun,'calls':G.RESULTS,'steps':S.STEPS,'hardware_tested':False,'limitations':['Real RV32 C/native wrappers/gates; resource font descriptors/bitmaps and external firmware APIs mocked.','Synthetic glyphs test semantics, not real MemoMind/G2 font equality.','Native8192 ingress/64KiB scene store unchanged; synthetic stacks exclude native frames/interrupts.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
