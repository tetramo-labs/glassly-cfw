"""Inspect the pinned vendor debug ELF; emulate only its code-read setup.

Never launch the utility or access hardware. Transport, time and printing are
stubbed. This is related-family protocol evidence, not a Zero 2 binding.
"""
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, __version__
from unicorn.x86_const import (UC_X86_REG_RIP, UC_X86_REG_RSP, UC_X86_REG_RAX,
                               UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX,
                               UC_X86_REG_RCX, UC_X86_REG_FS_BASE)

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'research/downloads/yichip-16xx/SDK/util/tool/e'
STOP, STACK, BUFFER, TLS = 0x300000, 0x700000, 0x500000, 0x400000


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def parse_elf(data):
    require(data[:7] == b'\x7fELF\x02\x01\x01', 'Expected ELF64 little endian')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(h[2] == 62, 'Expected x86-64')
    ph = [struct.unpack_from('<IIQQQQQQ', data, h[5] + i*h[9]) for i in range(h[10])]
    sh = [struct.unpack_from('<IIQQQQIIQQ', data, h[6] + i*h[11]) for i in range(h[12])]
    symbols = {}
    for s in sh:
        if s[1] != 2:
            continue
        strings = sh[s[6]]
        names = data[strings[4]:strings[4]+strings[5]]
        for off in range(s[4], s[4]+s[5], s[9]):
            n, info, other, index, address, size = struct.unpack_from('<IBBHQQ', data, off)
            name = names[n:].split(b'\0', 1)[0].decode()
            symbols[name] = (address, size)
    return ph, symbols


def emulate(data):
    segments, symbols = parse_elf(data)
    expected = {'readcoderam2': (0x5b0c, 415), 'stop_cpub': (0x59de, 39),
                'write3bytes': (0x477f, 45)}
    require(all(symbols[k] == v for k, v in expected.items()), 'Symbol anchors changed')
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(0, 0x200000)
    for p in segments:
        if p[0] == 1:
            uc.mem_write(p[3], data[p[2]:p[2]+p[5]])
    for address, size in [(STOP, 4096), (STACK, 0x10000), (BUFFER, 4096), (TLS, 4096)]:
        uc.mem_map(address, size)
    uc.reg_write(UC_X86_REG_FS_BASE, TLS)
    events = []
    initial_control = 0

    def ret(value=0):
        sp = uc.reg_read(UC_X86_REG_RSP)
        target = struct.unpack('<Q', uc.mem_read(sp, 8))[0]
        uc.reg_write(UC_X86_REG_RSP, sp+8)
        uc.reg_write(UC_X86_REG_RAX, value)
        uc.reg_write(UC_X86_REG_RIP, target)

    def hook(emu, address, size, _):
        args = [emu.reg_read(r) for r in (UC_X86_REG_RDI, UC_X86_REG_RSI,
                                        UC_X86_REG_RDX, UC_X86_REG_RCX)]
        if address == STOP:
            emu.emu_stop()
        elif address == symbols['readbyte'][0]:
            require(args[0] == 0x8203, 'Unexpected debug-control read')
            events.append(['read_control', args[0], initial_control])
            ret(initial_control)
        elif address == symbols['writebyte'][0]:
            events.append(['write', args[0], args[1] & 255, 1])
            ret()
        elif address == symbols['writedata'][0]:
            require(args[0] == 0x8022 and args[2:] == [3, 1], 'Unexpected cleanup write')
            value = int.from_bytes(emu.mem_read(args[1], 3), 'little')
            events.append(['write', args[0], value, 3])
            ret()
        elif address == symbols['readdata'][0]:
            require(args[0] == 0x8025 and args[1] == BUFFER and args[2] <= 64 and args[3] == 2,
                    'Unexpected data-port request')
            events.append(['read_port', args[0], args[2], args[3]])
            emu.mem_write(BUFFER, bytes(range(args[2])))
            ret()
        elif address == 0x3350:  # gettimeofday PLT
            emu.mem_write(args[0], bytes(16))
            ret()
        elif address == 0x33e0:  # fprintf PLT
            ret()
        else:
            require(any(a <= address and address+size <= a+n for a, n in expected.values()),
                    f'Unexpected code at {address:#x}; no fallback syscall execution')

    uc.hook_add(UC_HOOK_CODE, hook)
    results = []
    indices = [0, 0x7ff, 0x800, 0x4eda, 0x4f01, 0x7dc1, 0x7fff, 0x8000, 0x10000, 0x17fff]
    for initial_control in (0x20, 0x21):
        for pc in indices:
            for length in (4, 64):
                events.clear()
                sp = STACK + 0x8000 - 8
                uc.mem_write(sp, struct.pack('<Q', STOP))
                uc.reg_write(UC_X86_REG_RSP, sp)
                uc.reg_write(UC_X86_REG_RDI, BUFFER)
                uc.reg_write(UC_X86_REG_RSI, length)
                uc.reg_write(UC_X86_REG_RDX, pc)
                uc.emu_start(symbols['readcoderam2'][0], STOP+1, count=10000)
                require(uc.reg_read(UC_X86_REG_RIP) == STOP, 'Routine did not return')
                bank = 0x80 if pc < 0x800 else 0x40 if pc < 0x8000 else 0
                selectors = [pc >> 12 & 255, bank | (pc >> 6 & 63), pc*4 & 255]
                expected_events = [
                    ['read_control', 0x8203, initial_control],
                    ['write', 0x8203, initial_control | 1, 1],
                    *[['write', 0x8022+i, value, 1] for i, value in enumerate(selectors)],
                    ['read_port', 0x8025, length, 2], ['write', 0x8022, 0, 3]]
                require(events == expected_events, 'Selector/control trace differs')
                require(bytes(uc.mem_read(BUFFER, length)) == bytes(range(length)), 'Output changed')
                results.append({'index': hex(pc), 'length': length,
                                'initial_control': hex(initial_control),
                                'selectors': [hex(x) for x in selectors]})
    return {'cases': len(results), 'cases_detail': results,
            'executed_functions': {k: {'address': hex(a), 'size': n} for k, (a, n) in expected.items()},
            'stubbed': ['readbyte', 'writebyte', 'writedata', 'readdata', 'gettimeofday', 'fprintf'],
            'control_operation': 'read 0x8203; write original OR 1',
            'data_operation': 'readdata(0x8025, destination, byte_length, flags=2)',
            'cleanup': 'write three zero bytes starting at 0x8022',
            'radio_resume_in_this_function': False,
            'zero2_compatibility_proven': False,
            'limitations': ['No device opened; returned bytes are synthetic',
                           'Vendor debug transport is not the 8BitDo bootloader protocol',
                           'Register access, selector meaning and stop/resume behavior on Zero 2 remain unverified']}


def main():
    refs = json.loads((ROOT/'docs/evidence/references.json').read_text())['yichip_debug_utility']
    data = PATH.read_bytes()
    require(hashlib.sha256(data).hexdigest() == refs['files']['SDK/util/tool/e']['sha256'],
            'Vendor debug utility hash mismatch')
    result = {'mode': 'offline_x86_64_emulation', 'hardware_access': False,
              'source_revision': refs['revision'], 'utility_sha256': hashlib.sha256(data).hexdigest(),
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'unicorn_version': __version__, 'code_read': emulate(data)}
    output = ROOT/'build/references/yichip-debug.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(f'{result["code_read"]["cases"]} offline selector traces passed; no hardware access. {output}')


if __name__ == '__main__':
    main()
