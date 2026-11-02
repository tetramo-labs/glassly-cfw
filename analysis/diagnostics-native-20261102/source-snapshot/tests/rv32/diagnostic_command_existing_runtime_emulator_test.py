#!/usr/bin/env python3
"""Retained tests on diagnostics profile with explicit metadata/cleanup adaptations."""
import argparse,json,sys,types
from pathlib import Path
from diagnostic_command_runtime_emulator_test import BUILD,PINNED_SHA,DiagnosticMachine

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',choices=('gates','canary','reader','input','scene','bundle','text'),required=True);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 assert json.loads((a.build/'build.json').read_text())['diagnostic_commands'] is True
 if a.suite=='gates':import flash_canary_gate_emulator_test as suite
 elif a.suite=='canary':import flash_canary_runtime_emulator_test as suite
 elif a.suite=='reader':
  import flash_canary_reader_emulator_test as reader
  suite=reader.suite
 elif a.suite=='text':
  import text_command_runtime_emulator_test as suite
  suite.TextMachine=DiagnosticMachine
 elif a.suite=='bundle':
  path=Path(__file__).with_name('command_bundle_runtime_emulator_test.py');source=path.read_text()
  edits={'[3,6,8,9,11,19,20,36,37,38,39,40,41]':'[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41]',
         '[3,6,9,19,20,36,37,38,39,40,41]':'[3,6,9,15,19,20,36,37,38,39,40,41]',
         ",wire([b'\\x0f'+bytes(6)])":'',
         'snapshots={p:m.read(p,m.allocations[p][\'size\']) for p in m.owned_live()}':
         'snapshots={p:m.read(p,m.allocations[p][\'size\']) for p in m.owned_live() if p not in [m.images[i][\'owner\'] for i in m.metadata()]}'}
  # Alias fixture covers session/core-owned spans; diagnostic metadata is a
  # distinct callback owner, validated/freed separately by DiagnosticMachine.
  for before,after in edits.items():assert source.count(before)==1,before;source=source.replace(before,after)
  suite=types.ModuleType('diagnostic_retained_bundle');suite.__file__=str(path);exec(compile(source,str(path),'exec'),suite.__dict__);suite.BundleMachine=DiagnosticMachine
 elif a.suite=='scene':
  import scene_runtime_emulator_test as suite
  class RetainedSceneTests(suite.SceneRuntimeTests):
   def test_identity_and_reset_put_show_state_clear(self):
    m=DiagnosticMachine();v,_=m.service(0x7e);self.assertEqual(v['modes'],[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41]);self.assertEqual(v['storeKiB'],64);self.assertEqual(v['maxMessageBytes'],8192);self.assertTrue(v['builtinText'])
    m.establish();reply,_=m.send_scene(bytes([40])+bytes(8));self.assertIn(reply[3],(5,6,7));self.assertGreater(suite.struct.unpack_from('<I',reply,6)[0],0)
    allocations=list(m.owned_live());m.now=400;_,values=m.send_scene(bytes([36,0]));self.assertEqual(values[0]['result'],'ok');self.assertEqual(m.pixel(6,6),7);self.assertEqual(m.owned_live(),allocations);m.assert_clear()
  suite.SceneRuntimeTests=RetainedSceneTests;suite.SceneMachine=DiagnosticMachine;suite.SCENE_SHA=PINNED_SHA
 else:
  import input_runtime_emulator_test as suite
  class RetainedInputTests(suite.InputRuntimeTests):
   def test_hidden_and_graphics_owners_are_independent(self):
    m=DiagnosticMachine();m.execute(suite.subscribe());hidden=next(iter(m.images));owner=m.owner();m.execute_display(suite.graphics.point_message())
    self.assertEqual(len(m.images),2);self.assertEqual(len(m.hidden),1);self.assertTrue(m.image_sources);m.observe(3,2);self.assertEqual(m.execute(suite.poll())['sequence'],1)
    m.execute_display(b'\x0b');self.assertNotIn(hidden,m.images);self.assertFalse(m.allocations[owner]['live']);self.assertFalse(m.execute(bytes([1,0]))['active'])
    # New cleanup deliberately stops input too. Only tagged diagnostic metadata
    # may survive; assert_clear validates it and executes its DELETE callback.
    m.assert_clear()
  suite.InputRuntimeTests=RetainedInputTests;suite.InputMachine=DiagnosticMachine
 suite.BUILD=a.build.resolve();suite.PINNED_SHA=PINNED_SHA
 sys.argv=[sys.argv[0],'--build',str(a.build),'--report',str(a.report)];suite.main()
if __name__=='__main__':main()
