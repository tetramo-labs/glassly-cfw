#!/usr/bin/env python3
"""Run the linked GLASSLYCFW RV32 blob under Unicorn with mocked stock calls.

Executes the actual machine code from a build_runtime.py output directory:
the router gate, glassly_command, the UI-task jobs, the scene pump and the
flush gate. Every stock entry point the runtime binds is a hooked `ret` that a
Python mock answers: the heap is a real arena, gui_post_async queues the job
for a separate UI-task stack, the critical section, display mutex, panel,
clock and LVGL timer are mocks too.

Strict like the device (Unicorn itself would accept all of these):
  - instructions outside RV32IMC trap (the NIMO core has no A extension),
  - misaligned halfword/word loads and stores trap,
  - every data access must fall in a region the runtime owns: its RAM block
    and breadcrumbs, the few stock flags it reads or refreshes, a live heap
    allocation, the current task's stack, the request payload (read-only);
    anything else, including a freed allocation, is an access fault.
A trap raises DeviceFault: on the glasses it is a reset. The run also records
the peak stack depth per task and every multi-byte read of packet bytes.

The hardware step list (tests/hardware/steps-<revision>.json) replays in
order with the payloads the Mac harness sends and the heap the glasses
reported (194,520 bytes free before the lease). This checks the compiled code
and the gates' register contracts, not the stock firmware or a device. Run
with the Unicorn venv (~/dev/glassly-memomind-one-cfw/.tools/rv32-tests-venv).
"""
import argparse
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import zlib

import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import runtime_scan  # noqa: E402
import scene_packets  # noqa: E402

TOOLS = ROOT / ".tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin"
RAM, RAM_SIZE = 0x02000000, 0x00100000
LIT, BLANK, LEFT, DISPLAY_ON = 0x02011A3A, 0x02012A38, 0x02011B18, 0x02011FA6
PANEL_UP, PANEL_BRIGHTNESS = 0x020121BE, 0x0201198E
HEAP, HEAP_SIZE = 0x03000000, 0x00200000
SCRATCH = 0x03E00000
PAYLOAD_AREA = (SCRATCH, SCRATCH + 0x10000)
PAYLOAD = SCRATCH + 0x1004            # the stock chain buffer + 4: word aligned
# The GUI task: 32 KiB stack; its loop (0x04206762, 64 B) and async drain
# (0x04206342, 512 B) sit above a posted job.
UI_STACK = (0x03E78000, 0x03E80000)
UI_TOP = UI_STACK[1] - 576
ROUTER_STACK = (0x03EF0000, 0x03F00000)  # size unknown on the device; 64 KiB window here
STACK_TOP = ROUTER_STACK[1]
RETURN = 0x05000000
FAKE_FLUSH = 0x05001000
ROUTER_UNROUTED, ROUTER_EPILOGUE = 0x0426E036, 0x0426E112
KICK_REJOIN, KICK_TAIL = 0x041F7044, 0x041F705C   # the frame kick after the hooked bytes; its frame-task tail call
KICK_FLAG = 0x02011FA5                             # 1157(gp): the byte the kick tests first
UI_DISPATCH_REJOIN = 0x04208DDA                    # the stock UI dispatcher after the hooked prologue
ANCS_WHITELIST_REJOIN = 0x042767D8                 # the stock whitelist check after the hooked prologue
ANCS_INTAKE_RETURN = 0x0427400E                    # the ANCS attribute handler after the hooked call
GP = 0x02011B20
# The stock framebuffers and their index bytes (runtime/nimo/stock.h). The
# machine starts flipped (front 0, back 1), so the lease's canvas is buffer 0.
FB, FB_BYTES = 0x0202F064, 0x12750
FB_BACK, FB_FRONT = 0x020120FB, 0x0201198A
STOCK = {
    "send_response": 0x0426E2D6, "is_master": 0x041FC24E, "gui_post_async": 0x04206CF2,
    "malloc": 0x041FA772, "free": 0x041FA784, "heap_free": 0x042F7AEA, "heap_largest": 0x042F7A38,
    "now_ms": 0x041FA73C, "display_mutex": 0x041FC706, "os_lock": 0x0200ED06, "os_unlock": 0x0200ED7E,
    "panel_flush": 0x04200DB2, "set_brightness": 0x041FEC90, "repaint_all": 0x041FE71A,
    "cancel_auto_off": 0x04268164, "lv_screen_active": 0x0424143C, "lv_obj_invalidate": 0x04233F3A,
    "lv_timer_create": 0x0423F7F8, "lv_timer_delete": 0x0423F89E,
    "critical_enter": 0x041FA74E, "critical_exit": 0x041FA760, "ancs_intake": 0x0428C846,
}
MUTEX, SCREEN, TIMER = 0x02090000, 0x02090100, 0x02090200
W, H, STRIDE = 540, 280, 270
HW_HEAP_FREE = 194_520                 # step 2 on the glasses, 2026-11-09
HW_LARGEST_GAP = 194_520 - 190_020
STAGES = ["idle", "router", "posted", "dispatch", "render", "present", "reply", "done", "tick"]
RESULTS = []
EVIDENCE = {}


class DeviceFault(Exception):
    """What the core would trap on; the glasses reset."""


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def readelf(build):
    path = build / "symbols.txt"
    if path.is_file():
        return path.read_text()
    return subprocess.run([str(TOOLS / "riscv-none-elf-readelf"), "-sW", str(build / "runtime.elf")],
                          check=True, capture_output=True, text=True).stdout


class Machine:
    def __init__(self, build, left=True, heap_free=400 * 1024, largest_gap=0, payload=PAYLOAD,
                 crumbs=None, isa_traps=True):
        report = json.loads((build / "build.json").read_text())
        self.report = report
        self.revision = report["revision"]
        self.symbols = {k: int(v, 16) for k, v in report["symbols"].items()}
        self.ram_block = tuple(int(v, 16) for v in report["ram_block"])
        self.crumbs = tuple(int(v, 16) for v in report.get("crumbs", ["0x0", "0x0"]))
        blob = (build / "runtime.bin").read_bytes()
        origin = int(report["runtime_origin"], 16)
        self.blob = (origin, origin + len(blob))
        self.uc = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
        base = origin & ~0xFFF
        self.uc.mem_map(base, (origin + len(blob) - base + 0xFFF) & ~0xFFF, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_write(origin, blob)
        stops = [ROUTER_UNROUTED, ROUTER_EPILOGUE, KICK_REJOIN, KICK_TAIL, UI_DISPATCH_REJOIN, ANCS_WHITELIST_REJOIN,
                 ANCS_INTAKE_RETURN]
        pages = sorted({a & ~0xFFF for a in [*STOCK.values(), *stops]} - {RAM & ~0xFFF})
        for page in pages:
            if not RAM <= page < RAM + RAM_SIZE:
                self.uc.mem_map(page, 0x1000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_map(RAM, RAM_SIZE, u.UC_PROT_READ | u.UC_PROT_WRITE | u.UC_PROT_EXEC)
        self.uc.mem_map(HEAP, HEAP_SIZE, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(SCRATCH, STACK_TOP - SCRATCH, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(RETURN, 0x2000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        ret = struct.pack("<I", 0x00008067)
        self.by_address = {}
        for name, address in STOCK.items():
            self.uc.mem_write(address, ret)
            self.by_address[address] = name
        for address in (RETURN, FAKE_FLUSH, *stops):
            self.uc.mem_write(address, ret)
        self.uc.mem_write(FB, bytes([0x3C]) * FB_BYTES + bytes([0x5A]) * FB_BYTES)
        self.uc.mem_write(FB_FRONT, b"\x00")
        self.uc.mem_write(FB_BACK, b"\x01")
        self.uc.mem_write(LEFT, bytes([1 if left else 0]))
        self.uc.mem_write(DISPLAY_ON, b"\x01")
        self.uc.mem_write(PANEL_UP, b"\x01")
        self.uc.mem_write(PANEL_BRIGHTNESS, struct.pack("<H", 4))   # Nimo-4026's level, 2026-11-10
        self.uc.mem_write(BLANK, struct.pack("<I", 5))
        if crumbs is not None:
            self.uc.mem_write(self.crumbs[0], crumbs)
        self.replies, self.queue, self.flushes, self.calls = [], [], [], []
        self.allocations, self.freed, self.lock_depth, self.now = {}, [], 0, 5000
        self.heap_next, self.heap_base_free, self.largest_gap = HEAP + 4, heap_free, largest_gap
        self.timer_fn, self.fake_flush_calls, self.stopped_at = None, [], None
        self.critical, self.payload, self.payload_len, self.jobs = 0, payload, 0, {}
        self.context, self.depth, self.wide_packet_reads = "router", {}, {}
        self.fault_hook = None
        self.allowed = [  # (lo, hi, writable) of stock RAM the runtime may touch
            (self.ram_block[0], self.ram_block[1], True), (self.crumbs[0], self.crumbs[1], True),
            (LIT, LIT + 1, True), (BLANK, BLANK + 4, True), (LEFT, LEFT + 1, False),
            (DISPLAY_ON, DISPLAY_ON + 1, False), (PANEL_UP, PANEL_UP + 1, False),
            (PANEL_BRIGHTNESS, PANEL_BRIGHTNESS + 2, False), (KICK_FLAG, KICK_FLAG + 1, False),
            (FB_BACK, FB_BACK + 1, True), (FB_FRONT, FB_FRONT + 1, True),
            (FB, FB + FB_BYTES, True), (FB + FB_BYTES, FB + 2 * FB_BYTES, False)]
        self.tick_ms = 10
        for address in [*STOCK.values(), RETURN, FAKE_FLUSH, *stops]:
            self.uc.hook_add(u.UC_HOOK_CODE, self.stub, begin=address, end=address)
        funcs = runtime_scan.parse_listing((build / "runtime.asm").read_text(),
                                           runtime_scan.code_ranges(readelf(build)))
        self.isa = runtime_scan.isa_violations(funcs)
        for row in self.isa if isa_traps else []:
            a = int(row["address"], 16)
            self.uc.hook_add(u.UC_HOOK_CODE, self.illegal, user_data=row, begin=a, end=a)
        self.uc.hook_add(u.UC_HOOK_MEM_READ | u.UC_HOOK_MEM_WRITE, self.access)
        self.uc.hook_add(u.UC_HOOK_BLOCK, self.block)
        self.uc.hook_add(u.UC_HOOK_MEM_INVALID, self.invalid)

    # --- registers and memory ------------------------------------------------
    def reg(self, x):
        return self.uc.reg_read(getattr(r, f"UC_RISCV_REG_X{x}"))

    def set(self, x, value):
        self.uc.reg_write(getattr(r, f"UC_RISCV_REG_X{x}"), value & 0xFFFFFFFF)

    def u8(self, address):
        return self.uc.mem_read(address, 1)[0]

    def u32(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def pc(self):
        return self.uc.reg_read(r.UC_RISCV_REG_PC)

    def where(self, pc=None):
        pc = self.pc() if pc is None else pc
        best = max(((a, n) for n, a in self.symbols.items() if a <= pc), default=(0, "?"))
        return f"{pc:#x} <{best[1]}+{pc - best[0]:#x}>"

    # --- traps ------------------------------------------------------------------
    def fault(self, kind, detail):
        raise DeviceFault(f"{kind}: {detail} at {self.where()} ({self.context} task)")

    def illegal(self, uc, address, size, row):
        self.fault("illegal instruction", f"{row['insn']} (not RV32IMC)")

    def invalid(self, uc, access, address, size, value, data):
        self.fault("access fault", f"unmapped access {access} at {address:#x}+{size}")

    def block(self, uc, address, size, data):
        sp = self.reg(2)
        if sp < self.min_sp:
            self.min_sp = sp

    def stack_window(self):
        return UI_STACK if self.context == "ui" else ROUTER_STACK

    def access(self, uc, access, address, size, value, data):
        write = access == u.UC_MEM_WRITE
        what = f"{'store' if write else 'load'} of {size} B at {address:#x}"
        if size > 1 and address % size:
            self.fault("misaligned", what)
        end = address + size
        if RAM <= address < RAM + RAM_SIZE:
            for lo, hi, writable in self.allowed:
                if lo <= address and end <= hi and (writable or not write):
                    return
            self.fault("stock RAM", what)
        elif HEAP <= address < HEAP + HEAP_SIZE:
            for start, length in self.allocations.items():
                if start <= address and end <= start + length:
                    if not write and size > 1:
                        for lo, hi in self.jobs.values():
                            if lo <= address < hi:
                                self.wide_packet_reads[self.where()] = size
                    return
            freed = any(s <= address < s + n for s, n in self.freed)
            self.fault("heap", f"{what} outside a live allocation{' (freed)' if freed else ''}")
        elif PAYLOAD_AREA[0] <= address < PAYLOAD_AREA[1]:
            if write:
                self.fault("payload", f"{what}: the request buffer is the router's")
            if size > 1 and self.payload <= address < self.payload + self.payload_len:
                self.wide_packet_reads[self.where()] = size
        elif SCRATCH <= address < STACK_TOP:
            lo, hi = self.stack_window()
            if not (lo <= address and end <= hi):
                self.fault("stack", f"{what} outside the {self.context} task's stack")
            if address < self.min_sp:
                self.min_sp = address
        elif not (self.blob[0] <= address < self.blob[1] and not write):
            self.fault("access fault", what)

    # --- stock mocks ------------------------------------------------------------
    def heap_free(self):
        return max(0, self.heap_base_free - sum(n + 8 for n in self.allocations.values()))

    def stub(self, uc, address, size, data):
        if address in (RETURN, ROUTER_UNROUTED, ROUTER_EPILOGUE, KICK_REJOIN, KICK_TAIL, UI_DISPATCH_REJOIN):
            self.stopped_at = address
            uc.emu_stop()
            return
        if address == FAKE_FLUSH:
            self.fake_flush_calls.append([self.reg(x) for x in (10, 11, 12, 13, 14)])
            self.set(10, 0x55)
            return
        name = self.by_address.get(address)
        if name is None:
            return
        a = [self.reg(x) for x in (10, 11, 12, 13, 14)]
        self.calls.append(name)
        if self.critical and name != "critical_exit":
            self.fault("critical section", f"{name} called with interrupts masked")
        if self.fault_hook:
            self.fault_hook(self, name, a)
        result = 0
        if name == "send_response":
            check(a[3] <= 590, f"reply of {a[3]} B overflows build_response")
            self.replies.append((a[0], a[1], bytes(self.uc.mem_read(a[2], a[3]))))
        elif name == "is_master":
            result = 1
        elif name == "gui_post_async":
            self.queue.append((a[0], a[1]))
            if a[0] == self.symbols.get("nimo_ui_scene") and a[1] in self.allocations:
                length = self.u32(a[1])
                start = a[1] + self.allocations[a[1]] - length
                self.jobs[a[1]] = (start, start + length)
            result = 1
        elif name == "malloc":
            size = a[0]
            if size and size + 8 <= self.heap_free() - self.largest_gap and \
                    self.heap_next + size + 8 <= HEAP + HEAP_SIZE:
                result = self.heap_next            # 4-aligned, never 8-aligned: the stock heap's promise
                self.allocations[result] = size
                self.uc.mem_write(result, b"\xa5" * size)
                self.heap_next = (result + size + 8 + 7) // 8 * 8 + 4
        elif name == "free":
            check(a[0] in self.allocations, f"free of {a[0]:#x} not allocated")
            self.uc.mem_write(a[0], b"\xdd" * self.allocations[a[0]])
            self.freed.append((a[0], self.allocations.pop(a[0])))
            self.jobs.pop(a[0], None)
        elif name == "heap_free":
            result = self.heap_free()
        elif name == "heap_largest":
            result = max(0, self.heap_free() - self.largest_gap)
        elif name == "now_ms":
            result = self.now
        elif name == "display_mutex":
            result = MUTEX
        elif name == "os_lock":
            check(a[0] == MUTEX and self.lock_depth == 0, "display mutex nested or wrong")
            self.lock_depth = 1
        elif name == "os_unlock":
            check(a[0] == MUTEX and self.lock_depth == 1, "display mutex not held")
            self.lock_depth = 0
        elif name == "panel_flush":
            check(self.lock_depth == 1 and a[1] == 0 and a[3] == W, "flush outside the mutex or bad x/w")
            check(0 < a[4] and a[2] + a[4] <= H, f"flush rows {a[2]}+{a[4]}")
            rows = bytes(self.uc.mem_read(a[0] + a[2] * STRIDE, a[4] * STRIDE))
            self.flushes.append((a[2], a[4], a[0], rows))
        elif name == "set_brightness":
            if a[0] <= 32:
                self.uc.mem_write(PANEL_BRIGHTNESS, struct.pack("<H", a[0]))
            else:
                result = 1
        elif name == "lv_screen_active":
            result = SCREEN
        elif name == "lv_obj_invalidate":
            check(a[0] == SCREEN, "invalidate of a non-screen object")
        elif name == "lv_timer_create":
            check(a[1] == 10 and self.timer_fn is None, "pump timer period or duplicate")
            self.timer_fn = a[0]
            result = TIMER
        elif name == "lv_timer_delete":
            check(a[0] == TIMER, "deleting an unknown timer")
            self.timer_fn = None
        elif name == "critical_enter":
            self.critical += 1
        elif name == "critical_exit":
            check(self.critical > 0, "critical section exit without enter (stock asserts)")
            self.critical -= 1
        self.set(10, result)

    # --- running code -----------------------------------------------------------
    def call(self, function, *args, regs=None, until=RETURN, context="router", label=None):
        for i, value in enumerate(args):
            self.set(10 + i, value)
        for x, value in (regs or {}).items():
            self.set(x, value)
        top = UI_TOP if context == "ui" else STACK_TOP
        self.context, self.min_sp = context, top
        self.set(1, RETURN)
        self.set(2, top)
        self.stopped_at = None
        self.uc.emu_start(function, until, count=50_000_000)
        pc = self.pc()
        if pc in (RETURN, ROUTER_UNROUTED, ROUTER_EPILOGUE, KICK_REJOIN, KICK_TAIL, UI_DISPATCH_REJOIN,
                  ANCS_WHITELIST_REJOIN, ANCS_INTAKE_RETURN):
            self.stopped_at = pc
        check(self.stopped_at is not None, f"call to {function:#x} did not return (pc {pc:#x})")
        check(self.critical == 0, "returned inside a critical section")
        label = label or next((n for n, a in self.symbols.items() if a == function), hex(function))
        used = top - self.min_sp
        self.depth[f"{context}:{label}"] = max(self.depth.get(f"{context}:{label}", 0), used)
        return self.reg(10)

    def run_ui(self):
        while self.queue:
            fn, arg = self.queue.pop(0)
            self.call(fn, arg, context="ui")

    def command(self, key, payload=b"", run_ui=True):
        self.payload_len = len(payload)
        self.uc.mem_write(self.payload, payload or b"\0")
        before = len(self.replies)
        check(self.call(self.symbols["glassly_command"], 0x7E, key, self.payload, len(payload)) == 1, "not handled")
        self.payload_len = 0
        if run_ui:
            self.run_ui()
        replies = [rep for rep in self.replies[before:] if rep[1] == key]
        check(replies, f"no reply to key {key:#x}")
        return replies[0]

    def tick(self):
        self.now += self.tick_ms
        if self.timer_fn:
            self.call(self.timer_fn, TIMER, context="ui", label="pump")

    def hold(self, seconds):
        for _ in range(int(seconds * 1000 / self.tick_ms)):
            self.tick()

    def touch(self, message, param):
        """The stock UI dispatcher receiving a touch message: the input gate's view."""
        self.uc.mem_write(self.payload, param)
        self.payload_len = len(param)
        before = len(self.replies)
        self.call(self.symbols["glassly_input_gate"], message, self.payload, len(param), context="ui",
                  until=UI_DISPATCH_REJOIN)
        self.payload_len = 0
        return self.stopped_at, self.replies[before:]

    def status(self):
        return json.loads(self.command(0x04)[2][1:].decode())

    def crumb_bytes(self):
        return bytes(self.uc.mem_read(self.crumbs[0], self.crumbs[1] - self.crumbs[0]))


def pixel(rows, row0, x, y):
    byte = rows[(y - row0) * STRIDE + x // 2]
    return byte & 15 if x & 1 else byte >> 4


def test(name):
    def wrap(fn):
        def run(build):
            fn(build)
            RESULTS.append(name)
            print(f"passed: {name}")
        run.__name__ = fn.__name__
        return run
    return wrap


def subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(v, actual[k]) for k, v in expected.items())
    return expected == actual


def step_payload(step):
    if "payload_file" not in step:
        return bytes.fromhex(step.get("payload_hex", ""))
    name = Path(step["payload_file"]).name
    generated = scene_packets.demo() if name == "demo-geometry.bin" else \
        {**scene_packets.retained(), **scene_packets.cues()}[name]
    path = ROOT / step["payload_file"]
    if path.is_file():
        check(path.read_bytes() == generated, f"{path} differs from scripts/scene_packets.py")
    return generated


def run_steps(m, steps, upto=None, log=None):
    """Replays hardware steps in order; returns {step: reply}."""
    out = {}
    for step in steps:
        if upto is not None and step["step"] > upto:
            break
        check(step["cmd"] == "7e", "only 0x7E steps replay here")
        key = int(step["key"], 16)
        if step.get("await"):
            touch = step["emulate_input"]
            stopped, sent = m.touch(touch["id"], bytes.fromhex(touch["param_hex"]))
            matching = [rep for rep in sent if rep[1] == key]
            check(stopped == RETURN and matching, f"step {step['step']}: the touch reached the stock dispatcher")
            cmd, rkey, data = matching[0]
        else:
            cmd, rkey, data = m.command(key, step_payload(step))
        out[step["step"]] = data
        where = f"step {step['step']} ({step['title']})"
        if "expect_status" in step:
            check(data[0] == step["expect_status"], f"{where}: status {data[0]}")
        expected = step.get("expect_reply_hex")
        # Canvas checksums are the right arm's (the master answers on the glasses).
        if expected is not None and not (key == 0x25 and expected[-2:] != data.hex()[-2:]):
            check(data.hex() == expected, f"{where}: reply {data.hex()}")
        if "expect_reply_prefix_hex" in step:
            check(data.hex().startswith(step["expect_reply_prefix_hex"]), f"{where}: reply {data.hex()}")
        if "expect_json" in step:
            actual = json.loads(data[1:].decode())
            check(subset(step["expect_json"], actual), f"{where}: JSON {actual}")
        if log is not None:
            log.append({"step": step["step"], "reply": data.hex() if len(data) < 40 else data[1:].decode(),
                        "heap_free": m.heap_free()})
        m.hold(step.get("hold_seconds", 0))
    return out


def steps_file(revision):
    return json.loads((ROOT / "tests/hardware" / f"steps-{revision}.json").read_text())


@test("identity, echo and the 1200-byte checksum from the router handler")
def test_plain(build):
    m = Machine(build)
    cmd, key, data = m.command(0x01)
    identity = json.loads(data[1:].decode())
    check(data[0] == 0 and identity["version"] == f"GLASSLYCFW/{m.revision}" and identity["eye"] == "left", identity)
    check(m.command(0x02, b"abc")[2] == b"\0abc", "echo")
    chunk = bytes((i * 7 + 3) & 255 for i in range(1200))
    reply = m.command(0x03, chunk)[2]
    check(reply == b"\0" + struct.pack("<II", 1200, zlib.crc32(chunk)), f"checksum {reply.hex()}")
    status = json.loads(m.command(0x04)[2][1:].decode())
    check(status["owned"] == 0 and status["commands"] == 4, status)


@test("router gate: 0x7E leaves through the epilogue, others replay the hooked bytes")
def test_router_gate(build):
    m = Machine(build)
    gate = m.symbols["glassly_router_gate"]
    m.uc.mem_write(PAYLOAD, b"\0")
    saved = {x: 0x1000 + x for x in (8, 19, 22, 23, 24, 25, 26, 27)}
    m.call(gate, regs={9: 0x7E, 18: 0x01, 21: PAYLOAD, 20: 0, **saved}, until=ROUTER_EPILOGUE)
    check(m.stopped_at == ROUTER_EPILOGUE and m.replies and m.replies[-1][1] == 1, "handled path")
    m.call(gate, regs={9: 0x05, 18: 0x33, 21: PAYLOAD, 20: 7, **saved}, until=ROUTER_UNROUTED)
    check(m.stopped_at == ROUTER_UNROUTED, "unrouted path")
    check(m.reg(12) == 0x04378000 and m.reg(14) == 0x33 and m.reg(15) == 7, "replayed lui a2 / mv a4,s2 / mv a5,s4")
    check(m.reg(9) == 0x05 and m.reg(18) == 0x33 and m.reg(20) == 7 and m.reg(21) == PAYLOAD, "cmd/key/len/payload kept")
    check(all(m.reg(x) == v for x, v in saved.items()), "callee-saved registers changed")


@test("flush gate: stock path tail-calls the panel op, owned path skips it")
def test_flush_gate(build):
    m = Machine(build)
    gate = m.symbols["glassly_flush_gate"]
    ops = SCRATCH + 0x100
    m.uc.mem_write(ops + 16, struct.pack("<I", FAKE_FLUSH))
    saved = {x: 0x2000 + x for x in (8, 9, 18, 20, 21, 22, 23, 24, 25, 26, 27)}
    regs = {10: 0x0202F064, 11: 0, 12: 12, 13: 540, 15: ops, 19: 0x77, **saved}
    m.call(gate, regs=regs)
    check(m.fake_flush_calls == [[0x0202F064, 0, 12, 540, saved[18]]], f"stock flush args {m.fake_flush_calls}")
    check(m.reg(10) == 0x55 and m.reg(19) == 0 and m.u32(m.ram_block[0] + 12) == 0, "stock result and s3 replay")
    m.uc.mem_write(m.ram_block[0] + 8, b"\x01")
    m.uc.mem_write(LIT, b"\x00")
    m.uc.mem_write(BLANK, struct.pack("<I", 2))
    m.call(gate, regs=regs)
    check(len(m.fake_flush_calls) == 1 and m.reg(10) == 0 and m.reg(19) == 0 and m.reg(14) == saved[18],
          "owned path wrote the panel or broke the replay")
    check(m.u32(m.ram_block[0] + 12) == 1 and m.u8(LIT) == 1 and m.u32(BLANK) == 0, "owned path bookkeeping")
    check(all(m.reg(x) == v for x, v in saved.items()) and m.reg(2) == STACK_TOP, "callee-saved registers changed")


@test("kick gate: stock path replays the hooked bytes, owned path skips the commit")
def test_kick_gate(build):
    m = Machine(build)
    gate = m.symbols["glassly_kick_gate"]
    saved = {x: 0x3000 + x for x in (8, 9, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27)}
    args = {10: 0xA0, 11: 0xA1, 12: 0xA2, 3: GP, **saved}
    m.uc.mem_write(KICK_FLAG, b"\x01")
    m.call(gate, regs=args, until=KICK_REJOIN)
    check(m.stopped_at == KICK_REJOIN and m.reg(2) == STACK_TOP - 32 and m.reg(15) == 1, "flag set: frame and rejoin")
    m.uc.mem_write(KICK_FLAG, b"\x00")
    m.call(gate, regs=args, until=KICK_TAIL)
    check(m.stopped_at == KICK_TAIL and m.reg(2) == STACK_TOP and m.reg(15) == 0, "flag clear: tail call, no frame")
    check(all(m.reg(x) == v for x, v in saved.items()) and m.reg(10) == 0xA0 and m.reg(3) == GP,
          "stock path changed an argument or a callee-saved register")
    m.uc.mem_write(m.ram_block[0] + 8, b"\x01")
    m.call(gate, regs=args)
    check(m.stopped_at == RETURN and m.reg(10) == 0 and m.reg(2) == STACK_TOP and m.u32(m.ram_block[0] + 12) == 1,
          "owned path: return 0 to the caller, count the skip")
    check(all(m.reg(x) == v for x, v in saved.items()), "owned path changed a callee-saved register")


@test("input gate: touches while owned go to the phone, auto brightness waits after a 0x23 level")
def test_input_gate(build):
    m = Machine(build)
    saved = {x: 0x4000 + x for x in (8, 9, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27)}
    tap = bytes.fromhex("0101030005000000")
    m.uc.mem_write(PAYLOAD, tap)

    def gate(message, owned):
        m.uc.mem_write(m.ram_block[0] + 8, bytes([owned]))
        before = len(m.replies)
        m.call(m.symbols["glassly_input_gate"], regs={10: message, 11: PAYLOAD, 12: len(tap), **saved},
               context="ui", until=UI_DISPATCH_REJOIN)
        return m.stopped_at, m.replies[before:]

    stopped, sent = gate(0x88, 0)
    check(stopped == UI_DISPATCH_REJOIN and not sent, "not owned: the dispatcher gets the tap")
    check(m.reg(2) == UI_TOP - 128 and (m.reg(10), m.reg(11), m.reg(12)) == (0x88, PAYLOAD, 8),
          "replayed frame or changed arguments")
    for slot, x in ((120, 8), (116, 9), (108, 19)):
        check(m.u32(UI_TOP - 128 + slot) == saved[x], f"replayed save of x{x} at {slot}(sp)")
    for message in (0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x98, 0x99):
        stopped, sent = gate(message, 1)
        check(stopped == RETURN and sent == [(0x7E, 0x26, bytes([0, message, 8]) + tap)],
              f"owned: message {message:#x} forwarded {sent}")
        check(m.reg(2) == UI_TOP and all(m.reg(x) == v for x, v in saved.items()), "callee-saved registers")
    for message in (0x87, 0x8D, 0x97, 0x9A, 0xA7, 0xBB, 0x24):
        stopped, sent = gate(message, 1)
        check(stopped == UI_DISPATCH_REJOIN and not sent, f"owned: message {message:#x} is not a touch")
    check(m.u32(m.ram_block[0] + 0x84) == 7, "inputs counter")
    # Auto-brightness steps (0xa8) pass until the phone sets a level, then wait.
    skips = m.u32(m.ram_block[0] + 12)
    stopped, sent = gate(0xA8, 1)
    check(stopped == UI_DISPATCH_REJOIN and not sent, "auto brightness before a 0x23 level")
    m.uc.mem_write(m.ram_block[0] + 0x89, b"\x01")
    stopped, sent = gate(0xA8, 1)
    check(stopped == RETURN and not sent and m.u32(m.ram_block[0] + 12) == skips + 1, "auto brightness held off")
    stopped, sent = gate(0xA8, 0)
    check(stopped == UI_DISPATCH_REJOIN, "auto brightness while not owned")


def demo_session(build, left):
    m = Machine(build, left)
    acquire = m.command(0x21)[2]
    check(acquire == bytes([0, 0, 1, 1 if left else 2]), f"acquire reply {acquire.hex()}")
    check(m.u8(m.ram_block[0] + 8) == 1 and m.timer_fn and m.flushes[-1][:2] == (0, 280), "acquire state")
    check(set(m.flushes[-1][3]) == {0}, "acquire presents black")
    check(m.u8(LIT) == 1 and m.u32(BLANK) == 0, "acquire keeps the display lit")
    demos = scene_packets.retained()
    reply = m.command(0x20, scene_packets.demo())[2]
    check(reply == b"\0" and m.flushes[-1][:2] == (0, 280) and pixel(m.flushes[-1][3], 0, 3, 140) == 15, "mode-36 demo")
    reply = m.command(0x20, demos["scene-retained.bin"])[2]
    check(reply[0] == 0 and reply[1] == 38 and reply[4] == 0, f"geometry reply {reply.hex()}")
    row0, nrows, fb, rows = m.flushes[-1]
    check((row0, nrows) == (0, 280) and pixel(rows, 0, 270, 100) == 11 and pixel(rows, 0, 9, 140) == 15,
          "geometry frame pixels")
    presents = len(m.flushes)
    for _ in range(400):
        m.tick()
        if m.replies[-1][1] == 0x24:
            break
    check(m.replies[-1] == (0x7E, 0x24, bytes([0, 3, 0])), f"settled notice {m.replies[-1]}")
    check(len(m.flushes) > presents and all(f[0] >= 30 and f[0] + f[1] <= 100 for f in m.flushes[presents:]),
          "glide presents only the box rows")
    frame = bytearray(m.uc.mem_read(fb, STRIDE * H))
    check(pixel(frame, 0, 460, 60) == 15 and pixel(frame, 0, 60, 60) == 0, "glide end position")
    m.command(0x20, demos["scene-eyes.bin"])
    frame = bytes(m.uc.mem_read(fb, STRIDE * H))
    check(pixel(frame, 0, 80, 210) == (15 if left else 0) and pixel(frame, 0, W - 85, 210) == (0 if left else 15),
          "eye objects")
    presents = len(m.flushes)
    m.command(0x20, demos["scene-show-right.bin"])
    check((len(m.flushes) == presents) == left, "right-eye SHOW reaches only the right arm")
    presents = len(m.flushes)
    m.command(0x20, demos["scene-show-left.bin"])
    check((len(m.flushes) > presents) == left, "left-eye SHOW reaches only the left arm")
    check(m.command(0x23, b"\x08")[2] == b"\0\0", "brightness")
    check(fb == FB, f"canvas {fb:#x} is not the stock buffer the back index leaves free")
    check(m.u8(FB_FRONT) == 1 and m.u8(FB_BACK) == 1, "front index pinned to the back buffer")
    canvas = m.command(0x25)[2]
    check(canvas == b"\0" + struct.pack("<I", zlib.crc32(bytes(m.uc.mem_read(FB, FB_BYTES)))) +
          bytes([1 if left else 2]), f"canvas checksum {canvas.hex()}")
    check(m.command(0x22)[2] == b"\0", "release")
    check(m.u8(m.ram_block[0] + 8) == 0 and m.timer_fn is None and not m.allocations, "release frees everything")
    check(m.u8(FB_FRONT) == 0 and m.u8(FB_BACK) == 1 and
          m.uc.mem_read(FB, FB_BYTES) == m.uc.mem_read(FB + FB_BYTES, FB_BYTES), "release gives the buffer back")
    check(m.calls.count("repaint_all") == 1 and m.calls.count("lv_obj_invalidate") == 1, "stock repaint")
    return m


@test("notification gates: the whitelist and the intake follow the relay lease")
def test_ancs_gates(build):
    m = Machine(build)
    saved = {x: 0x4000 + x for x in (8, 9, 18, 19, 20, 21)}
    appid, strings, intake = PAYLOAD, PAYLOAD + 0x100, PAYLOAD + 0x400
    m.uc.mem_write(appid, b"com.example.chat\0")
    fields = [b"com.example.chat", b"Title", b"", b"x" * 200, b"20261114T153000"]
    pointers, at = [], strings
    for text in fields:
        m.uc.mem_write(at, text + b"\0")
        pointers.append(at)
        at += len(text) + 1
    m.uc.mem_write(intake, struct.pack("<10I", 0x11223344, 7, 0, pointers[0], pointers[1], pointers[2], pointers[3],
                                       0, 0, pointers[4]))

    def whitelist(until):
        m.call(m.symbols["glassly_ancs_whitelist_gate"], regs={10: appid, **saved}, until=until)
        return m.stopped_at

    check(whitelist(ANCS_WHITELIST_REJOIN) == ANCS_WHITELIST_REJOIN and m.reg(10) == appid, "no lease: stock check runs")
    check(m.reg(2) == STACK_TOP - 16 and m.u32(STACK_TOP - 16 + 8) == saved[8] and m.u32(STACK_TOP - 16 + 4) == saved[9]
          and m.u32(STACK_TOP - 16 + 12) == RETURN, "replayed whitelist prologue")

    def intake_gate():
        before = len(m.replies), m.calls.count("ancs_intake")
        m.call(m.symbols["glassly_ancs_intake_gate"], regs={10: intake, **saved})
        check(m.stopped_at == RETURN and m.reg(12) == 0x1CA and m.reg(2) == STACK_TOP, "intake gate returns to its caller")
        check(all(m.reg(x) == v for x, v in saved.items()), "callee-saved registers through the intake gate")
        return m.replies[before[0]:], m.calls.count("ancs_intake") - before[1]

    sent, stock = intake_gate()
    check(not sent and stock == 1, "no lease: the stock intake runs")
    status = m.command(0x27, b"\x01")[2]
    check(status[:7] == bytes([0, 0x41, 0x4E, 1, 4, 1, 1]) and status[7:9] == b"\x01\x00", f"lease status {status.hex()}")
    check(whitelist(RETURN) == RETURN and m.reg(10) == 1 and m.reg(2) == STACK_TOP, "leased: every app allowed")
    sent, stock = intake_gate()
    check(stock == 0 and len(sent) == 1 + 7 + 2 and all(r[:2] == (0x7E, 0x28) for r in sent), f"leased: {len(sent)} records")
    check(sent[0][2] == bytes([0, 0x41, 0x4E, 1, 1, 0, 0, 7, 0]) + struct.pack("<I", 0x11223344), "SOURCE record")
    check(sent[1][2][9:14] == bytes([0, 16, 0, 0, 0]) and sent[1][2][14:] == b"com.example.chat", "app id attribute")
    check(sent[4][2][9:14] == bytes([3, 200, 0, 0, 0]) and len(sent[4][2]) == 14 + 128, "first message chunk")
    check(sent[5][2][11:14] == bytes([0, 128, 0]) and len(sent[5][2]) == 14 + 72, "second message chunk")
    check(sent[6][2][9:14] == bytes([4, 0, 0, 0, 0]) and len(sent[6][2]) == 14, "empty message-size attribute")
    check(sent[7][2][9:14] == bytes([5, 15, 0, 0, 0]) and sent[7][2][14:] == b"20261114T153000", "date attribute")
    check(max(len(r[2]) for r in sent) <= 590, "records fit build_response")
    status = m.command(0x27, b"\x03")[2]
    check(status[5] == 1 and status[7:11] == bytes([1, 0, 10, 0]), f"status counters {status.hex()}")
    m.now += 90_001
    sent, stock = intake_gate()
    check(not sent and stock == 1, "expired lease: the stock intake runs again")
    check(m.command(0x27, b"\x04")[2] == b"\x05" and m.command(0x27, b"\x01\x01")[2] == b"\x01", "refused ops")


@test("left arm: acquire, demo scenes, pump, per-eye SHOW, brightness, release")
def test_left(build):
    m = demo_session(build, True)
    EVIDENCE["demo_stack_depth"] = m.depth
    EVIDENCE["demo_wide_packet_reads"] = m.wide_packet_reads


@test("right arm: acquire, demo scenes, pump, per-eye SHOW, brightness, release")
def test_right(build):
    demo_session(build, False)


@test("hardware steps through the first mode-36 frame with the glasses' heap (the GLASSLYCFW/5 reset)")
def test_steps_to_geometry(build):
    m = Machine(build, heap_free=HW_HEAP_FREE, largest_gap=HW_LARGEST_GAP)
    steps = [s for s in steps_file(m.revision)["steps"]]
    # Steps up to and including the first mode-36 frame (step 7 of steps-5,
    # 8 of steps-6): GLASSLYCFW/5 reset at its first AMO here.
    upto = next(s["step"] for s in steps if Path(s.get("payload_file", "")).name == "demo-geometry.bin")
    log = []
    replies = run_steps(m, steps, upto=upto, log=log)
    check(replies[upto] == b"\0", f"mode-36 reply {replies[upto].hex()}")
    check(m.flushes[-1][:2] == (0, 280) and pixel(m.flushes[-1][3], 0, 3, 140) == 15, "mode-36 frame on the panel")
    status = m.status()
    check(status["scenes"] == 1 and status["rejected"] == 0 and status["owned"] == 1, status)
    EVIDENCE["steps_to_geometry"] = {"replies": log, "stack_depth": m.depth, "wide_packet_reads": m.wide_packet_reads,
                                     "heap_free_after": m.heap_free()}


@test("whole hardware step list in order, every reply, with 400 KB and with the glasses' heap")
def test_all_steps(build):
    for left in (True, False):
        m = Machine(build, left)
        log = []
        run_steps(m, steps_file(m.revision)["steps"], log=log)
        check(not m.allocations, "the release step leaves no allocation")
        if left:
            EVIDENCE["all_steps_400k"] = {"replies": log, "stack_depth": m.depth}
    # The glasses' heap (194,520 B free before the lease): with the canvas in a
    # stock framebuffer the retained scene fits, so every expectation holds.
    for left in (True, False):
        m = Machine(build, left, heap_free=HW_HEAP_FREE, largest_gap=HW_LARGEST_GAP)
        log = []
        run_steps(m, steps_file(m.revision)["steps"], log=log)
        check(not m.allocations, "the release step leaves no allocation")
        if not left:
            EVIDENCE["all_steps_glasses_heap"] = {"replies": log, "stack_depth": m.depth}


def canvas_checksums(build, tick_ms):
    """The right arm's key-25 replies over the step list, by step."""
    m = Machine(build, False, heap_free=HW_HEAP_FREE, largest_gap=HW_LARGEST_GAP)
    m.tick_ms = tick_ms
    steps = [dict(s, expect_reply_hex=None) if s["key"] == "25" else s for s in steps_file(m.revision)["steps"]]
    replies = run_steps(m, steps)
    return {s["step"]: replies[s["step"]].hex() for s in steps if s["key"] == "25"}


@test("canvas checksums of the step list do not depend on the pump's tick")
def test_canvas_timing(build):
    revision = json.loads((build / "build.json").read_text())["revision"]
    expected = {s["step"]: s.get("expect_reply_hex") for s in steps_file(revision)["steps"] if s["key"] == "25"}
    for tick in (10, 7, 23):
        got = canvas_checksums(build, tick)
        check(got == expected, f"tick {tick} ms: canvas replies {got} differ from the step list {expected}")
    EVIDENCE["canvas_checksums"] = expected


@test("odd payload address: no multi-byte read of packet bytes")
def test_odd_payload(build):
    m = Machine(build, payload=PAYLOAD + 1)
    m.command(0x21)
    for packet in [scene_packets.demo(), *scene_packets.retained().values()]:
        check(m.command(0x20, packet)[2][0] == 0, "scene message from an odd address")
    m.command(0x03, bytes(range(255)) * 3)
    m.command(0x02, b"odd")
    reads = {k: v for k, v in m.wide_packet_reads.items() if "mm_scene_memcpy" not in k}
    check(not reads, f"multi-byte packet reads {reads}")


def crumbs_json(status):
    return {"boot": status.get("boot"), "last_crash": status.get("last_crash")}


@test("breadcrumbs: power-on record, reset mid-render, previous boot reported")
def test_breadcrumbs(build):
    m0 = Machine(build)
    if not m0.crumbs[1]:
        raise AssertionError("build has no breadcrumb carve")
    noise = random.Random(6).randbytes(m0.crumbs[1] - m0.crumbs[0])
    # Power-on: random RAM there is not trusted.
    m = Machine(build, crumbs=noise)
    status = m.status()
    check(status["boot"] == 1 and status["last_crash"] is None, crumbs_json(status))
    # A clean session ends at rest: the next boot reports no crash.
    m.command(0x21)
    m.command(0x20, scene_packets.demo())
    m.hold(0.1)
    m = Machine(build, crumbs=m.crumb_bytes())
    status = m.status()
    check(status["boot"] == 2 and status["last_crash"] is None, crumbs_json(status))
    # Reset while the mode-36 frame renders (the GLASSLYCFW/5 symptom).
    m.command(0x21)
    seq = m.status()["commands"] + 1

    def reset_in_render(machine, name, args):
        if name == "panel_flush" and machine.context == "ui":
            raise DeviceFault("simulated reset during the present")
    m.fault_hook = reset_in_render
    try:
        m.command(0x20, scene_packets.demo())
        raise AssertionError("the simulated reset did not happen")
    except DeviceFault:
        pass
    m = Machine(build, crumbs=m.crumb_bytes())
    status = m.status()
    crash = status["last_crash"]
    check(status["boot"] == 3 and crash == {"lane": "ui", "stage": "present", "seq": seq, "key": 0x20, "mode": 36,
                                             "len": len(scene_packets.demo()), "open": 2}, crumbs_json(status))
    # Reset inside the router (before the reply) and in a pump tick.
    m.fault_hook = lambda machine, name, args: (_ for _ in ()).throw(DeviceFault("reset")) \
        if name == "send_response" else None
    try:
        m.command(0x02, b"x")
    except DeviceFault:
        pass
    m = Machine(build, crumbs=m.crumb_bytes())
    status = m.status()
    check(status["last_crash"]["lane"] == "router" and status["last_crash"]["stage"] == "reply" and
          status["last_crash"]["key"] == 2 and status["boot"] == 4, crumbs_json(status))
    m.command(0x21)
    m.command(0x20, scene_packets.retained()["scene-retained.bin"])
    m.fault_hook = lambda machine, name, args: (_ for _ in ()).throw(DeviceFault("reset")) \
        if name == "panel_flush" and machine.calls.count("panel_flush") > 3 else None
    try:
        m.hold(1)
        raise AssertionError("no pump present")
    except DeviceFault:
        pass
    m = Machine(build, crumbs=m.crumb_bytes())
    status = m.status()
    check(status["last_crash"]["lane"] == "pump" and status["last_crash"]["stage"] == "present", crumbs_json(status))
    # The JSON stays inside the reply buffer with every number at 10 digits
    # and the router lane open at its longest stage name (RV32 layout, ram.h).
    m = Machine(build, crumbs=m.crumb_bytes())
    m.status()
    block = m.ram_block[0]
    for offset in [0x0C, *range(0x20, 0x54, 4), 0x80, 0x84]:
        m.uc.mem_write(block + offset, b"\xff\xff\xff\xff")
    m.uc.mem_write(block + 0x1C, struct.pack("<I", 0xFFFFFFFE))
    m.uc.mem_write(block + 0x54, b"\x02")
    m.uc.mem_write(block + 0x58, b"\xff" * 8 + bytes([3, 255, 255, 0]) + bytes(8) + bytes([7, 0, 0, 0]) +
                   bytes(8) + bytes([7, 0, 0, 0]))
    m.uc.mem_write(PANEL_BRIGHTNESS, b"\xff\xff")
    m.heap_base_free = 0xFFFFFFFF
    m.largest_gap = 0
    data = m.command(0x04)[2]
    widest = json.loads(data[1:].decode())
    check(len(data) < 560 and widest["last_crash"]["lane"] == "router" and widest["boot"] == 0xFFFFFFFF and
          widest["last_crash"]["len"] == 0xFFFFFFFF, f"{len(data)} {widest}")
    EVIDENCE["breadcrumbs"] = {"crash_status": crash, "widest_status_bytes": len(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", type=Path, required=True, help="build_runtime.py output (glasslycfw-N)")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected", action="store_true",
                        help="write the right arm's canvas checksums into the step list and exit")
    args = parser.parse_args()
    if args.expected:
        revision = json.loads((args.build / "build.json").read_text())["revision"]
        path = ROOT / "tests/hardware" / f"steps-{revision}.json"
        doc = json.loads(path.read_text())
        got = canvas_checksums(args.build, 10)
        for step in doc["steps"]:
            if step["step"] in got:
                step["expect_reply_hex"] = got[step["step"]]
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(got, indent=2))
        return
    tests = [test_plain, test_router_gate, test_flush_gate, test_kick_gate, test_input_gate, test_ancs_gates, test_left, test_right,
             test_steps_to_geometry, test_all_steps, test_canvas_timing, test_odd_payload, test_breadcrumbs]
    for fn in tests:
        fn(args.build)
    report = {"format": "nimo-rv32-runtime-emulator-v2", "passed": RESULTS, "unicorn": u.__version__,
              "blob": str(args.build / "runtime.bin"), "hardware_tested": False,
              "strict": ["rv32imc", "aligned", "owned-regions", "task-stacks"], "evidence": EVIDENCE}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(RESULTS)} RV32 emulator checks")


if __name__ == "__main__":
    main()
