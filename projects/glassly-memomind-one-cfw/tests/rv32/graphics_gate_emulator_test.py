#!/usr/bin/env python3
"""Execute actual linked graphics gates in RV32; C/native entry bodies are mocked.

Includes the real eight-byte patched worker callsite and observes its return
continuation. This tests gate ABI/routing only, not graphics C or hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"))
from build_memomind_graphics import pc_relative_call

ENTRY, DISPLAY, CALLSITE, CONTINUE = 0x0439bea0, 0x0439bee0, 0x0425c00a, 0x0425c012
STOCK_SERVICE, STOCK_DISPLAY = 0x042e4680, 0x0425b38a
STACK, FRAME, ENVELOPE = 0x03001000, 0x03100200, 0x03200000
BUILD = ROOT/"runtime/build/graphics-gates-004"
CASES, EXECUTED = [], set()


class GateMachine:
    def __init__(self, *, command=None, request=0, class_byte=0, event=0, null_envelope=False):
        build = json.loads((BUILD/"build.json").read_text())
        blob = (BUILD/"graphics.bin").read_bytes()
        assert hashlib.sha256(blob).hexdigest() == build["blob_sha256"]
        elf = (BUILD/"graphics.elf").read_bytes()
        assert elf[:7] == b"\x7fELF\x01\x01\x01" and struct.unpack_from("<H", elf, 18)[0] == 243
        assert hashlib.sha256(elf).hexdigest() == build["elf_sha256"]
        assert blob[64:68] == bytes.fromhex("032504f9")
        self.symbols, self.blob = build["symbols"], blob
        self.display = command is None
        self.command, self.request, self.class_byte, self.event = command, request, class_byte, event
        self.envelope = 0 if null_envelope else ENVELOPE
        self.uc = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
        base, end = ENTRY & ~4095, (ENTRY+len(blob)+4095) & ~4095
        self.uc.mem_map(base, end-base, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_write(ENTRY, blob)
        for page in (STOCK_SERVICE & ~4095, STOCK_DISPLAY & ~4095, CALLSITE & ~4095):
            self.uc.mem_map(page, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for addr in (STOCK_SERVICE, STOCK_DISPLAY):
            self.uc.mem_write(addr, bytes.fromhex("67800000"))
        self.uc.mem_write(CALLSITE, pc_relative_call(CALLSITE, DISPLAY)+bytes.fromhex("032504f9"))
        self.uc.mem_map(STACK-4096, 4096, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(FRAME & ~4095, 4096, u.UC_PROT_READ)
        self.uc.mem_map(ENVELOPE, 4096, u.UC_PROT_READ)
        self.uc.mem_write(STACK-4096, b"\x5a"*4096)
        self.uc.mem_write(FRAME-0x70, struct.pack("<I", self.envelope))
        self.uc.mem_write(ENVELOPE, bytes([0x99, class_byte])+bytes(2)+struct.pack("<H", event)+bytes(10))
        for x in range(1, 32):
            self.set(x, 0xa0000000+x*0x101)
        for x, value in {1: 0x05000000, 2: STACK, 3: 0x02011688, 4: 0x0200abcd,
                         8: FRAME, 10: 0xdeadbeef if self.display else command,
                         11: request, 12: FRAME+8, 13: FRAME+16}.items():
            self.set(x, value)
        self.initial = {x: self.reg(x) for x in range(1, 32)}
        self.expected_target = (self.symbols["glassly_graphics_display"]
                                if self.display and self.envelope and class_byte & 63 == 63 and event == 0x474c
                                else STOCK_DISPLAY if self.display
                                else self.symbols["glassly_graphics_probe"] if command == 0x7e
                                else self.symbols["glassly_graphics_command"] if command == 0x7d
                                else STOCK_SERVICE)
        self.boundary_seen, self.continuation_seen = False, False
        self.pcs, self.reads = [], []
        self.uc.hook_add(u.UC_HOOK_CODE, self.instruction)
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self.write)
        self.uc.hook_add(u.UC_HOOK_MEM_READ, self.read)

    def reg(self, x):
        return self.uc.reg_read(getattr(r, f"UC_RISCV_REG_X{x}"))

    def set(self, x, value):
        self.uc.reg_write(getattr(r, f"UC_RISCV_REG_X{x}"), value)

    def write(self, uc, access, address, size, value, userdata):
        raise AssertionError(f"Gate performed a memory write at {address:#x}+{size}")

    def read(self, uc, access, address, size, value, userdata):
        assert self.display, "Service gate dereferenced request arguments"
        assert (address, size) in ((FRAME-0x70, 4), (ENVELOPE+1, 1), (ENVELOPE+4, 2))
        self.reads.append((address, size))

    def assert_boundary_registers(self):
        for x in range(1, 32):
            if x in (5, 6, 7):  # t0..t2 are explicitly allowed scratch.
                continue
            expected = (CONTINUE if x == 1 else self.envelope if x == 10 else self.initial[x]) if self.display else self.initial[x]
            assert self.reg(x) == expected, f"Changed x{x}: {self.reg(x):#x} != {expected:#x}"

    def instruction(self, uc, address, size, userdata):
        self.pcs.append(address)
        assert self.reg(2) == STACK, "Gate allocated stack before C/native entry"
        targets = {STOCK_SERVICE, STOCK_DISPLAY, self.symbols["glassly_graphics_probe"],
                   self.symbols["glassly_graphics_command"], self.symbols["glassly_graphics_display"]}
        if address in targets:
            assert not self.boundary_seen and address == self.expected_target, "Wrong gate route"
            self.assert_boundary_registers()
            self.boundary_seen = True
            if self.display:
                # Mock only the handler's return to prove callsite continuation.
                # No C/native implementation instructions run in this harness.
                uc.reg_write(r.UC_RISCV_REG_PC, self.reg(1))
            else:
                uc.emu_stop()
        elif address == CONTINUE:
            assert self.display and self.boundary_seen
            self.assert_boundary_registers()
            self.continuation_seen = True
            uc.emu_stop()
        else:
            assert ENTRY <= address < ENTRY+len(self.blob) or (self.display and address in (CALLSITE, CALLSITE+4))

    def run(self):
        self.uc.emu_start(CALLSITE if self.display else ENTRY, 0, count=100)
        assert self.boundary_seen and (not self.display or self.continuation_seen)
        assert bytes(self.uc.mem_read(STACK-4096, 4096)) == b"\x5a"*4096
        if self.display:
            if not self.envelope:
                assert self.reads == [(FRAME-0x70, 4)], "NULL envelope was dereferenced"
            else:
                assert self.reads[:2] == [(FRAME-0x70, 4), (ENVELOPE+1, 1)]
                assert len(self.reads) == (3 if self.class_byte & 63 == 63 else 2)
            assert self.pcs[:3] == [CALLSITE, CALLSITE+4, DISPLAY]
        else:
            assert not self.reads
        case = {"kind": "display" if self.display else "service", "command": self.command,
                "request_nonempty": bool(self.request), "class_byte": self.class_byte,
                "null_envelope": not bool(self.envelope),
                "event": self.event, "destination": f"0x{self.expected_target:08x}",
                "no_stack_or_memory_writes": True, "register_contract_passed": True,
                "displaced_load_and_continuation": self.display}
        CASES.append(case)
        EXECUTED.update(self.pcs)
        return case


class GateTests(unittest.TestCase):
    def test_null_envelope_preserves_stock_null_handling(self):
        GateMachine(null_envelope=True, class_byte=0x3f, event=0x474c).run()

    def test_all_service_command_bytes_preserve_arguments_and_stack(self):
        for request in (0, ENVELOPE):
            for command in range(256):
                with self.subTest(command=command, request=request):
                    GateMachine(command=command, request=request).run()

    def test_all_class_bytes_and_exact_event_gate(self):
        for class_byte in range(256):
            for event in (0, 0x474c, 0xffff):
                with self.subTest(class_byte=class_byte, event=event):
                    GateMachine(class_byte=class_byte, event=event).run()

    def test_matching_classes_reject_every_single_bit_event_mismatch(self):
        for class_byte in (0x3f, 0x7f, 0xbf, 0xff):
            for bit in range(16):
                with self.subTest(class_byte=class_byte, bit=bit):
                    GateMachine(class_byte=class_byte, event=0x474c ^ (1 << bit)).run()


def main():
    global BUILD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=BUILD)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    BUILD = args.build.resolve()
    assert u.__version__ == "2.1.4"
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GateTests))
    build = json.loads((BUILD/"build.json").read_text())
    report = {"format": "memomind-graphics-gate-emulation-v1", "kind": "RV32 machine-code gates with mocked C/native boundaries",
              "build": str(BUILD), "blob_sha256": build["blob_sha256"], "gate_fixture_only": build["gate_fixture_only"],
              "architecture": "UC_ARCH_RISCV / UC_MODE_RISCV32", "unicorn_version": u.__version__,
              "all_passed": result.wasSuccessful(), "test_groups": result.testsRun,
              "successful_cases": len(CASES), "executed_addresses": [f"0x{x:08x}" for x in sorted(EXECUTED)],
              "cases": CASES, "limitations": ["C runtime/native function bodies are not executed by these gate tests.",
                                                   "Handler return is mocked; real runtime ownership/rendering need separate tests.",
                                                   "Synthetic RAM, no device execution or firmware flashing."]}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
