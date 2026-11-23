"""Capture actual startup BLE-name and visibility command construction offline.

No radio/device is emulated. Stop at IPC entry, before submission; replace only
the startup hardware initializer with a return. Peripheral registers are RAM.
"""
import itertools
import json
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from firmware_image import ROOT, load_stock, sha256
from build_name_probe import build
from build_ble_probe import build as build_ble
from startup import reconstruct


def capture(payload, entry, arguments=(), chip_id=None):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x1018000, 0x12000)
    uc.mem_write(0x1018000, payload)
    uc.mem_map(0x20000, 0x10000)
    uc.mem_map(0xe000e000, 0x1000)  # Synthetic NVIC register page.
    for address, data in reconstruct(payload)[1].items():
        uc.mem_write(address, data)
    if chip_id is not None:
        uc.mem_write(0x20000, chip_id)
    uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
    uc.reg_write(UC_ARM_REG_LR, 0x1018101)
    for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), arguments):
        uc.reg_write(register, value)
    commands = []
    stubs = []

    def hook(emu, address, size, _):
        if address == 0x1018d8c:
            stubs.append('0x01018d8c startup hardware initializer: return without effects')
            emu.reg_write(UC_ARM_REG_PC, emu.reg_read(UC_ARM_REG_LR))
        elif address == 0x10202c8:
            pointer = emu.reg_read(UC_ARM_REG_R0)
            descriptor = bytes(emu.mem_read(pointer, 8))
            length, data_pointer = struct.unpack_from('<HI', descriptor, 2)
            if length > 64:
                raise AssertionError('Unexpected command size')
            commands.append({'opcode': descriptor[1], 'length': length,
                             'payload_hex': bytes(emu.mem_read(data_pointer, length)).hex()})
            emu.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.emu_start(entry | 1, 0x1018100, count=10000)
    if uc.reg_read(UC_ARM_REG_PC) != 0x10202c8 or len(commands) != 1:
        raise AssertionError('Did not reach exactly one command submission boundary')
    return commands[0], stubs


def verify():
    stock = load_stock()[2][1]
    patched = build()[1]
    ble_probe = build_ble()[1]
    names = []
    for image, payload in [('stock', stock), ('name-probe', patched), ('ble-probe', ble_probe)]:
        for chip_id in (bytes(6), bytes.fromhex('0123456789ab'), bytes([255]) * 6):
            command, stubs = capture(payload, 0x101a570, chip_id=chip_id)
            assert command == {'opcode': 4, 'length': 14, 'payload_hex': (b'80EL' + bytes(10)).hex()}
            assert len(stubs) == 1
            names.append({'image': image, 'synthetic_chip_id': chip_id.hex(), 'command': command})
    visibility = []
    for image, payload, flag in [('stock', stock, 0), ('ble-probe', ble_probe, 4)]:
        for args in itertools.product((0, 1), repeat=3):
            command, stubs = capture(payload, 0x101a304, args)
            assert command == {'opcode': 2, 'length': 1, 'payload_hex': bytes([args[0] | 2 | flag]).hex()}
            assert not stubs
            visibility.append({'image': image, 'arguments': args, 'command': command})
    return {'kind': 'Offline stock instruction execution to IPC entry; no submission or radio execution',
            'hardware_accessed': False, 'stock_plaintext_sha256': sha256(stock),
            'name_probe_plaintext_sha256': sha256(patched),
            'ble_probe_plaintext_sha256': sha256(ble_probe),
            'name_cases': names, 'visibility_cases': visibility,
            'stubs': ['0x01018d8c startup hardware initializer: return without effects'],
            'synthetic_registers': ['NVIC register page 0xe000e000'],
            'limits': ['Opcode 04 BLE-name meaning is supported by related YC1021/YC1121 source',
                       'Actual advertisement name, visibility, acceptance and on-air identity remain unobserved',
                       'The 80EL name alone does not identify this physical controller']}


if __name__ == '__main__':
    result = verify()
    out = ROOT / 'build/stock/ble-setup-emulation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print('Passed 9 startup name cases and 16 visibility-command cases; no hardware accessed.')
