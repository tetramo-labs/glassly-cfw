"""Audit stock idle thresholds/guards offline, stopping before power-related I/O.

No hardware, timing simulation, firmware mutation or proof of a live shutdown
cause. BLE/HID/mode/threshold values are explicit synthetic inputs.
"""
import itertools
import json
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR
from firmware_image import ROOT, load_stock, sha256
from startup import reconstruct

STOP = 0x1018100


def machine(payload):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x1018000, 0x12000)
    uc.mem_write(0x1018000, payload)
    uc.mem_map(0x20000, 0x10000)
    for address, data in reconstruct(payload)[1].items():
        uc.mem_write(address, data)
    uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
    uc.reg_write(UC_ARM_REG_LR, STOP | 1)
    return uc


def run(uc, entry):
    uc.emu_start(entry | 1, STOP, count=10000)
    return uc.reg_read(UC_ARM_REG_PC)


def word(uc, address):
    return int.from_bytes(uc.mem_read(address, 4), 'little')


def verify():
    payload = load_stock()[2][1]
    guards, thresholds = [], []
    for ble, hid, cable, mode, count in itertools.product((0, 2), (0, 2), (0, 1), (0, 2, 3), (5999, 6000)):
        uc = machine(payload)
        for address, value in [(0x20682, ble), (0x20182, hid), (0x201b8, cable), (0x20181, mode)]:
            uc.mem_write(address, bytes([value]))
        uc.mem_write(0x20194, struct.pack('<II', 6000, count))
        reached = []

        def stop_before_io(emu, address, size, _):
            reached.append(emu.reg_read(UC_ARM_REG_R0))
            emu.emu_stop()

        uc.hook_add(UC_HOOK_CODE, stop_before_io, begin=0x1020350, end=0x1020350)
        pc = run(uc, 0x101db3c)
        expected = count >= 6000 and not (cable and hid == 2) and mode not in (2, 3)
        assert reached == ([10] if expected else [])
        assert pc == (0x1020350 if expected else STOP)
        if not expected:
            assert uc.reg_read(UC_ARM_REG_SP) == 0x2ff00
        wanted_count = count if count < 6000 or expected else 0
        assert word(uc, 0x20198) == wanted_count
        guards.append(dict(ble_state=ble, hid_state=hid, flag_201b8=cable, mode_20181=mode,
                           idle_counter=count, threshold=6000, reaches_pre_power_call=expected))
    for ble, hid, mode, scale in itertools.product((0, 2), (0, 2), (0, 3), (5, 10, 20)):
        uc = machine(payload)
        for address, value in [(0x20682, ble), (0x20182, hid), (0x201b4, mode), (0x2058d, scale)]:
            uc.mem_write(address, bytes([value]))
        uc.mem_write(0x20198, struct.pack('<I', 12345))
        assert run(uc, 0x1022938) == STOP
        expected = 90000 if ble == 2 or hid == 2 else 18000
        if mode == 0:
            expected = expected * 10 // scale
        assert word(uc, 0x20194) == expected and word(uc, 0x20198) == 0
        assert uc.reg_read(UC_ARM_REG_SP) == 0x2ff00
        thresholds.append(dict(ble_state=ble, hid_state=hid, mode_201b4=mode, scale=scale,
                               threshold=expected, counter_reset=True))
    return dict(kind='Offline execution of stock idle guard and threshold setter', hardware_accessed=False,
                stock_plaintext_sha256=sha256(payload), guards=guards, thresholds=thresholds,
                instruction_stubs=[], stop_before_io='0x01020350 called with argument 10',
                limits=['Synthetic state does not establish the active live threshold or mode',
                        'No power I/O executed; reaching the boundary is not an observed shutdown',
                        'No wall-clock cadence simulated; no duration inferred from counter values'])


if __name__ == '__main__':
    report = verify()
    output = ROOT / 'build/stock/idle-emulation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Passed {len(report["guards"])} idle-guard and {len(report["thresholds"])} threshold cases; no hardware I/O.')
