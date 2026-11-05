#!/usr/bin/env python3
"""Run RESET undo policy on actual linked RV32 with explicit native heap mocks."""
import argparse,hashlib,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import command_bundle_runtime_emulator_test as B
from diagnostic_command_runtime_emulator_test import DiagnosticMachine
PINNED_SHA='93040b1de94b52b710d7a3e37a3adef2f1e840108fb53ab69b9ecf46e14102f4'
BUILD=G.ROOT/'runtime/build/reset-undo-trim-003'
class TrimTests(unittest.TestCase):
    def test_exact_rv32_release_reacquire_and_pixels(self):
        m=DiagnosticMachine();m.establish();pixels=m.pixels();before=m.core_bytes()
        undo=[p for p in m.owned_live() if m.allocations[p]['size']==48824]
        self.assertEqual(len(undo),1)
        reply,_=m.send_scene(S.reset_packet());self.assertEqual(reply[3],0)
        self.assertEqual(before-m.core_bytes(),48824);self.assertEqual(m.pixels(),pixels)
        self.assertFalse(m.allocations[undo[0]]['live'])
        after=m.core_bytes();m.send_scene(S.reset_packet());self.assertEqual(m.core_bytes(),after)
        reply,_=m.send_scene(S.put_packet());self.assertEqual(reply[3],0)
        self.assertEqual(m.core_bytes(),before);allocs=m.owned_live()
        m.send_scene(S.show_packet());self.assertEqual(m.owned_live(),allocs);self.assertEqual(m.pixel(6,6),7)
        m.assert_clear()
    def test_reacquisition_refuses_before_mutation(self):
        m=DiagnosticMachine();m.establish();m.send_scene(S.reset_packet())
        pixels=m.pixels();before=m.core_bytes()
        # Exact RV32 cfw_undo47536 plus8-byte adapter header; fail every
        # allocation fallback capacity, not request or framebuffer allocations.
        m.fail_alloc_sizes={47544+20*c for c in (64,32,16,8,4,2,1,0)}
        reply,_=m.send_scene(S.put_packet());self.assertEqual(reply[3],3)
        self.assertEqual(struct.unpack_from('<I',reply,6)[0],0)
        self.assertEqual(m.core_bytes(),before);self.assertEqual(m.pixels(),pixels)
        show=bytearray(39);show[0]=38;show[5]=1;show[7]=1;show[8:37]=S.put_packet()[5:]
        reply,_=m.send_scene(bytes(show));self.assertEqual(reply[3],3)
        self.assertEqual(struct.unpack_from('<I',reply,6)[0],0)
        self.assertEqual(m.core_bytes(),before);self.assertEqual(m.pixels(),pixels)
        reply,_=m.bundle(B.wire([bytes([41,23,0,71,0,0]),B.epoch_packet(S.put_packet(),23,72)]))
        self.assertEqual(reply[3],3);self.assertEqual(struct.unpack_from('<I',reply,6)[0],0)
        self.assertEqual(m.core_bytes(),before);self.assertEqual(m.pixels(),pixels)
        m.fail_alloc_sizes=set();m.send_scene(S.put_packet());m.send_scene(S.show_packet());self.assertEqual(m.pixel(6,6),7);m.assert_clear()
    def test_bundles_keep_prepared_undo(self):
        for variant in range(3):
            m=DiagnosticMachine();m.establish();before=m.core_bytes()
            reset=bytes([41,23,0,10,0,0]);put=B.epoch_packet(S.put_packet(),23,11)
            show=B.epoch_packet(S.show_packet(),23,12)
            children=[reset,put,show]
            if variant==1:children.insert(0,B.epoch_packet(S.put_packet(),m.epoch,9))
            if variant==2:children.append(b'\x00')
            reply,values=m.bundle(B.wire(children))
            if variant==2:
                self.assertIsNone(reply);self.assertEqual(values[0]['result'],'invalid')
                state,_=m.send_scene(bytes([40])+bytes(8),patch_epoch=False)
                self.assertEqual(struct.unpack_from('<H',state,4)[0],23)
                self.assertEqual(struct.unpack_from('<I',state,6)[0],1)
            else:self.assertEqual(reply[3],0)
            self.assertEqual(m.core_bytes(),before);self.assertEqual(m.pixel(6,6),7)
            m.bundle(B.wire([reset]));self.assertEqual(m.core_bytes(),before)
            m.send_scene(S.reset_packet());self.assertEqual(before-m.core_bytes(),48824);m.assert_clear()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    G.BUILD=a.build.resolve();d=json.loads((G.BUILD/'build.json').read_text());assert d['reset_undo_trim'] and d['diagnostic_commands'];assert d['blob_bytes']<=65536
    G.PINNED_SHA=PINNED_SHA;G.RESULTS.clear();S.STEPS.clear()
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(TrimTests))
    report={'passed':result.wasSuccessful(),'test_groups':result.testsRun,'build':str(G.BUILD),'blob_sha256':PINNED_SHA,'calls':G.RESULTS,'steps':S.STEPS,'hardware_tested':False,'rv32_requested_bytes_released':48824,'limits':['Native heap and LVGL mocked; real RV32 policy/session/core runs.','Strong rollback is a native opt-in OOM policy; default G2 no-undo fallback remains tested separately.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
