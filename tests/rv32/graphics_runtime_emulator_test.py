#!/usr/bin/env python3
"""Execute linked graphics C/native adapters/geometry in RV32, mocking firmware APIs.

Unlike gate tests, this runs the actual C handlers and native.c extraction,
lookup and call wrappers. Only pinned external firmware functions are stubbed.
Synthetic allocator/LVGL/queue models are contracts, not hardware emulation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import unittest

import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT/"runtime/build/graphics-004"
PINNED_SHA = "08d478321f5340d06eab0f7007a49741a1ee7b1d8a3f716534221672ceac0b39"
ENTRY, RET, CALLBACK_RET = 0x0439bea0, 0x05000000, 0x05001000
BT_BASE, DISPLAY_BASE, HEAP = 0x03000000, 0x03010000, 0x06000000
CALLEE = (1, 2, 3, 4, 8, 9, *range(18, 28))
FP_CALLEE = (8, 9, *range(18, 28))
CALLER = (5, 6, 7, *range(10, 18), 28, 29, 30, 31)
NATIVES = {
    0x0433c294: "try_alloc", 0x0434e6ee: "free", 0x042eff8e: "release",
    0x042ef9f6: "json", 0x042ef924: "status", 0x0425abe8: "post",
    0x042e866e: "send", 0x042d01b2: "default_display", 0x042ccc62: "active_screen",
    0x0425db22: "base_app", 0x0425daf8: "top_app", 0x042cf47a: "child_count",
    0x042cf44e: "child", 0x042bd7d0: "image_create", 0x042c7894: "on_delete",
    0x042bd7fa: "image_source", 0x042c963e: "position", 0x042c96ec: "size",
    0x042cf61c: "image_delete", 0x042b68c8: "cache_invalidate",
    0x042c7854: "event_userdata", 0x042b27ca: "timer_create",
    0x042b285a: "timer_delete", 0x042d02c6: "now",
    0x0433c460: "free_bytes", 0x0433c4a4: "low_water",
}
RESULTS = []


class Machine:
    def __init__(self):
        self.build = json.loads((BUILD/"build.json").read_text())
        self.blob = (BUILD/"graphics.bin").read_bytes()
        assert hashlib.sha256(self.blob).hexdigest() == self.build["blob_sha256"] == PINNED_SHA
        elf = (BUILD/"graphics.elf").read_bytes()
        assert elf[:7] == b"\x7fELF\x01\x01\x01" and struct.unpack_from("<H", elf, 18)[0] == 243
        assert hashlib.sha256(elf).hexdigest() == self.build["elf_sha256"]
        self.symbols = self.build["symbols"]
        self.uc = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
        base, end = ENTRY & ~4095, (ENTRY+len(self.blob)+4095) & ~4095
        self.uc.mem_map(base, end-base, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_write(ENTRY, self.blob)
        for page in sorted({a & ~4095 for a in NATIVES} | {RET, CALLBACK_RET}):
            self.uc.mem_map(page, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for address in NATIVES:
            self.uc.mem_write(address, bytes.fromhex("67800000"))
        self.uc.mem_write(RET, bytes.fromhex("13000000"))
        self.uc.mem_write(CALLBACK_RET, bytes.fromhex("13000000"))
        self.uc.mem_map(BT_BASE, 4096, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(DISPLAY_BASE, 8192, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(HEAP, 0x400000, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.allocations, self.next_heap, self.requests, self.replies = {}, HEAP, {}, {}
        self.events, self.calls, self.queue, self.sent, self.images, self.timers = [], [], [], [], {}, {}
        self.children, self.callback_frames, self.image_sources = [], [], []
        self.request_releases = []
        self.now, self.free_bytes, self.low_water = 100, 0x80000, 0x40000
        self.free_values = []
        self.fail_json = self.fail_status = self.fail_image = self.fail_event = self.fail_timer = False
        self.fail_alloc_sizes, self.drop_queue = set(), False
        self.active_launcher, self.screen_present = True, True
        self.stack_base, self.stack_top, self.min_sp = BT_BASE, BT_BASE+4096, BT_BASE+4096
        self.cpu_writes, self.native_writes, self.instructions = 0, 0, 0
        self.parent = self.allocate(64, "native-parent")
        self.display = self.allocate(32, "native-display")
        self.uc.hook_add(u.UC_HOOK_CODE, self.instruction)
        self.uc.hook_add(u.UC_HOOK_MEM_READ, self.memory_read)
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self.memory_write)

    def reg(self, index):
        return self.uc.reg_read(getattr(r, f"UC_RISCV_REG_X{index}"))

    def set(self, index, value):
        self.uc.reg_write(getattr(r, f"UC_RISCV_REG_X{index}"), value & 0xffffffff)

    def allocate(self, size, tag, data=None, writable=True):
        assert 0 < size < 0x200000
        pointer = (self.next_heap+15) & ~15
        self.next_heap = pointer+size+32
        assert self.next_heap < HEAP+0x400000
        self.allocations[pointer] = {"size": size, "tag": tag, "live": True, "writable": writable}
        self.uc.mem_write(pointer, bytes(size) if data is None else data)
        return pointer

    def region(self, address, size, writing=False):
        if self.stack_base <= address and address+size <= self.stack_top:
            return "stack"
        if not writing and ENTRY <= address and address+size <= ENTRY+len(self.blob):
            return "flash"
        for pointer, block in self.allocations.items():
            if block["live"] and pointer <= address and address+size <= pointer+block["size"]:
                assert not writing or block["writable"], f"Write to immutable {block['tag']}"
                return block["tag"]
        raise AssertionError(f"Out-of-bounds/use-after-free {'write' if writing else 'read'} {address:#x}+{size}")

    def read(self, address, size):
        self.region(address, size)
        return bytes(self.uc.mem_read(address, size))

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def native_write(self, address, data):
        self.region(address, len(data), writing=True)
        self.native_writes += 1
        self.uc.mem_write(address, data)

    def memory_read(self, uc, access, address, size, value, userdata):
        self.region(address, size)

    def memory_write(self, uc, access, address, size, value, userdata):
        self.region(address, size, writing=True)
        self.cpu_writes += 1

    def discard(self, pointer):
        block = self.allocations[pointer]
        assert block["live"], f"Double free {pointer:#x}"
        self.uc.mem_write(pointer, b"\xdd"*block["size"])
        block["live"] = False
        self.events.append(("free", pointer, block["tag"]))

    def cstring(self, pointer):
        out = bytearray()
        for i in range(1024):
            char = self.read(pointer+i, 1)[0]
            if not char:
                return out.decode("ascii")
            out.append(char)
        raise AssertionError("Unterminated native text argument")

    def request(self, payload, *, next_node=0, kind=1, header_null=False, data_null=False, declared=None):
        data = self.allocate(max(1, len(payload)), "request-data", payload or bytes(1), writable=False)
        length = len(payload) if declared is None else declared
        header = self.allocate(8, "request-header", bytes([kind])+length.to_bytes(3, "little")+
                               struct.pack("<I", 0 if data_null else data), writable=False)
        node = self.allocate(8, "request-node", struct.pack("<II", next_node, 0 if header_null else header), writable=False)
        self.requests[node] = [node, header, data]
        return node

    def response(self, value):
        pointer = self.allocate(16, "native-response")
        self.replies[pointer] = value
        return pointer

    def return_native(self, value=0):
        continuation = self.reg(1)
        assert ENTRY <= continuation < ENTRY+len(self.blob) or continuation in (RET, CALLBACK_RET)
        for index in CALLER:
            self.set(index, 0xd0000000+index*0x101)
        self.set(10, value)
        self.uc.reg_write(r.UC_RISCV_REG_PC, continuation)

    def instruction(self, uc, address, size, userdata):
        self.instructions += 1
        sp = self.reg(2)
        assert self.stack_base <= sp <= self.stack_top and sp % 16 == 0, "Task stack bound/alignment violated"
        self.min_sp = min(self.min_sp, sp)
        if address == CALLBACK_RET:
            saved, image, event = self.callback_frames.pop()
            for index in CALLEE:
                expected = CALLBACK_RET if index == 1 else saved[index]
                assert self.reg(index) == expected, f"DELETE callback corrupted x{index}"
            self.discard(event)
            self.finish_image_delete(image)
            for index, value in saved.items():
                self.set(index, value)
            self.return_native()
        elif address in NATIVES:
            name = NATIVES[address]
            args = tuple(self.reg(i) for i in range(10, 18))
            self.calls.append(name)
            result = self.native(name, args)
            if result is not None:
                self.return_native(result)
        else:
            assert ENTRY <= address < ENTRY+len(self.blob), f"Unexpected executable address {address:#x}"

    def native(self, name, args):
        a0, a1, a2, a3, a4 = args[:5]
        if name == "try_alloc":
            assert a1 == 0 and 0 < a0 <= 0x1ffffc
            self.events.append(("try_alloc", a0))
            return 0 if a0 in self.fail_alloc_sizes else self.allocate(a0, "owned")
        if name == "free":
            assert self.allocations[a0]["tag"] == "owned"
            self.discard(a0); return 0
        if name == "release":
            pointer = self.word(a0)
            if pointer in self.requests:
                assert pointer not in self.request_releases
                self.request_releases.append(pointer)
                self.events.append(("release_request", pointer))
                for part in self.requests[pointer]: self.discard(part)
            elif pointer:
                assert pointer in self.replies
                self.events.append(("release_response", pointer))
                self.discard(pointer)
            self.native_write(a0, bytes(4)); return 0
        if name == "json":
            value = json.loads(self.cstring(a0))
            self.events.append(("json", value))
            return 0 if self.fail_json else self.response(value)
        if name == "status":
            assert (a0, a1) == (4, 0)
            return 0 if self.fail_status else self.response({"status": 4})
        if name == "post":
            assert (a0, a1, a4) == (63, 0x474c, 2)
            assert self.allocations[a2]["tag"] == "owned" and self.allocations[a2]["live"]
            copied = self.read(a2, a3)
            self.events.append(("queue_copy", a2, copied.hex()))
            if not self.drop_queue: self.queue.append(copied)
            return 0
        if name == "send":
            assert (a1, a2, a4) == (15, 0x7d, 1)
            assert self.allocations[a3]["live"] and a3 in self.replies
            self.sent.append((a0, self.replies[a3]))
            self.events.append(("send_copy", a3)); return 1
        if name == "default_display": return self.display
        if name == "active_screen":
            assert a0 == self.display
            return self.parent if self.screen_present else 0
        if name in ("base_app", "top_app"):
            return 0x0200fc7c if self.active_launcher else 0x0200abcd
        if name == "child_count":
            assert a0 == self.parent; return len(self.children)
        if name == "child":
            assert a0 == self.parent
            return self.children[a1] if a1 < len(self.children) else 0
        if name == "image_create":
            assert a0 == self.parent
            if self.fail_image: return 0
            image = self.allocate(64, "native-image")
            self.children.append(image); self.images[image] = {"callback": 0, "owner": 0, "extra": []}
            return image
        if name == "on_delete":
            assert a0 in self.images and a1 == self.symbols["deleted"] and a2 == 0x21
            if self.fail_event: return 0
            spec = self.allocate(40, "native-spec")
            record = self.allocate(12, "native-event-record", struct.pack("<IIB3x", a1, a3, a2))
            self.native_write(a0+8, struct.pack("<I", spec))
            self.native_write(spec+12, struct.pack("<I", record))
            self.native_write(spec+0x22, struct.pack("<H", 1))
            self.images[a0].update(callback=a1, owner=a3, extra=[spec, record])
            return record
        if name == "image_source":
            assert a0 in self.images
            header, length, pixels = struct.unpack("<III", self.read(a1, 12))
            assert header == (350 << 21) | (600 << 10) | 9 and length == 105064
            assert a1 == self.images[a0]["owner"]+20
            assert self.allocations[pixels]["tag"] == "owned"
            self.read(pixels, length)
            self.image_sources.append((a0, a1, header, length, pixels)); return 0
        if name == "position":
            assert a0 in self.images and (a1, a2) == (0, 0); return 0
        if name == "size":
            assert a0 in self.images and (a1, a2) == (600, 350); return 0
        if name == "image_delete":
            assert a0 in self.images
            self.events.append(("image_delete", a0))
            info = self.images[a0]
            if not info["callback"]:
                self.finish_image_delete(a0); return 0
            event = self.allocate(16, "native-delete-event")
            self.native_write(event+12, struct.pack("<I", info["owner"]))
            saved = {i: self.reg(i) for i in range(1, 32)}
            self.callback_frames.append((saved, a0, event))
            self.set(10, event); self.set(1, CALLBACK_RET)
            self.uc.reg_write(r.UC_RISCV_REG_PC, info["callback"])
            return None
        if name == "cache_invalidate":
            self.read(a0, 12); return 0
        if name == "event_userdata": return self.word(a0+12)
        if name == "timer_create":
            assert a0 == self.symbols["tick"] and a1 == 20
            if self.fail_timer: return 0
            timer = self.allocate(16, "native-timer")
            self.native_write(timer+12, struct.pack("<I", a2))
            self.timers[timer] = {"callback": a0, "owner": a2}; return timer
        if name == "timer_delete":
            assert a0 in self.timers
            del self.timers[a0]; self.discard(a0); return 0
        if name == "now": return self.now
        if name == "free_bytes": return self.free_values.pop(0) if self.free_values else self.free_bytes
        if name == "low_water": return self.low_water
        raise AssertionError("Unknown native contract: "+name)

    def finish_image_delete(self, image):
        info = self.images.pop(image)
        self.children.remove(image)
        for pointer in info["extra"]: self.discard(pointer)
        self.discard(image)

    def call(self, symbol, *args, display=False):
        self.stack_base, size = (DISPLAY_BASE, 8192) if display else (BT_BASE, 4096)
        self.stack_top, self.min_sp = self.stack_base+size, self.stack_base+size
        self.uc.mem_write(self.stack_base, b"\xcc"*size)
        for i in range(1, 32): self.set(i, 0xa0000000+i*0x101)
        for i, value in {1: RET, 2: self.stack_top, 3: 0x02011688, 4: 0x0200abcd}.items(): self.set(i, value)
        for i, value in enumerate(args): self.set(10+i, value)
        initial = {i: self.reg(i) for i in CALLEE}
        for i in FP_CALLEE:
            self.uc.reg_write(getattr(r, f"UC_RISCV_REG_F{i}"), 0x3f800000+i)
        fp_initial = {i: self.uc.reg_read(getattr(r, f"UC_RISCV_REG_F{i}")) for i in FP_CALLEE}
        start = self.symbols[symbol] if isinstance(symbol, str) else symbol
        old_calls, old_instructions = len(self.calls), self.instructions
        self.uc.emu_start(start, RET, count=3000000)
        assert self.uc.reg_read(r.UC_RISCV_REG_PC) == RET, "Instruction budget exhausted or no return"
        assert not self.callback_frames
        for i in CALLEE: assert self.reg(i) == initial[i], f"Handler corrupted x{i}"
        for i in FP_CALLEE:
            assert self.uc.reg_read(getattr(r, f"UC_RISCV_REG_F{i}")) == fp_initial[i], f"Handler corrupted f{i}"
        result = {"entry": symbol, "task": "display" if display else "BT", "stack_capacity": size,
                  "observed_stack_bytes": self.stack_top-self.min_sp,
                  "instructions": self.instructions-old_instructions,
                  "native_calls": self.calls[old_calls:], "callee_gp_tp_preserved": True,
                  "callee_fp_registers_preserved": True,
                  "all_cpu_memory_accesses_bounded": True}
        RESULTS.append(result)
        return result

    def service(self, command, request=0, sequence=0x51):
        seq = 0 if sequence is None else self.allocate(1, "sequence", bytes([sequence]), writable=False)
        response = self.allocate(4, "caller-response", bytes.fromhex("efbeadde"))
        result = self.call("service_entry", command, request, seq, response)
        reply = self.word(response)
        return (self.replies[reply] if reply else None), result

    def envelope(self, payload, event=0x51, version=1, declared=None):
        length = len(payload) if declared is None else declared
        job = bytes([version, event])+struct.pack("<H", length)+payload
        raw = bytes([0, 63, 0, 0])+struct.pack("<HH", 0x474c, len(job))+job
        return self.allocate(len(raw), "worker-envelope", raw, writable=False)

    def execute_display(self, payload, **kwargs):
        envelope = self.envelope(payload, **kwargs)
        result = self.call("glassly_graphics_display", envelope, display=True)
        assert self.allocations[envelope]["live"], "Handler freed borrowed worker envelope"
        return result

    def owned_live(self):
        return [ptr for ptr, block in self.allocations.items() if block["live"] and block["tag"] == "owned"]


def point_message():
    # Shape1: one-pixel line from (2,3) to (2,3), color10, stroke1.
    return bytes([36, 1, 1, 0, 10, 1])+struct.pack("<8h", 2, 3, 2, 3, 0, 0, 0, 0)


class GraphicsRuntimeTests(unittest.TestCase):
    def test_passive_probe_real_hex_format_and_request_cleanup(self):
        for nonempty in (False, True):
            m = Machine(); m.free_bytes, m.low_water = 0xfedcba98, 0x01234567
            request = m.request(b"opaque") if nonempty else 0
            value, result = m.service(0x7e, request)
            self.assertEqual(value["freeBytesHex"], "fedcba98")
            self.assertEqual(value["lowWaterBytesHex"], "01234567")
            self.assertEqual(value["modes"], [11, 36]); self.assertEqual(value["profile"], "H001Y-1.0.3.127")
            self.assertEqual(value["shapeTypes"], list(range(1, 14)))
            self.assertEqual(m.request_releases, [request] if nonempty else [])
            self.assertFalse(m.queue or m.images or m.owned_live())
            self.assertLessEqual(result["observed_stack_bytes"], 4096)

    def test_command_native_extraction_copies_before_request_and_job_free(self):
        m = Machine(); payload = point_message(); request = m.request(payload)
        response, _ = m.service(0x7d, request, sequence=0xa7)
        self.assertIsNone(response)
        self.assertEqual(m.queue, [bytes([1, 0xa7])+struct.pack("<H", len(payload))+payload])
        self.assertEqual(m.request_releases, [request]); self.assertFalse(m.owned_live())
        copy_index = next(i for i, event in enumerate(m.events) if event[0] == "queue_copy")
        job = m.events[copy_index][1]
        self.assertTrue(any(e[0] == "release_request" for e in m.events[:copy_index]))
        self.assertTrue(any(e[:2] == ("free", job) for e in m.events[copy_index+1:]))

    def test_malformed_parsed_tlv_and_incomplete_geometry_rejected(self):
        cases = [(b"\x0b", {"next_node": 0x1234}), (b"\x0b", {"kind": 5}),
                 (b"\x0b", {"header_null": True}), (b"\x0b", {"data_null": True}),
                 (b"\x24\x01\x01", {}), (b"", {}), (b"\x0b", {"declared": 5103}),
                 (b"\x0b", {"declared": 0x100000})]
        for payload, options in cases:
            with self.subTest(options=options, payload=payload):
                m = Machine(); request = m.request(payload, **options)
                value, _ = m.service(0x7d, request)
                self.assertEqual(value["result"], "invalid")
                self.assertFalse(m.queue or m.owned_live()); self.assertEqual(m.request_releases, [request])
        for null_request, null_sequence in ((True, False), (False, True)):
            m = Machine(); request = 0 if null_request else m.request(b"\x0b")
            value, _ = m.service(0x7d, request, None if null_sequence else 0x51)
            self.assertEqual(value["result"], "invalid"); self.assertFalse(m.queue)

    def test_command_allocation_failure_and_queue_drop_have_no_false_success(self):
        m = Machine(); m.fail_alloc_sizes.add(5)
        value, _ = m.service(0x7d, m.request(b"\x0b"))
        self.assertEqual(value["result"], "allocation-failed"); self.assertFalse(m.owned_live())
        m = Machine(); m.drop_queue = True
        value, _ = m.service(0x7d, m.request(b"\x0b"))
        self.assertIsNone(value); self.assertFalse(m.queue or m.owned_live())

    def test_display_real_geometry_descriptor_palette_and_clear_callback(self):
        m = Machine(); result = m.execute_display(point_message(), event=0x92)
        self.assertEqual(m.sent[-1], (0x92, {"glassly": "graphics", "abi": 1, "result": "ok", "presentation": "scheduled"}))
        self.assertEqual(len(m.images), 1); self.assertEqual(len(m.timers), 1)
        image, descriptor, header, length, pixels = m.image_sources[-1]
        self.assertEqual((header, length), ((350 << 21) | (600 << 10) | 9, 105064))
        self.assertEqual(m.read(pixels, 64), b"".join(struct.pack("<I", 0xff000000 | (i*17)*0x010101) for i in range(16)))
        raster = m.read(pixels+64, 105000)
        expected = bytearray(105000); expected[3*300+1] = 0xa0
        self.assertEqual(raster, bytes(expected))
        self.assertLessEqual(result["observed_stack_bytes"], 8192)
        m.execute_display(b"\x0b", event=0x93)
        self.assertEqual(m.sent[-1][1]["result"], "cleared")
        self.assertFalse(m.images or m.timers or m.owned_live())
        self.assertTrue(any(e[0] == "image_delete" and e[1] == image for e in m.events))

    def test_timer_callback_real_expiry_and_ui_yield_cleanup(self):
        for ui_changed in (False, True):
            m = Machine(); m.execute_display(point_message())
            timer = next(iter(m.timers)); m.now = 1099
            m.call("tick", timer, display=True)
            self.assertEqual(len(m.images), 1)
            if ui_changed: m.active_launcher = False
            else: m.now = 1100
            m.call("tick", timer, display=True)
            self.assertFalse(m.images or m.timers or m.owned_live())

    def test_display_ui_guard_and_all_injected_create_failure_cleanup(self):
        m = Machine(); m.active_launcher = False
        m.execute_display(point_message())
        self.assertEqual(m.sent[-1][1]["result"], "stock-ui-active")
        self.assertFalse(m.images or m.owned_live())
        m = Machine(); m.execute_display(point_message()); m.active_launcher = False
        m.execute_display(point_message())
        self.assertEqual(m.sent[-1][1]["result"], "stock-ui-active")
        self.assertFalse(m.images or m.timers or m.owned_live())
        for failure in ("owner", "image", "event", "timer", "pixels", "initial_headroom", "late_headroom"):
            with self.subTest(failure=failure):
                m = Machine()
                if failure == "owner": m.fail_alloc_sizes.add(32)
                if failure == "image": m.fail_image = True
                if failure == "event": m.fail_event = True
                if failure == "timer": m.fail_timer = True
                if failure == "pixels": m.fail_alloc_sizes.add(105064)
                if failure == "initial_headroom": m.free_bytes = 65536
                if failure == "late_headroom": m.free_values = [0x80000, 65536]
                m.execute_display(point_message())
                self.assertEqual(m.sent[-1][1]["result"], "allocation-failed")
                self.assertFalse(m.images or m.timers or m.owned_live())

    def test_display_malformed_job_and_response_allocation_failure(self):
        for options in ({"version": 2}, {"declared": 2}):
            m = Machine(); m.execute_display(b"\x0b", **options)
            self.assertEqual(m.sent[-1][1]["result"], "invalid"); self.assertFalse(m.images)
        m = Machine(); m.fail_json = True
        value, _ = m.service(0x7e)
        self.assertEqual(value, {"status": 4})
        m = Machine(); m.fail_json = m.fail_status = True
        m.execute_display(b"\x0b")
        self.assertFalse(m.sent or m.images or m.owned_live())


def main():
    global BUILD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=BUILD)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    BUILD = args.build.resolve()
    assert u.__version__ == "2.1.4"
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(GraphicsRuntimeTests))
    try:
        build_label = str(BUILD.relative_to(ROOT))
    except ValueError:
        build_label = str(BUILD)
    report = {"format": "memomind-graphics-runtime-emulation-v1", "kind": "Actual RV32 C/native adapters/geometry with mocked external firmware APIs",
              "build": build_label, "blob_sha256": PINNED_SHA, "unicorn_version": u.__version__,
              "architecture": "UC_ARCH_RISCV / UC_MODE_RISCV32", "native_stubs": {f"0x{k:08x}": v for k, v in NATIVES.items()},
              "test_groups": result.testsRun, "all_passed": result.wasSuccessful(), "successful_handler_calls": len(RESULTS),
              "calls": RESULTS,
              "limitations": ["Native heap/LVGL/queue/serializer implementations and hardware are mocked.",
                              "Injected NULL returns test cleanup; actual native LVGL allocations may assert instead.",
                              "Parsed TLV node/header/data allocations must be valid; arbitrary forged pointers are not a supported parser input.",
                              "4KiB BT and 8KiB display stack checks are synthetic bounds, not an exhaustive stack proof.",
                              "Graphics coverage uses one real point-line geometry record; portable suites cover additional geometry algorithms.",
                              "No real transport serialization, display scanout, concurrent RTOS scheduling or device execution is established."]}
    if args.report: args.report.write_text(json.dumps(report, indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
