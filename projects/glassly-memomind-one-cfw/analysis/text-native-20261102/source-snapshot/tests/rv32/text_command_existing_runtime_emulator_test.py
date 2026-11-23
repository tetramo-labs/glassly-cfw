#!/usr/bin/env python3
"""Retained suites repinned to text runtime; only native mocks, no devices."""
import argparse,json,sys
from pathlib import Path
from text_command_runtime_emulator_test import BUILD,PINNED_SHA

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',choices=('gates','canary','reader','input','scene','bundle'),required=True);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    assert json.loads((a.build/'build.json').read_text())['text_commands'] is True
    if a.suite=='gates':import flash_canary_gate_emulator_test as suite
    elif a.suite=='canary':import flash_canary_runtime_emulator_test as suite
    elif a.suite=='reader':
        import flash_canary_reader_emulator_test as reader
        suite=reader.suite
    elif a.suite=='bundle':
        # Preserve all prior bundle test logic except intentional capability
        # growth and removal of mode15 from the unsupported-child fixture.
        # New text suite checks malformed15/latefailure and resource failure.
        import types
        path=Path(__file__).with_name('command_bundle_runtime_emulator_test.py')
        source=path.read_text()
        edits={'[3,6,8,9,11,19,20,36,37,38,39,40,41]':'[3,6,8,9,11,15,19,20,36,37,38,39,40,41]',
               '[3,6,9,19,20,36,37,38,39,40,41]':'[3,6,9,15,19,20,36,37,38,39,40,41]',
               ",wire([b'\\x0f'+bytes(6)])":''}
        for before,after in edits.items():
            assert source.count(before)==1,(before,source.count(before))
            source=source.replace(before,after)
        suite=types.ModuleType('text_retained_bundle');suite.__file__=str(path)
        exec(compile(source,str(path),'exec'),suite.__dict__)
    elif a.suite=='scene':
        import scene_runtime_emulator_test as suite
        class BundleSceneTests(suite.SceneRuntimeTests):
            def test_identity_and_reset_put_show_state_clear(self):
                # Only the capability assertion differs from the retained test;
                # every subsequent reset/put/show/state/lifetime assertion remains.
                m=suite.SceneMachine();value,_=m.service(0x7e)
                self.assertEqual(value['modes'],[3,6,8,9,11,15,19,20,36,37,38,39,40,41])
                self.assertEqual(value['storeKiB'],64);self.assertEqual(value['maxMessageBytes'],8192);self.assertTrue(value['builtinText'])
                m.establish();reply,_=m.send_scene(bytes([40])+bytes(8))
                self.assertIn(reply[3],(5,6,7));self.assertGreater(suite.struct.unpack_from('<I',reply,6)[0],0)
                allocations=list(m.owned_live());m.now=400;_,values=m.send_scene(bytes([36,0]))
                self.assertEqual(values[0]['result'],'ok');self.assertEqual(m.pixel(6,6),7);self.assertEqual(m.owned_live(),allocations);m.assert_clear()
        suite.SceneRuntimeTests=BundleSceneTests;suite.SCENE_SHA=PINNED_SHA
    else:import input_runtime_emulator_test as suite
    suite.BUILD=a.build.resolve();suite.PINNED_SHA=PINNED_SHA
    sys.argv=[sys.argv[0],'--build',str(a.build),'--report',str(a.report)];suite.main()
if __name__=='__main__':main()
