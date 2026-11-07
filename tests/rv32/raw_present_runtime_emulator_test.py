#!/usr/bin/env python3
"""Raw presents on the pinned RV32 runtime: changed boxes are copied into the
locked panel slices and submitted, the LVGL image object is sourced once as
the fallback, and a refused slice lock falls back to the image object."""
import argparse
import json
import struct
import unittest
from pathlib import Path

import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
from sensor_capture_runtime_test import SensorMachine


def moved_show_packet():
    """SHOW that moves object 1 to x=100 (the animate packet's target, snapped)."""
    data = bytearray(24); data[0] = 38; data[5] = 7
    data[10] = 4; S.w32(data, 11, 1); S.w16(data, 15, 100); S.w16(data, 17, 0)
    data[19] = 0; data[20:24] = bytes([0, 0, 255, 255])
    return bytes(data)


class RawMachine(SensorMachine):
    """The full record build: flash, wake, notification and sensor natives mocked."""
    def submits(self):
        return [entry for entry in self.slices if entry[0] == "submit"]


class RawPresentTests(unittest.TestCase):
    def test_first_present_sources_the_fallback_once_and_copies_the_box(self):
        m = RawMachine(); m.establish()
        self.assertEqual(len(m.image_sources), 1, "the image object is sourced once as the fallback")
        submits = m.submits()
        self.assertEqual(len(submits), 2, "RESET clears the whole panel, then the SHOW presents its box")
        self.assertEqual(submits[0][2], (0, 0, 599, 349), "the clear covers the panel")
        self.assertEqual(submits[0][1], 3, "both slices locked for a whole-panel present")
        _, mask, rect, present = submits[1]
        self.assertEqual(present, 1)
        x1, y1, x2, y2 = rect
        self.assertTrue(x1 <= 5 and x2 >= 14 and y1 <= 5 and y2 >= 9, f"the SHOW's box covers the object: {rect}")
        # The first frame after a RESET may legitimately redraw the whole panel; the
        # moving-object test proves later frames present only their boxes.
        self.assertEqual(m.panel_pixel(6, 6), 7, "the object landed on the panel")
        self.assertEqual(m.panel_pixel(300, 300), 0)
        self.assertEqual(m.locked_mask, 0, "no slice stays locked")
        m.assert_clear()

    def test_moving_an_object_submits_only_the_union_box_without_resourcing(self):
        m = RawMachine(); m.establish()
        sources, before = len(m.image_sources), len(m.submits())
        reply, _ = m.send_scene(moved_show_packet()); self.assertEqual(reply[3], 0)
        self.assertEqual(len(m.image_sources), sources, "no LVGL invalidation for a raw present")
        new = m.submits()[before:]
        self.assertEqual(len(new), 1)
        x1, y1, x2, y2 = new[0][2]
        self.assertTrue(x1 <= 5 and x2 >= 109, f"old and new positions are both inside the box: {new[0][2]}")
        self.assertLessEqual(y2 - y1, 40, "rows outside the object are not transferred")
        self.assertEqual(m.panel_pixel(106, 6), 7); self.assertEqual(m.panel_pixel(6, 6), 0)
        m.assert_clear()

    def test_animation_ticks_present_raw_boxes_every_frame(self):
        m = RawMachine(); m.establish()
        period = bytes([41, 0, 0, 0, 0, 2, 20])
        reply, _ = m.send_scene(period); self.assertEqual(reply[3], 0)
        reply, values = m.send_scene(S.animate_packet()); self.assertEqual(reply[3], 0)
        sources, before = len(m.image_sources), len(m.submits())
        for offset in range(20, 201, 20): m.tick_at(100+offset)
        ticks = m.submits()[before:]
        self.assertGreaterEqual(len(ticks), 5, "each due tick submits its box")
        self.assertEqual(len(m.image_sources), sources, "ticks never hide or re-source the image")
        for _, _, (x1, y1, x2, y2), present in ticks:
            self.assertEqual(present, 1); self.assertLessEqual(y2 - y1, 40); self.assertLess(x2 - x1, 300)
        self.assertEqual(m.panel_pixel(106, 6), 7); self.assertEqual(m.panel_pixel(6, 6), 0)
        self.assertEqual(m.pixel(106, 6), 7, "the owned raster matches the panel")
        m.assert_clear()

    def test_refused_slice_lock_falls_back_to_the_image_object(self):
        m = RawMachine(); m.fail_slice = True
        m.establish()
        self.assertEqual(m.submits(), [])
        self.assertGreaterEqual(len(m.image_sources), 2, "the fallback re-sources the image on every present")
        self.assertEqual(m.pixel(6, 6), 7)
        m.assert_clear()

    def test_bundle_presents_the_union_of_its_segments_once(self):
        m = RawMachine(); m.establish()
        before, sources = len(m.submits()), len(m.image_sources)
        inner = moved_show_packet()
        data = bytearray(inner); S.w16(data, 1, m.epoch); m.request_number += 1; S.w16(data, 3, m.request_number)
        bundle = bytes([8, 1]) + struct.pack("<H", len(data)) + bytes(data)
        m.sequence_number = (m.sequence_number+1) & 255
        request = m.request(bundle)
        immediate, _ = m.service(0x7d, request, m.sequence_number)
        assert immediate is None and m.queue
        job = m.queue.pop(0)
        raw = bytes([0, 63, 0, 0])+struct.pack("<HH", 0x474c, len(job))+job
        envelope = m.allocate(len(raw), "native-envelope", raw)
        m.call("glassly_graphics_display", envelope, display=True)
        new = m.submits()[before:]
        self.assertEqual(len(new), 1, "a bundle submits once")
        self.assertLess(new[0][2][3] - new[0][2][1], 40, "the bundle's box is the segments' union, not the panel")
        self.assertEqual(len(m.image_sources), sources)
        self.assertEqual(m.panel_pixel(106, 6), 7)
        m.assert_clear()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    G.BUILD = args.build.resolve()
    build = json.loads((G.BUILD/"build.json").read_text())
    G.PINNED_SHA = S.SCENE_SHA = build["blob_sha256"]
    assert build.get("raw_present") is True, "Expected a --raw-present build"
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RawPresentTests))
    args.report.write_text(json.dumps({"passed": result.wasSuccessful(), "groups": result.testsRun,
                                       "runtimeSHA256": G.PINNED_SHA, "hardwareTested": False,
                                       "slicesMocked": True}, indent=2)+"\n")
    return not result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(main())
