#!/usr/bin/env python3
"""Execute pinned scene-session RV32 code using existing explicit native mocks.

The legacy graphics emulator remains unchanged. Only its in-process BUILD/hash
are overridden for this distinct scene profile, whose build flag is required.
"""
import argparse
import json
from pathlib import Path
import struct
import unittest

import graphics_runtime_emulator_test as graphics

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT/"runtime/build/scene-004"
SCENE_SHA = "cd849a72ecd662a79327d01f792ddbe6b09cd5d7a2a683aa05440301dced2bbd"
FONT, READY = 0x0438f77c, 0x0205a048
FONT_NATIVES = {0x042d153c: "font_metrics", 0x042d14be: "font_bitmap"}
graphics.NATIVES.update(FONT_NATIVES)
# The firmware text adapter draws the resource font at this ratio (native_text.h);
# the mock font is 4 high with its baseline 1 up, its glyph 3x2 with advance 3.
TEXT_SCALE = (4, 5)
GLYPH_VALUES = ((0, 5, 10), (15, 10, 5))
MOCK_FONT_HEIGHT, MOCK_FONT_BASELINE, MOCK_ADVANCE = 4, 1, 3


def scaled(value, num=TEXT_SCALE[0], den=TEXT_SCALE[1]):
    return (value*num + den//2)//den


def scaled_glyph(values=GLYPH_VALUES, num=TEXT_SCALE[0], den=TEXT_SCALE[1]):
    """The adapter's output for one mock glyph: {(dx, dy): gray}, each pixel the
    rounded mean of a 2x2 sample of the glyph box, as native_text.c draws it."""
    box_w, box_h = len(values[0]), len(values)
    w, h = max(1, scaled(box_w, num, den)), max(1, scaled(box_h, num, den))
    out = {}
    for oy in range(h):
        for ox in range(w):
            total = 0
            for k in range(4):
                sx = ((4*ox + (3 if k & 1 else 1))*box_w)//(4*w)
                sy = ((4*oy + (3 if k & 2 else 1))*box_h)//(4*h)
                total += values[sy][sx]
            out[(ox, oy)] = (total + 2)//4
    return out


def glyph_top(y, num=TEXT_SCALE[0], den=TEXT_SCALE[1]):
    """Top row of a mock glyph on a line at y: the scaled baseline less the scaled box."""
    return y + scaled(MOCK_FONT_HEIGHT - MOCK_FONT_BASELINE, num, den) - max(1, scaled(len(GLYPH_VALUES), num, den))


def glyph_left(x, index, num=TEXT_SCALE[0], den=TEXT_SCALE[1]):
    """Left column of the index-th glyph of a string at x (advances accumulate in 1/den px)."""
    return (x*den + index*MOCK_ADVANCE*num)//den
STEPS = []


def w16(data, offset, value):
    struct.pack_into("<H", data, offset, value)


def w32(data, offset, value):
    struct.pack_into("<I", data, offset, value)


def reset_packet():
    return bytes([41, 0, 0, 0, 0, 0])


def put_packet():
    data = bytearray(34); data[0] = 37; data[5] = 1
    w32(data, 6, 1); w32(data, 10, 1)
    data[14:18] = bytes([3, 1, 7, 0])
    for offset, value in ((18, 5), (20, 5), (22, 10), (24, 5)):
        w16(data, offset, value)
    return bytes(data)


def show_packet(tagged=False):
    data = bytearray(18); data[0] = 38; data[5] = 5 if tagged else 1
    w16(data, 8, 1); w32(data, 10, 1); w32(data, 14, 1)
    return bytes(data)


def animate_packet():
    data = bytearray(24); data[0] = 38; data[5] = 7
    data[10] = 4; w32(data, 11, 1); w16(data, 15, 100); w16(data, 17, 0)
    data[19] = 10; data[20:24] = bytes([0, 0, 255, 255])
    return bytes(data)


class SceneMachine(graphics.Machine):
    def __init__(self, *, alignment_four=False):
        self.alignment_four = alignment_four
        self.readonly_fixtures = {}
        super().__init__()
        assert self.build.get("scene_session") is True, "Expected explicit scene-session build"
        assert set(self.build["retained_scene_entries"]) == {
            "mm_scene_session_init", "mm_scene_session_dispatch", "mm_scene_session_pump", "mm_scene_session_dispose"}
        self.epoch, self.request_number, self.sequence_number = 0, 0, 0x30
        self.peak_core_bytes = 0
        self.font_metrics_calls = []
        self.font_missing = None
        self.fixed_readonly(READY, b"\x01", "font-ready")
        self.fixed_readonly(FONT, struct.pack("<IIiiI", 0, 0, 4, 1, 0), "mock-font-fields")
        self.font_bits = self.allocate(2, "mock-glyph-bits", b"\x1b\x90", writable=False)

    def fixed_readonly(self, address, data, tag):
        self.uc.mem_map(address & ~4095, 4096, graphics.u.UC_PROT_READ)
        self.uc.mem_write(address, data)
        self.readonly_fixtures[address] = (len(data), tag)

    def region(self, address, size, writing=False):
        for base, (length, tag) in self.readonly_fixtures.items():
            if base <= address and address+size <= base+length:
                assert not writing, "Write to immutable font fixture"
                return tag
        return super().region(address, size, writing)

    def allocate(self, size, tag, data=None, writable=True):
        if not self.alignment_four or tag != "owned":
            return super().allocate(size, tag, data, writable)
        # Model only the proven native four-byte allocation guarantee. Keep
        # each block at4mod8, with guards and the same ownership ledger.
        pointer = ((self.next_heap+7) & ~7)+4
        self.next_heap = pointer+size+32
        assert 0 < size < 0x200000 and self.next_heap < graphics.HEAP+0x400000
        self.allocations[pointer] = {"size": size, "tag": tag, "live": True, "writable": writable}
        self.uc.mem_write(pointer, bytes(size) if data is None else data)
        return pointer

    def native(self, name, args):
        if name == "font_metrics":
            font, glyph, cp, following = args[:4]
            assert font == FONT and cp in (65, 66) and following in (0, 65, 66)
            self.font_metrics_calls.append((cp, following))
            if cp == self.font_missing: return 0
            self.native_write(glyph, struct.pack("<IHHHhhBB", FONT, 3, 3, 2, 0, 0, 2, 0))
            return 1
        if name == "font_bitmap":
            assert args[0] == FONT and args[1] in (65, 66)
            return self.font_bits
        return super().native(name, args)

    def core_bytes(self):
        total = 0
        for pointer in self.owned_live():
            block = self.allocations[pointer]
            if block["size"] >= 8 and self.word(pointer) == block["size"] and self.word(pointer+4) in (0, 1):
                total += block["size"]
        self.peak_core_bytes = max(self.peak_core_bytes, total)
        assert total <= 170*1024, "Actual live scene allocations exceeded configured budget"
        return total

    def send_scene(self, payload, *, patch_epoch=True, reply_mode=None):
        data = bytearray(payload)
        self.request_number += 1; self.sequence_number = (self.sequence_number+1) & 255
        if len(data) >= 5 and 37 <= data[0] <= 41:
            if patch_epoch: w16(data, 1, self.epoch)
            if data[0] != 40: w16(data, 3, self.request_number)
        request = self.request(bytes(data))
        start_sent = len(self.sent)
        immediate, _ = self.service(0x7d, request, self.sequence_number)
        assert immediate is None and self.queue, "Expected deferred queued scene command"
        job = self.queue.pop(0)
        assert job == bytes([1, self.sequence_number])+struct.pack("<H", len(data))+data
        raw = bytes([0, 63, 0, 0])+struct.pack("<HH", 0x474c, len(job))+job
        envelope = self.allocate(len(raw), "worker-envelope", raw, writable=False)
        self.call("glassly_graphics_display", envelope, display=True)
        assert self.allocations[envelope]["live"], "Runtime freed borrowed queue envelope"
        values = self.sent[start_sent:]
        assert values and all(event == self.sequence_number for event, _ in values)
        cache = None
        for _, value in values:
            if "replyHex" in value:
                cache = bytes.fromhex(value["replyHex"])
                assert 10 <= len(cache) <= 250 and cache[0] == (data[0] if reply_mode is None else reply_mode)
                self.epoch = struct.unpack_from("<H", cache, 4)[0]
                break
        core = self.core_bytes()
        STEPS.append({"mode": data[0], "request": self.request_number, "event": self.sequence_number,
                      "responses": [value for _, value in values], "core_live_bytes": core,
                      "core_peak_bytes": self.peak_core_bytes})
        return cache, [value for _, value in values]

    def establish(self):
        reply, _ = self.send_scene(reset_packet())
        assert len(reply) == 13 and reply[3] == 0 and self.epoch != 0
        assert struct.unpack_from("<H", reply, 11)[0] == 64
        reply, _ = self.send_scene(put_packet()); assert reply[3] == 0
        reply, _ = self.send_scene(show_packet()); assert reply[3] == 0
        assert self.pixel(6, 6) == 7

    def pixel(self, x, y):
        assert self.image_sources
        pixels = self.image_sources[-1][4]
        value = self.read(pixels+64+y*300+x//2, 1)[0]
        return value & 15 if x & 1 else value >> 4

    def tick_at(self, time):
        self.now = time
        timer = next(iter(self.timers))
        self.call("tick", timer, display=True)
        self.core_bytes()

    def assert_clear(self):
        self.send_scene(b"\x0b")
        assert not self.images and not self.timers and not self.owned_live()


class SceneRuntimeTests(unittest.TestCase):
    def test_identity_and_reset_put_show_state_clear(self):
        m = SceneMachine()
        value, _ = m.service(0x7e)
        self.assertEqual(value["modes"], [11, 19, 20, 36, 37, 38, 39, 40, 41])
        self.assertEqual(value["storeKiB"], 64); self.assertEqual(value["maxMessageBytes"], 8192)
        self.assertTrue(value["builtinText"])
        m.establish()
        state = bytes([40])+bytes(8)
        reply, _ = m.send_scene(state)
        self.assertIn(reply[3], (5, 6, 7))
        self.assertGreater(struct.unpack_from("<I", reply, 6)[0], 0)
        allocations = list(m.owned_live()); m.now = 400
        _, values = m.send_scene(bytes([36, 0]))
        self.assertEqual(values[0]["result"], "ok")
        self.assertEqual(m.pixel(6, 6), 7); self.assertEqual(m.owned_live(), allocations)
        m.assert_clear()

    def test_settled_is_deferred_until_after_reply(self):
        m = SceneMachine(); m.establish()
        reply, values = m.send_scene(show_packet(tagged=True))
        self.assertEqual(reply[3], 0)
        self.assertEqual(len(values), 2)
        self.assertIn("replyHex", values[0]); self.assertEqual(values[1]["result"], "settled")
        self.assertEqual(values[1]["tag"], m.request_number)
        m.assert_clear()

    def test_actual_native_timer_pumps_200ms_scene_animation(self):
        m = SceneMachine(); m.establish()
        period = bytes([41, 0, 0, 0, 0, 2, 20])
        reply, _ = m.send_scene(period); self.assertEqual(reply[3], 0)
        reply, values = m.send_scene(animate_packet()); tag = m.request_number
        self.assertEqual(reply[3], 0); self.assertEqual(len(values), 1)
        before = len(m.sent)
        for offset in range(20, 201, 20): m.tick_at(100+offset)
        self.assertEqual(m.pixel(106, 6), 7); self.assertEqual(m.pixel(6, 6), 0)
        settled = [value for _, value in m.sent[before:] if value.get("result") == "settled"]
        self.assertEqual(settled, [{"glassly": "scene", "abi": 1, "result": "settled", "tag": tag}])
        m.assert_clear()

    def test_native_queue_drop_and_admission_headroom(self):
        m = SceneMachine(); m.drop_queue = True
        value, _ = m.service(0x7d, m.request(reset_packet()))
        self.assertIsNone(value); self.assertFalse(m.queue or m.images or m.owned_live())
        m = SceneMachine(); m.free_bytes = 32000
        value, _ = m.service(0x7d, m.request(reset_packet()))
        self.assertEqual(value["result"], "allocation-failed"); self.assertFalse(m.queue or m.owned_live())

    def test_scene_budget_guard_and_core_headroom_failure(self):
        m = SceneMachine(); m.establish()
        owner = m.images[next(iter(m.images))]["owner"]
        # Existing owner prefix has a 12-byte descriptor at offset20; the scene
        # context follows at32. Verify its magic before this internal callback test.
        session = owner+32; self.assertEqual(m.word(session), 0xc0ffee72)
        original_owned, old_native_calls = list(m.owned_live()), len(m.calls)
        m.call("allocate", session, 0, 170*1024, display=True)
        self.assertEqual(m.reg(10), 0)
        self.assertEqual(m.calls[old_native_calls:], [], "Aggregate budget rejection reached native allocator")
        self.assertEqual(m.owned_live(), original_owned)
        m.assert_clear()
        m = SceneMachine()
        m.send_scene(graphics.point_message())  # Owner/canvas exists, no retained cache yet.
        m.free_bytes = 48*1024+100
        reply, _ = m.send_scene(reset_packet())
        self.assertEqual(reply[3], 3); self.assertEqual(m.core_bytes(), 0)
        m.free_bytes = 0x80000; m.assert_clear()

    def test_malformed_request_and_expiry_ui_cleanup(self):
        m = SceneMachine()
        value, _ = m.service(0x7d, m.request(bytes([37])+bytes(8192)))
        self.assertEqual(value["result"], "invalid"); self.assertFalse(m.queue)
        m.establish()
        _, values = m.send_scene(bytes([38, 0, 0, 0, 0]))
        self.assertEqual(values[0]["result"], "invalid")
        self.assertEqual(m.pixel(6, 6), 7)
        m.tick_at(1100)
        self.assertFalse(m.images or m.timers or m.owned_live())
        m = SceneMachine(); m.establish(); m.active_launcher = False; m.tick_at(120)
        self.assertFalse(m.images or m.timers or m.owned_live())

    def test_native_four_byte_allocator_alignment(self):
        m = SceneMachine(alignment_four=True); m.establish()
        self.assertTrue(m.owned_live())
        self.assertTrue(all(pointer % 8 == 4 for pointer in m.owned_live()))
        m.send_scene(animate_packet()); m.tick_at(120)
        m.assert_clear()

    def test_actual_builtin_ascii_and_preflight_failure(self):
        m = SceneMachine(alignment_four=True)
        # Mode36 inline text: one3x2 mocked resource glyph at(10,10), drawn at
        # the adapter's4/5 as2x2 means (fontheight4/baseline1 put its top at y10).
        # Two passes execute actual native_text.c and firmware wrappers; only
        # glyph lookup is mocked.
        record = bytes([17, 1, 15, 0])+struct.pack("<hhhhB", 10, 10, 20, 10, 2)+b"AB"
        _, values = m.send_scene(bytes([36, 1])+record)
        self.assertEqual(values[0]["result"], "ok")
        self.assertEqual(m.font_metrics_calls, [(65, 66), (66, 0)]*2)
        self.assertEqual(scaled_glyph(), {(0, 0): 3, (1, 0): 8, (0, 1): 13, (1, 1): 8})
        for index in range(2):
            for (dx, dy), value in scaled_glyph().items():
                self.assertEqual(m.pixel(glyph_left(10, index)+dx, glyph_top(10)+dy), value)
        self.assertEqual(m.pixel(10, 12), 0, "nothing below the scaled box")
        before = m.read(m.image_sources[-1][4]+64, 105000)
        m.font_missing = 66
        shifted = bytes([17, 1, 15, 0])+struct.pack("<hhhhB", 30, 10, 20, 10, 2)+b"AB"
        m.send_scene(bytes([36, 1])+shifted)
        self.assertEqual(m.read(m.image_sources[-1][4]+64, 105000), before)
        m.assert_clear()


def main():
    global BUILD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=BUILD)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(); BUILD = args.build.resolve()
    graphics.BUILD, graphics.PINNED_SHA = BUILD, SCENE_SHA
    graphics.RESULTS.clear()
    assert graphics.u.__version__ == "2.1.4"
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(SceneRuntimeTests))
    report = {"format": "memomind-scene-runtime-emulation-v1", "build": str(BUILD),
              "blob_sha256": SCENE_SHA, "scene_session_required": True,
              "architecture": "Actual RV32 linked C/session/scene/native wrappers; native firmware APIs mocked",
              "native_stubs": {f"0x{k:08x}": v for k, v in graphics.NATIVES.items()},
              "all_passed": result.wasSuccessful(), "test_groups": result.testsRun,
              "successful_handler_calls": len(graphics.RESULTS), "calls": graphics.RESULTS, "steps": STEPS,
              "limitations": ["Native heap/LVGL/queue/sender APIs remain synthetic contracts, not hardware.",
                              "ASCII font metrics/bitmap/resources/readiness are mocked contracts; real OTA font resources are not present. Actual RV32 font wrappers, preflight and GRAY4 pixel drawing execute.",
                              "One retained rectangle and translation animation are exercised; broader scene/vector corpus is covered separately on host.",
                              "Aggregate budget failure invokes the real private allocator callback with an oversized request; not a public wire operation.",
                              "Measured stacks cover these cases only; no full worst-case RTOS/interrupt-stack proof."]}
    if args.report: args.report.write_text(json.dumps(report, indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
