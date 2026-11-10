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


def tagged_put(oid, x, y, color=7):
    """PUT of one 20x20 filled rect under object id `oid` (bit 31: one eye; bit 30: right)."""
    data = bytearray(34); data[0] = 37; data[5] = 1
    S.w32(data, 6, oid); S.w32(data, 10, 1)
    data[14:18] = bytes([3, 1, color, 0])
    for offset, value in ((18, x), (20, y), (22, 20), (24, 20)):
        S.w16(data, offset, value)
    return bytes(data)


def refs_show(ids):
    data = bytearray([38, 0, 0, 0, 0, 1, 0, 0]) + struct.pack("<H", len(ids))
    for oid in ids:
        data += struct.pack("<II", oid, 1)
    return bytes(data)


def eye_panels(m, snapshots):
    """Replays every submit into a model of each eye's panel (bit 5 left, bit 4 right)."""
    panels = {0x20: bytearray(600*350), 0x10: bytearray(600*350)}
    for (enable, frame), (_, _, (x1, y1, x2, y2), _) in zip(snapshots, m.submits()):
        for bit, panel in panels.items():
            if not enable & bit: continue
            for y in range(y1, y2+1):
                for x in range(x1, x2+1):
                    byte = frame[G.FRAMEBUFFER_STRIDE*y+x//2]
                    panel[600*y+x] = byte & 15 if x & 1 else byte >> 4
    return lambda bit, x, y: panels[bit][600*y+x]


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

    def test_one_eye_shows_reach_only_their_panel_and_the_other_catches_up(self):
        m = RawMachine(); m.establish()
        before = len(m.submits())
        self.assertTrue(all(enable == 0x30 for enable in m.panel_enables), "both-eye frames broadcast")
        left = bytearray(moved_show_packet()); left[5] |= 0x10
        reply, _ = m.send_scene(bytes(left)); self.assertEqual(reply[3], 0)
        self.assertEqual(len(m.submits()), before+1)
        self.assertEqual(m.panel_enables[-1], 0x20, "a left SHOW enables only panel 2")
        self.assertEqual(m.read(G.PANEL_ENABLE, 1)[0], 0x30, "both panels enabled again after the submit")
        moved = m.submits()[-1][2]
        self.assertTrue(moved[0] <= 5 and moved[2] >= 109, f"the left panel gets the move: {moved}")
        # The right eye's SHOW moves the object again: panel 1 gets that move and the
        # first one it missed.
        right = bytearray(moved_show_packet()); right[5] |= 0x20
        reply, _ = m.send_scene(bytes(right)); self.assertEqual(reply[3], 0)
        self.assertEqual(len(m.submits()), before+2)
        self.assertEqual(m.panel_enables[-1], 0x10, "a right SHOW enables only panel 1")
        x1, y1, x2, y2 = m.submits()[-1][2]
        self.assertTrue(x1 <= moved[0] and y1 <= moved[1] and x2 >= moved[2] and y2 >= moved[3],
                        f"the right panel receives the box it missed: {(x1, y1, x2, y2)} vs {moved}")
        # Both eyes caught up: a both-eye frame broadcasts its own box once.
        reply, _ = m.send_scene(S.show_packet()); self.assertEqual(reply[3], 0)
        self.assertEqual(len(m.submits()), before+3)
        self.assertEqual(m.panel_enables[-1], 0x30)
        self.assertEqual(m.panel_pixel(206, 6), 7); self.assertEqual(m.panel_pixel(106, 6), 0)
        m.assert_clear()

    def test_a_both_eye_frame_after_one_eye_broadcasts_what_either_lacks(self):
        m = RawMachine(); m.establish()
        before = len(m.submits())
        left = bytearray(moved_show_packet()); left[5] |= 0x10
        reply, _ = m.send_scene(bytes(left)); self.assertEqual(reply[3], 0)
        moved = m.submits()[-1][2]
        # A both-eye SHOW: one broadcast covers its own change and the move the
        # right panel lacks.
        reply, _ = m.send_scene(moved_show_packet()); self.assertEqual(reply[3], 0)
        self.assertEqual(m.panel_enables[before:], [0x20, 0x30])
        x1, y1, x2, y2 = m.submits()[-1][2]
        self.assertTrue(x1 <= moved[0] and y1 <= moved[1] and x2 >= moved[2] and y2 >= moved[3],
                        f"the broadcast covers the move the right panel lacks: {(x1, y1, x2, y2)} vs {moved}")
        self.assertEqual(m.read(G.PANEL_ENABLE, 1)[0], 0x30)
        m.assert_clear()

    def test_eye_tagged_objects_render_and_present_once_per_eye(self):
        m = RawMachine(); m.establish()
        left, right = 0x80000010, 0xC0000011
        for packet in (tagged_put(left, 100, 100), tagged_put(right, 200, 100)):
            reply, _ = m.send_scene(packet); self.assertEqual(reply[3], 0)
        samples = []
        m.on_submit = lambda: samples.append((m.read(G.PANEL_ENABLE, 1)[0], m.panel_pixel(106, 106), m.panel_pixel(206, 106)))
        reply, _ = m.send_scene(refs_show([1, left, right])); self.assertEqual(reply[3], 0)
        self.assertEqual(samples, [(0x20, 7, 0), (0x10, 0, 7)],
                         "the left panel gets only the left object, then the right panel only the right one")
        self.assertEqual(m.read(G.PANEL_ENABLE, 1)[0], 0x30)
        self.assertEqual(m.panel_pixel(6, 6), 7, "shared objects draw in both passes")
        # Without tagged objects the scene presents once to both panels again.
        before = len(m.submits())
        reply, _ = m.send_scene(refs_show([1])); self.assertEqual(reply[3], 0)
        self.assertEqual(m.panel_enables[before:], [0x30])
        m.assert_clear()

    def test_a_synced_stereo_frame_redraws_only_its_change_and_keeps_each_eye(self):
        m = RawMachine()
        snapshots = []
        m.on_submit = lambda: snapshots.append((m.read(G.PANEL_ENABLE, 1)[0], m.read(m.framebuffer, G.FRAMEBUFFER_STRIDE*350)))
        m.establish()
        left, right = 0x80000010, 0xC0000011
        for packet in (tagged_put(left, 100, 100), tagged_put(right, 200, 100)):
            reply, _ = m.send_scene(packet); self.assertEqual(reply[3], 0)
        reply, _ = m.send_scene(refs_show([1, left, right])); self.assertEqual(reply[3], 0)
        first = len(m.submits())
        reply, _ = m.send_scene(tagged_put(right, 260, 100)); self.assertEqual(reply[3], 0)
        reply, _ = m.send_scene(refs_show([1, left, right])); self.assertEqual(reply[3], 0)
        moved = m.submits()[first:]
        self.assertEqual([enable for enable, _ in snapshots[first:]], [0x20, 0x10], "one present per eye")
        for _, _, (x1, y1, x2, y2), _ in moved:
            self.assertGreaterEqual(x1, 120, f"the unchanged left object is not redrawn: {(x1, y1, x2, y2)}")
        pixel = eye_panels(m, snapshots)
        self.assertEqual((pixel(0x20, 106, 106), pixel(0x20, 206, 106), pixel(0x20, 266, 106)), (7, 0, 0),
                         "the left panel keeps the left object and never shows the right one")
        self.assertEqual((pixel(0x10, 106, 106), pixel(0x10, 206, 106), pixel(0x10, 266, 106)), (0, 0, 7),
                         "the right panel shows only the moved right object")
        self.assertEqual((pixel(0x20, 6, 6), pixel(0x10, 6, 6)), (7, 7), "shared objects reach both panels")
        m.assert_clear()

    def test_a_fallback_present_makes_the_next_stereo_frame_redraw_every_tagged_object(self):
        m = RawMachine()
        snapshots = []
        m.on_submit = lambda: snapshots.append((m.read(G.PANEL_ENABLE, 1)[0], m.read(m.framebuffer, G.FRAMEBUFFER_STRIDE*350)))
        m.establish()
        left, right = 0x80000010, 0xC0000011
        for packet in (tagged_put(left, 100, 100), tagged_put(right, 200, 100)):
            reply, _ = m.send_scene(packet); self.assertEqual(reply[3], 0)
        reply, _ = m.send_scene(refs_show([1, left, right])); self.assertEqual(reply[3], 0)
        # LVGL draws a refused raw present to both panels, right eye's pixels included.
        m.fail_slice = True
        reply, _ = m.send_scene(moved_show_packet()); self.assertEqual(reply[3], 0)
        m.fail_slice = False
        reply, _ = m.send_scene(tagged_put(right, 260, 100)); self.assertEqual(reply[3], 0)
        before = len(m.submits())
        reply, _ = m.send_scene(refs_show([1, left, right])); self.assertEqual(reply[3], 0)
        self.assertEqual(m.panel_enables[-2:], [0x20, 0x10])
        for _, _, (x1, y1, x2, y2), _ in m.submits()[before:]:
            self.assertLessEqual(x1, 100, f"the resync covers the left object again: {(x1, y1, x2, y2)}")
            self.assertGreaterEqual(x2, 279, f"and the moved right object: {(x1, y1, x2, y2)}")
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
