#!/usr/bin/env python3
"""Actual RV32 input gates; C observer/handlers and stock dispatcher are mocked.

The observer mock deliberately clobbers all ABI caller-saved integer and float
registers plus fcsr. The actual assembly must restore them before stock dispatch.
No observer C implementation, physical input or device firmware executes here.
"""
import argparse
import json
from pathlib import Path
import struct
import unittest

import graphics_gate_emulator_test as gates

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT/"runtime/build/input-001"
RESULTS = []
BUTTONS = (*range(0x1f7b, 0x1f80), *range(0x1fb0, 0x1fba))
IMU = tuple(range(1, 9))
FP_CALLER = (*range(8), *range(10, 18), *range(28, 32))
INT_CALLER = (1, 5, 6, 7, *range(10, 18), *range(28, 32))
CSR_FIXTURE = 0x05002000


class InputGateMachine(gates.GateMachine):
    def __init__(self, *, length=0, **kwargs):
        super().__init__(**kwargs)
        build = json.loads((gates.BUILD/"build.json").read_text())
        assert build["input_observer"] and build["scene_session"]
        assert set(build["retained_input_entries"]) == {"glassly_input_command", "glassly_input_observe"}
        self.length, self.observed, self.writes = length, [], []
        self.min_sp = gates.STACK
        self.csr_fixture_active = False
        self.uc.mem_map(CSR_FIXTURE, 4096, gates.u.UC_PROT_READ | gates.u.UC_PROT_EXEC)
        # Enable the native ilp32f floating-point context (FS=Dirty). Use real
        # CSR instructions for initialization, observer clobber and assertion.
        self.uc.reg_write(gates.r.UC_RISCV_REG_MSTATUS, 0x6000)
        self.uc.mem_write(CSR_FIXTURE, struct.pack("<4I", 0x00329073, 0x003022f3, 0x00329073, 0x00008067))
        self.uc.mem_write(gates.ENVELOPE+6, struct.pack("<H", length))
        if self.command == 0x7c:
            self.expected_target = self.symbols["glassly_input_command"]
        self.should_observe = bool(self.display and self.envelope and not length and
            ((self.class_byte & 63 == 2 and self.event in BUTTONS) or
             (self.class_byte & 63 == 3 and self.event in IMU)))
        for i in range(32):
            self.uc.reg_write(getattr(gates.r, f"UC_RISCV_REG_F{i}"), 0xffffffff3f800000+i)
        self.initial_fp = {i: self.uc.reg_read(getattr(gates.r, f"UC_RISCV_REG_F{i}")) for i in range(32)}
        saved = self.reg(5); self.set(5, 0x23)
        self.csr_fixture_active = True
        self.uc.emu_start(CSR_FIXTURE, 0, count=1)
        self.csr_fixture_active = False; self.set(5, saved)

    def assert_boundary_registers(self):
        for index in range(1, 32):
            if index in (5, 6): continue
            expected = (gates.CONTINUE if index == 1 else self.envelope if index == 10
                        else self.initial[index]) if self.display else self.initial[index]
            assert self.reg(index) == expected, f"Changed x{index}: {self.reg(index):#x} != {expected:#x}"
        for i, initial in self.initial_fp.items():
            assert self.uc.reg_read(getattr(gates.r, f"UC_RISCV_REG_F{i}")) == initial, f"Changed f{i}"

    def read(self, uc, access, address, size, value, userdata):
        if gates.STACK-144 <= address and address+size <= gates.STACK:
            assert self.should_observe
        else:
            assert self.display
            assert (address, size) in ((gates.FRAME-0x70, 4), (gates.ENVELOPE+1, 1),
                                       (gates.ENVELOPE+4, 2), (gates.ENVELOPE+6, 2))
        self.reads.append((address, size))

    def write(self, uc, access, address, size, value, userdata):
        assert self.should_observe and size == 4
        assert gates.STACK-144 <= address and address+size <= gates.STACK-4
        self.writes.append((address, size))

    def instruction(self, uc, address, size, userdata):
        if self.csr_fixture_active:
            assert address in (CSR_FIXTURE, CSR_FIXTURE+4)
            return
        self.pcs.append(address)
        sp = self.reg(2); self.min_sp = min(self.min_sp, sp)
        assert sp in (gates.STACK, gates.STACK-144) and sp % 16 == 0
        if address == self.symbols["glassly_input_observe"]:
            assert self.should_observe and not self.observed and sp == gates.STACK-144
            assert self.reg(10) == self.envelope
            continuation = self.reg(1)
            self.observed.append((self.class_byte & 63, self.event, self.length))
            for i in INT_CALLER: self.set(i, 0xb0000000+i)
            for i in FP_CALLER: uc.reg_write(getattr(gates.r, f"UC_RISCV_REG_F{i}"), 0xffffffff40000000+i)
            self.set(5, 0x5f); self.set(1, continuation)
            uc.reg_write(gates.r.UC_RISCV_REG_PC, CSR_FIXTURE+8)
            return
        targets = {gates.STOCK_SERVICE, gates.STOCK_DISPLAY,
                   *(self.symbols[name] for name in ("glassly_graphics_probe", "glassly_graphics_command",
                                                     "glassly_graphics_display", "glassly_input_command"))}
        if address in targets:
            assert not self.boundary_seen and address == self.expected_target
            assert sp == gates.STACK and bool(self.observed) == self.should_observe
            self.assert_boundary_registers(); self.boundary_seen = True
            if self.display: uc.reg_write(gates.r.UC_RISCV_REG_PC, self.reg(1))
            else: uc.emu_stop()
        elif address == gates.CONTINUE:
            assert self.display and self.boundary_seen
            self.assert_boundary_registers(); self.continuation_seen = True; uc.emu_stop()
        else:
            assert gates.ENTRY <= address < gates.ENTRY+len(self.blob) or address in (gates.CALLSITE, gates.CALLSITE+4, CSR_FIXTURE+8, CSR_FIXTURE+12)

    def run(self):
        self.uc.emu_start(gates.CALLSITE if self.display else gates.ENTRY, 0, count=300)
        assert self.boundary_seen and (not self.display or self.continuation_seen)
        saved = self.reg(5); self.csr_fixture_active = True
        self.uc.emu_start(CSR_FIXTURE+4, 0, count=1)
        self.csr_fixture_active = False
        assert self.reg(5) == 0x23, "Changed fcsr"
        self.set(5, saved)
        assert bool(self.observed) == self.should_observe
        if self.should_observe:
            assert self.min_sp == gates.STACK-144 and len(self.writes) == 35
            assert bytes(self.uc.mem_read(gates.STACK-4096, 4096-144)) == b"\x5a"*(4096-144)
            assert bytes(self.uc.mem_read(gates.STACK-4, 4)) == b"\x5a"*4
        else:
            assert self.min_sp == gates.STACK and not self.writes
            assert bytes(self.uc.mem_read(gates.STACK-4096, 4096)) == b"\x5a"*4096
        if self.display:
            assert self.pcs[:3] == [gates.CALLSITE, gates.CALLSITE+4, gates.DISPLAY]
            if not self.envelope: assert self.reads == [(gates.FRAME-0x70, 4)]
        else: assert not self.reads
        RESULTS.append({"command": self.command, "class_byte": self.class_byte, "event": self.event,
                        "length": self.length, "null_envelope": not bool(self.envelope),
                        "observer_calls": len(self.observed), "stock_or_handler": hex(self.expected_target),
                        "max_gate_stack": gates.STACK-self.min_sp, "original_state_restored": True})


class InputGateTests(unittest.TestCase):
    def test_all_commands(self):
        for request in (0, gates.ENVELOPE):
            for command in range(256): InputGateMachine(command=command, request=request).run()

    def test_all_classes_and_known_events(self):
        for class_byte in range(256):
            for event in (0, *BUTTONS, *IMU, 0x474c, 0xffff):
                InputGateMachine(class_byte=class_byte, event=event).run()

    def test_input_length_and_event_rejection(self):
        for class_byte in (2, 3, 0x42, 0x43, 0x82, 0x83, 0xc2, 0xc3):
            for length in (1, 255, 256, 65535):
                for event in (*BUTTONS, *IMU):
                    InputGateMachine(class_byte=class_byte, event=event, length=length).run()
            for event in (9, 0x1f7a, 0x1f80, 0x1faf, 0x1fba, 0xfffe):
                InputGateMachine(class_byte=class_byte, event=event).run()

    def test_null_stock_path(self):
        for class_byte in (2, 3, 63):
            InputGateMachine(class_byte=class_byte, event=1, null_envelope=True).run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=BUILD)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(); gates.BUILD = args.build.resolve()
    assert gates.u.__version__ == "2.1.4"
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(InputGateTests))
    build = json.loads((gates.BUILD/"build.json").read_text())
    report = {"format": "memomind-input-gate-emulation-v1", "build": str(gates.BUILD),
              "blob_sha256": build["blob_sha256"], "architecture": "UC_ARCH_RISCV / UC_MODE_RISCV32",
              "all_passed": result.wasSuccessful(), "test_groups": result.testsRun, "cases": RESULTS,
              "successful_cases": len(RESULTS), "gate_stack_bytes": 144,
              "limitations": ["Actual gates and patched callsite execute; all C handlers and observer bodies are mocked.",
                              "The observer mock poisons caller-saved integer/FPR/fcsr; ABI callee state is honored.",
                              "No hardware input, stock dispatcher execution or device writes."]}
    if args.report: args.report.write_text(json.dumps(report, indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__": main()
