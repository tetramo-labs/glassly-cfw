#!/usr/bin/env python3
"""Retained native raster/text/animation commands on the flash-scene profile."""
import argparse,json,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import rect_copy_runtime_emulator_test as R
import text_command_runtime_emulator_test as T
import command_bundle_runtime_emulator_test as B
from minimal_owner_flash_runtime_emulator_test import FlashMachine
class Tests(unittest.TestCase):
 def test_raster_copy_text_bundle_and_timer_reattach(self):
  m=FlashMachine();m.send_scene(R.keyframe());before=m.pixels()
  m.send_scene(R.packet(1,2,20,30,51,17));self.assertEqual(m.pixels(),R.snapshot_copy(before,1,2,20,30,51,17))
  m.send_scene(T.text(b'SWIFT',x=10,y=10));self.assertGreater(len(m.font_metrics_calls),0)
  _,values=m.bundle(B.wire([T.text(b'FLASH',x=10,y=40),R.packet(10,10,100,10,30,10)]))
  self.assertEqual(values[0]['result'],'ok');self.assertFalse(m.images[m.graphics()[0]].get('detached'))
  m.establish();m.send_scene(S.animate_packet());m.tick_at(m.now+20)
  self.assertFalse(m.images[m.graphics()[0]].get('detached'))
  m.tick_at(m.now+300);self.assertFalse(m.images[m.graphics()[0]].get('detached'))
  m.diagnostic(2);m.send_scene(R.keyframe());self.assertTrue(m.overlay())
  m.call('glassly_launcher_destroy_entry',display=True);self.assertFalse(m.images or m.timers or m.owned_live())
 def test_invalid_text_preserves_pixels_and_animation(self):
  m=FlashMachine();m.establish();before=m.pixels()
  _,values=m.send_scene(T.text(b'\xc0\xaf'));self.assertEqual(values[0]['result'],'invalid');self.assertEqual(m.pixels(),before)
  self.assertFalse(m.images[m.graphics()[0]].get('detached'))
  m.call('glassly_launcher_destroy_entry',display=True);self.assertFalse(m.owned_live())
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',required=True,type=Path);p.add_argument('--report',required=True,type=Path);a=p.parse_args()
 G.BUILD=a.build.resolve();G.PINNED_SHA=json.loads((G.BUILD/'build.json').read_text())['blob_sha256'];G.RESULTS.clear()
 result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 a.report.write_text(json.dumps({'passed':result.wasSuccessful(),'groups':result.testsRun,'runtime_sha256':G.PINNED_SHA,'calls':G.RESULTS,'hardware_tested':False},indent=2)+'\n');return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
