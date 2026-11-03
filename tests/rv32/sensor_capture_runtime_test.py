#!/usr/bin/env python3
"""Linked sensor commands and patched native acquisition; bus and RTOS are mocks."""
import argparse
import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

from microphone_runtime_emulator_test import G
from wake_control_runtime_emulator_test import WakeMachine
from flash_canary_runtime_emulator_test import REGISTRY
import sensor_native_abi_test as S


class SensorMachine(WakeMachine):
    def native(self, name, args):
        if name == 'mic_clock':
            assert not self.critical
            return self.now
        return super().native(name, args)

    def region(self, address, size, writing=False):
        if REGISTRY + 208 <= address and address + size <= REGISTRY + 256:
            if writing:
                assert self.critical
            return 'sensor-registry'
        return super().region(address, size, writing)

    def sensor(self, op=0, mask=3):
        body = b'SC\1' + bytes([op]) + (bytes([mask]) if op == 1 else b'')
        reply = self.service(0x76, self.request(body))[0]
        assert reply['glassly'] == 'sensors' and reply['abi'] == 1
        return reply, bytes.fromhex(reply['stateHex'])

    def begin(self, mask=1):
        self.call('glassly_sensor_begin', mask)
        return self.reg(10)

    def finish(self, generation, mask=1, data=bytes(range(14))):
        ptr = self.allocate(len(data), 'sensor-borrowed', data, writable=False)
        self.call('glassly_sensor_finish', mask, generation, ptr)
        self.discard(ptr)


class Tests(unittest.TestCase):
    def test_lifecycle_and_stale_completion(self):
        m = SensorMachine()
        assert m.sensor(1)[1][3:6] == b'\3\0\0'
        gen = m.begin()
        m.finish(gen)
        m.finish(gen, 2, struct.pack('<H', 1000))
        state = m.sensor()[1]
        assert state[3:6] == b'\3\3\3' and state[36:50] == bytes(range(14)) and state[50:] == b'\xe8\3'
        m.now += 1001
        assert m.sensor()[1][5] == 2
        m.sensor(2)
        m.sensor(1, 1)
        m.finish(gen)
        assert m.sensor()[1][4] == 0
        m.finish(m.begin())
        assert m.sensor()[1][4] == 1
        m.call('glassly_graphics_cleanup', display=True)
        assert m.sensor()[1][3:6] == bytes(3)
        assert m.sensor(3)[0]['result'] == 'inactive'

    def test_mode11_expiry_and_bounds(self):
        m = SensorMachine()
        m.now = 0xfffffff0
        m.sensor(1)
        gen = m.begin()
        m.now = (m.now + 90000) & 0xffffffff
        m.finish(gen)
        assert not m.begin() and m.sensor()[1][3:6] == bytes(3)
        m.sensor(1)
        m.execute_display(bytes([11]))
        assert not m.begin()
        for body in (b'', b'SC\1\1', b'SC\1\1\0', b'SC\1\1\4', b'SC\1\0\0', b'SC\2\0'):
            assert m.service(0x76, m.request(body))[0]['result'] == 'invalid'
        m.fail_alloc_sizes.add(208)
        assert m.service(0x76, m.request(b'SC\1\0'))[0] == {'status': 4}

    def test_freestanding_memset(self):
        m = SensorMachine()
        for size in (0, 1, 13, 52, 255):
            ptr = m.allocate(size + 2, 'memset-buffer', b'\xa5' * (size + 2))
            m.call('memset', ptr + 1, 0x1234, size)
            assert m.reg(10) == ptr + 1
            assert m.read(ptr, size + 2) == b'\xa5' + b'\x34' * size + b'\xa5'


def patched_acquisition(build):
    sys.path.insert(0, str(G.ROOT / 'scripts'))
    from build_memomind_minimal_owner import construct
    from memomind_ota import unpack_ota
    manifest = json.loads((build / 'build.json').read_text())
    blob = (build / 'graphics.bin').read_bytes()
    image, evidence = construct((G.ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes(), blob, manifest)
    body = unpack_ota(image)[1][3]['raw'][32:]
    symbols = manifest['symbols']
    results = []
    for kind in (1, 2):
        for alignment in (0, 8):
            for error in (0, 11):
                for generation in (0, 3):
                    uc = G.u.Uc(G.u.UC_ARCH_RISCV, G.u.UC_MODE_RISCV32)
                    uc.mem_map(S.BASE & ~4095, 0x200000)
                    uc.mem_write(S.BASE, body)
                    uc.mem_map(0x02000000, 0x60000)
                    uc.mem_map(0x03000000, 0x20000)
                    uc.mem_map(S.RET, 4096)
                    uc.mem_write(S.OUT - 2, b'\xa5' * 20)
                    uc.mem_write(0x02011628, struct.pack('<I', 7))
                    uc.mem_write(0x02011ac0, struct.pack('<I', S.TABLE))
                    uc.mem_write(S.TABLE + 4, struct.pack('<I', S.RET + 16))
                    stubs = {0x0434742e: 'imu_bus', 0x043421d2: 'lock', 0x04342200: 'unlock',
                             0x02003d5e: 'log', S.RET + 16: 'als_driver',
                             symbols['glassly_sensor_begin']: 'begin', symbols['glassly_sensor_finish']: 'finish'}
                    for address in stubs:
                        uc.mem_write(address, bytes.fromhex('67800000'))
                    def get(i): return uc.reg_read(getattr(G.r, f'UC_RISCV_REG_X{i}'))
                    def put(i, value): uc.reg_write(getattr(G.r, f'UC_RISCV_REG_X{i}'), value)
                    for i in range(1, 32): put(i, 0xa0000000 + i)
                    sp = S.SP - alignment
                    put(1, S.RET); put(2, sp); put(3, S.GP); put(10, S.OUT); put(11, 0); put(12, 0)
                    saved = {i: get(i) for i in G.CALLEE}
                    for i in G.FP_CALLEE: uc.reg_write(getattr(G.r, f'UC_RISCV_REG_F{i}'), 0x3f800000 + i)
                    calls = []
                    sample = struct.pack('>7h', -32768, -32768, -17, -16, -1, 0, 32767)
                    def hook(mu, address, size, _):
                        if address not in stubs:
                            assert G.ENTRY <= address < G.ENTRY + len(blob) or any(lo <= address < hi for lo, hi in S.RANGES), hex(address)
                            return
                        name = stubs[address]
                        args = [get(10 + i) for i in range(3)]
                        value = 0
                        if name in ('begin', 'finish'):
                            assert get(2) % 16 == 0 and args[0] == kind
                        if name == 'begin': value = generation
                        elif name == 'finish':
                            assert args[1] == generation and error == 0
                            expected = sample if kind == 1 else struct.pack('<H', 1000)
                            assert bytes(mu.mem_read(args[2], len(expected))) == expected
                        elif name == 'imu_bus':
                            assert kind == 1 and args[0] == 9 and args[2] == 14 and get(2) % 16 == 0
                            mu.mem_write(args[1], sample); value = error
                        elif name == 'als_driver': mu.mem_write(args[0], b'\xff\xff'); value = error
                        elif name in ('lock', 'unlock'): assert args[0] == 1
                        calls.append(name)
                        ret = get(1)
                        for i in G.CALLER: put(i, 0xd0000000 + i)
                        put(10, value); mu.reg_write(G.r.UC_RISCV_REG_PC, ret)
                    def write(mu, access, address, size, value, _):
                        assert sp - 256 <= address and address + size <= sp or S.OUT <= address and address + size <= S.OUT + 14
                    uc.hook_add(G.u.UC_HOOK_CODE, hook)
                    uc.hook_add(G.u.UC_HOOK_MEM_WRITE, write)
                    uc.emu_start(0x043475cc if kind == 1 else 0x0422b67a, S.RET, count=3000)
                    assert uc.reg_read(G.r.UC_RISCV_REG_PC) == S.RET
                    assert get(10) == (11 if error else 0) if kind == 1 else get(10) == int(not error)
                    for i, value in saved.items(): assert get(i) == value, (kind, alignment, i)
                    for i in G.FP_CALLEE: assert uc.reg_read(getattr(G.r, f'UC_RISCV_REG_F{i}')) == 0x3f800000 + i
                    expected = b'\xa5' * 14 if error else struct.pack('<7h', -2048, -2, -1, 1, 0, 2047, -32768) if kind == 1 else b'\xe8\3' + b'\xa5' * 12
                    assert bytes(uc.mem_read(S.OUT, 14)) == expected
                    assert calls.count('begin') == 1 and calls.count('finish') == int(not error)
                    assert bytes(uc.mem_read(S.OUT - 2, 2)) == bytes(uc.mem_read(S.OUT + 14, 2)) == b'\xa5\xa5'
                    results.append(dict(sensor=kind, stackAlignment=16 if alignment == 0 else 8, error=error, generation=generation, calls=calls))
    return dict(cases=len(results), results=results, imageSHA256=hashlib.sha256(image).hexdigest(),
                hooks=[row for row in evidence['launcher_edits'] if row['purpose'].startswith('sensor-')])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    G.BUILD = args.build.resolve()
    build = json.loads((G.BUILD / 'build.json').read_text())
    G.PINNED_SHA = build['blob_sha256']
    assert build['sensor_capture']
    hooks = patched_acquisition(G.BUILD)
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    args.report.write_text(json.dumps(dict(passed=result.wasSuccessful(), groups=result.testsRun,
        runtimeSHA256=G.PINNED_SHA, hooks=hooks, hardwareTested=False, nativeBusAndRTOSMocked=True,
        calls=G.RESULTS), indent=2) + '\n')
    return not result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
