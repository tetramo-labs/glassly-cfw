#!/usr/bin/env python3
"""Execute pinned probe-003 RV32 machine code with explicitly mocked natives.

This is not hardware emulation or a model of the native allocator/TLV internals.
Only four proven native call boundaries are stubbed. Unknown execution and
out-of-contract memory accesses fail closed. No firmware or device is modified.
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
BUILD = ROOT / "runtime/build/probe-003"
BLOB_SHA = "e6d9edd7e761fcc0c661e4b441eb45a642b4ead4a8acdb690286ceec7f42726b"
ENTRY, CODE_END = 0x0439bea0, 0x0439bf04
STOCK, RELEASE, JSON_REPLY, STATUS_REPLY = 0x042e4680, 0x042eff8e, 0x042ef9f6, 0x042ef924
RETURN = 0x05000000
# Synthetic, guarded harness RAM; these addresses are not a claimed device map.
STACK_BASE, STACK_TOP = 0x03000000, 0x03001000
CONTROL, RESPONSE, SEQUENCE = 0x03100000, 0x03100040, 0x03100080
REQUEST, JSON_NODE, STATUS_NODE = 0x03200000, 0x03200100, 0x03200200
CALLEE = (8, 9, *range(18, 28))
CALLER = (5, 6, 7, *range(10, 18), 28, 29, 30, 31)
EXPECTED_JSON = {"glassly": "runtime-probe", "abi": 1,
                 "profile": "H001Y-1.0.3.127", "entry": "0439bea0",
                 "writableStaticBytes": 0}
RESULTS = []
EXECUTED_PROBE_ADDRESSES = set()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned_blob():
    blob = (BUILD / "probe.bin").read_bytes()
    assert len(blob) == 208 and digest(blob) == BLOB_SHA, "Unexpected compiled probe bytes"
    elf = (BUILD / "probe.elf").read_bytes()
    assert elf[:7] == b"\x7fELF\x01\x01\x01", "Expected real ELF32 little-endian file"
    assert struct.unpack_from("<H", elf, 18)[0] == 243, "ELF must declare EM_RISCV"
    assert struct.unpack_from("<I", elf, 24)[0] == ENTRY, "Unexpected ELF entry"
    build = json.loads((BUILD / "build.json").read_text())
    assert build["blob_sha256"] == BLOB_SHA and build["blob_bytes"] == len(blob)
    return blob


class ProbeMachine:
    def __init__(self, command, nonempty=False, json_fails=False, status_fails=False,
                 response_address=RESPONSE):
        self.command, self.request = command, REQUEST if nonempty else 0
        self.json_fails, self.status_fails = json_fails, status_fails
        self.blob = pinned_blob()
        self.uc = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
        self.uc.mem_map(ENTRY & ~4095, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_write(ENTRY, self.blob)
        for page in (STOCK & ~4095, RELEASE & ~4095):
            self.uc.mem_map(page, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        # Valid RV32 RET instructions let Unicorn translate each stub boundary;
        # our pre-instruction hook handles it before this shim instruction runs.
        for address in (STOCK, RELEASE, JSON_REPLY, STATUS_REPLY):
            self.uc.mem_write(address, bytes.fromhex("67800000"))
        self.uc.mem_map(RETURN, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_write(RETURN, bytes.fromhex("13000000"))
        self.uc.mem_map(STACK_BASE, 4096, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(CONTROL, 4096, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(REQUEST, 4096, u.UC_PROT_READ)
        self.uc.mem_write(STACK_BASE, b"\xcc" * 4096)
        self.uc.mem_write(CONTROL, b"\xa5" * 4096)
        self.uc.mem_write(RESPONSE, struct.pack("<I", 0xdeadbeef))
        self.uc.mem_write(SEQUENCE, b"\x51")
        # The pointed-to list is opaque. RELEASE's observed ownership contract
        # is mocked; no invented node layout or allocator implementation.
        self.uc.mem_write(REQUEST, b"opaque-nonempty-request\0")
        for x in range(1, 32):
            self.set(x, 0xa1000000 + x * 0x101)
        for x, value in {1: RETURN, 2: STACK_TOP, 3: 0x02011688, 4: 0x0200abcd,
                         10: command, 11: self.request, 12: SEQUENCE, 13: response_address}.items():
            self.set(x, value)
        self.initial = {x: self.reg(x) for x in range(1, 32)}
        self.control_before = bytes(self.uc.mem_read(CONTROL, 4096))
        self.request_before = bytes(self.uc.mem_read(REQUEST, 4096))
        self.calls, self.writes, self.reads, self.helper_writes, self.pcs = [], [], [], [], []
        self.min_sp, self.stock_seen, self.release_seen = STACK_TOP, False, False
        self.uc.hook_add(u.UC_HOOK_CODE, self.instruction)
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self.write)
        self.uc.hook_add(u.UC_HOOK_MEM_READ, self.read)
        self.uc.hook_add(u.UC_HOOK_MEM_INVALID, self.invalid)

    def reg(self, x):
        return self.uc.reg_read(getattr(r, f"UC_RISCV_REG_X{x}"))

    def set(self, x, value):
        self.uc.reg_write(getattr(r, f"UC_RISCV_REG_X{x}"), value)

    @staticmethod
    def writable(address, size):
        return ((STACK_TOP-32 <= address and address+size <= STACK_TOP) or
                (RESPONSE <= address and address+size <= RESPONSE+4))

    def write(self, uc, access, address, size, value, userdata):
        assert self.writable(address, size), f"Out-of-bounds CPU write {address:#x}+{size}"
        self.writes.append((address, size))

    def read(self, uc, access, address, size, value, userdata):
        assert STACK_TOP-32 <= address and address+size <= STACK_TOP, \
            f"Unexpected CPU data read {address:#x}+{size}"
        self.reads.append((address, size))

    def invalid(self, uc, access, address, size, value, userdata):
        raise AssertionError(f"Unmapped/protected access {access} at {address:#x}+{size}")

    def helper_write(self, address, data):
        assert self.writable(address, len(data)), "Out-of-bounds mocked-native write"
        self.helper_writes.append((address, len(data)))
        self.uc.mem_write(address, data)

    def native_return(self, value):
        continuation = self.reg(1)
        assert ENTRY <= continuation < CODE_END
        # Native helpers may destroy all integer caller-saved registers. Poison
        # them to expose a wrapper that accidentally relies on their values.
        for x in CALLER:
            self.set(x, 0xd2000000+x*0x101)
        self.set(10, value)
        self.uc.reg_write(r.UC_RISCV_REG_PC, continuation)

    def instruction(self, uc, address, size, userdata):
        self.pcs.append(address)
        self.min_sp = min(self.min_sp, self.reg(2))
        assert STACK_TOP-32 <= self.reg(2) <= STACK_TOP and self.reg(2) % 16 == 0
        if address == STOCK:
            assert self.command != 0x7e
            assert not self.calls and not self.writes and self.min_sp == STACK_TOP
            # All original arguments and return/stack state must reach stock.
            for x in (1, 2, 3, 4, *range(10, 18), *CALLEE):
                assert self.reg(x) == self.initial[x], f"Stock forwarding changed x{x}"
            self.calls.append("stock")
            self.stock_seen = True
            uc.emu_stop()
        elif address == RELEASE:
            assert self.command == 0x7e and self.request != 0 and not self.release_seen
            pointer_slot = self.reg(10)
            assert pointer_slot != self.request and STACK_TOP-32 <= pointer_slot <= STACK_TOP-4
            assert struct.unpack("<I", uc.mem_read(pointer_slot, 4))[0] == self.request
            assert self.calls == [], "Request cleanup must precede response allocation"
            self.calls.append("release_by_address")
            self.release_seen = True
            self.helper_write(pointer_slot, bytes(4))
            self.native_return(0)
        elif address == JSON_REPLY:
            assert self.command == 0x7e
            assert self.release_seen == bool(self.request)
            ptr = self.reg(10)
            assert CODE_END <= ptr < ENTRY+len(self.blob)
            raw = bytes(uc.mem_read(ptr, ENTRY+len(self.blob)-ptr))
            assert b"\0" in raw
            self.json_text = raw.split(b"\0", 1)[0].decode("ascii")
            assert json.loads(self.json_text) == EXPECTED_JSON
            self.calls.append("json_response")
            self.native_return(0 if self.json_fails else JSON_NODE)
        elif address == STATUS_REPLY:
            assert self.json_fails and self.calls[-1] == "json_response"
            assert (self.reg(10), self.reg(11)) == (4, 0)
            self.calls.append("status_4_null_text")
            self.native_return(0 if self.status_fails else STATUS_NODE)
        else:
            assert ENTRY <= address < CODE_END, f"Unexpected executable address {address:#x}"

    def run(self):
        self.uc.emu_start(ENTRY, RETURN, count=200)
        assert self.stock_seen or self.uc.reg_read(r.UC_RISCV_REG_PC) == RETURN, "No valid return"
        for x in (1, 2, 3, 4, *CALLEE):
            assert self.reg(x) == self.initial[x], f"Preserved register x{x} changed"
        response = struct.unpack("<I", self.uc.mem_read(RESPONSE, 4))[0]
        expected_control = bytearray(self.control_before)
        if self.command == 0x7e:
            assert not self.stock_seen and self.min_sp == STACK_TOP-32
            expected = JSON_NODE if not self.json_fails else (0 if self.status_fails else STATUS_NODE)
            assert response == expected, "Wrong response-list assignment"
            struct.pack_into("<I", expected_control, RESPONSE-CONTROL, expected)
            assert self.release_seen == bool(self.request)
            assert self.calls.count("json_response") == 1
            assert self.calls.count("status_4_null_text") == int(self.json_fails)
        else:
            assert self.calls == ["stock"] and not self.writes and not self.helper_writes
        assert bytes(self.uc.mem_read(CONTROL, 4096)) == bytes(expected_control), "Caller canary/sequence changed"
        assert bytes(self.uc.mem_read(REQUEST, 4096)) == self.request_before, "Opaque request bytes changed"
        assert bytes(self.uc.mem_read(STACK_BASE, 4096-32)) == b"\xcc"*(4096-32)
        result = {"command": self.command, "nonempty_request": bool(self.request),
                  "json_allocation_fails": self.json_fails, "status_allocation_fails": self.status_fails,
                  "route": "stock" if self.stock_seen else "probe", "calls": self.calls,
                  "stack_bytes": STACK_TOP-self.min_sp, "cpu_write_count": len(self.writes),
                  "mocked_native_write_count": len(self.helper_writes),
                  "preserved_registers": True, "memory_bounds_pass": True}
        RESULTS.append(result)
        EXECUTED_PROBE_ADDRESSES.update(pc for pc in self.pcs if ENTRY <= pc < CODE_END)
        return result


class ProbeTests(unittest.TestCase):
    def test_all_256_commands_with_null_and_nonempty_requests(self):
        for nonempty in (False, True):
            for command in range(256):
                with self.subTest(command=command, nonempty=nonempty):
                    ProbeMachine(command, nonempty).run()

    def test_probe_response_allocation_failures_and_cleanup(self):
        for nonempty in (False, True):
            for json_fails, status_fails in ((False, False), (True, False), (True, True)):
                with self.subTest(nonempty=nonempty, json_fails=json_fails, status_fails=status_fails):
                    ProbeMachine(0x7e, nonempty, json_fails, status_fails).run()

    def test_guard_rejects_write_to_adjacent_caller_canary(self):
        with self.assertRaisesRegex(AssertionError, "Out-of-bounds CPU write"):
            ProbeMachine(0x7e, response_address=RESPONSE+4).run()

    def test_guard_rejects_unmapped_response_write(self):
        with self.assertRaises(u.UcError) as rejected:
            ProbeMachine(0x7e, response_address=0x06000000).run()
        self.assertEqual(rejected.exception.errno, u.UC_ERR_WRITE_UNMAPPED)


def main():
    global BUILD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--build", type=Path, default=BUILD,
                        help="Probe build directory; exact installed blob hash is still required")
    args = parser.parse_args()
    BUILD = args.build.resolve()
    assert u.__version__ == "2.1.4", "Use the pinned task-local Unicorn version"
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeTests))
    report = {"format": "memomind-rv32-probe-emulation-v1", "kind": "mocked-native execution, not hardware",
              "unicorn_version": u.__version__, "architecture": "UC_ARCH_RISCV / UC_MODE_RISCV32",
              "blob_path": str(BUILD / "probe.bin"), "blob_sha256": BLOB_SHA,
              "elf_machine": "EM_RISCV (243), ELF32 little-endian; no architecture spoofing",
              "elf_sha256": digest((BUILD / "probe.elf").read_bytes()),
              "native_stubs": {hex(STOCK): "capture untouched forwarding boundary, stop",
                               hex(RELEASE): "verify pointer-to-pointer, record cleanup, zero local slot",
                               hex(JSON_REPLY): "validate linked JSON, return opaque response pointer or NULL",
                               hex(STATUS_REPLY): "verify status4/null text, return opaque response pointer or NULL"},
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "successful_execution_cases": len(RESULTS), "all_passed": result.wasSuccessful(),
              "stock_forwarding_cases": sum(case["route"] == "stock" for case in RESULTS),
              "probe_command_cases": sum(case["route"] == "probe" for case in RESULTS),
              "executed_probe_instruction_addresses": [f"0x{pc:08x}" for pc in sorted(EXECUTED_PROBE_ADDRESSES)],
              "cases": RESULTS,
              "limitations": ["Native helper internals, real allocation, RTOS scheduling and hardware are not executed.",
                              "Synthetic guarded RAM is not an asserted device heap or stack allocation.",
                              "Stock dispatch is observed at its entry boundary, not emulated afterward.",
                              "Firmware boot, transport delivery and on-device execution require separate evidence."]}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
