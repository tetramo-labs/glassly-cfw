"""Offline startup OTP-call audit using the locally captured ARM ROM prefix.

No device access. OTP input and peripheral registers are synthetic; all ROM
instructions, including delay loops, execute without function stubs. This proves
only the isolated calls' memory footprint, not peripheral timing or IRQ nesting.
"""
import argparse
import hashlib
import json
from pathlib import Path

from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS,
                     UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE,
                     UC_PROT_READ, UC_PROT_EXEC, __version__)
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)

PREFIX_SIZE = 0x7fa0
PREFIX_SHA256 = 'cd416afad292582d97a74cfc07bae1009fbcc637de44955873e479cd0b65222a'
SP, STOP = 0x2ff00, 0x10000
ENTRIES = {'init_otp': 0x442c, 'read_chipid': 0x45d8, 'deinit_otp': 0x4480}
# Half-open instruction ranges, excluding literal pools.
CODE = ((0xc6, 0xce), (0x4238, 0x4254), (0x442c, 0x446e),
        (0x4480, 0x4494), (0x449c, 0x44d0), (0x45d8, 0x45e6))
PERIPHERAL_WRITES = {(0xf856c, 4), (0xc8973, 1), (0xf850a, 2), (0xf8508, 2)}
PERIPHERAL_READS = {(0xf856c, 4), (0xc8973, 1), (0xf8560, 4), (0xf850c, 1)}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def audit(data):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0, 0x8000, UC_PROT_READ | UC_PROT_EXEC)
    uc.mem_write(0, data)
    uc.mem_map(STOP, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
    uc.mem_map(0x20000, 0x10000)
    uc.mem_map(0xc8000, 0x1000)
    uc.mem_map(0xf8000, 0x1000)
    active, destination, fixture = '', 0, b''
    writes, reads, pcs = [], [], set()
    stack_low = SP
    steps = 0

    def code(emu, address, size, _):
        nonlocal steps, stack_low
        if address == STOP:
            emu.emu_stop()
            return
        require(any(lo <= address and address + size <= hi for lo, hi in CODE),
                f'Unexpected execution at {address:#x}')
        steps += 1
        pcs.add(address)
        stack_low = min(stack_low, emu.reg_read(UC_ARM_REG_SP))

    def write(emu, access, address, size, value, _):
        writes.append((address, size))
        allowed_ram = (SP - 32 <= address and address + size <= SP) or (
            active == 'read_chipid' and destination <= address and address + size <= destination + 6)
        require(allowed_ram or (address, size) in PERIPHERAL_WRITES,
                f'Unexpected write at {address:#x}, size {size}')

    def read(emu, access, address, size, value, _):
        if address >= 0xc0000:
            require((address, size) in PERIPHERAL_READS,
                    f'Unexpected peripheral read at {address:#x}')
        if address == 0xf850c:
            index = int.from_bytes(emu.mem_read(0xf8508, 2), 'little') >> 3
            require(2 <= index < 8, 'OTP read outside chip-ID offsets')
            reads.append(index)
            emu.mem_write(address, fixture[index:index+1])

    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    uc.hook_add(UC_HOOK_MEM_READ, read)
    max_stack = {name: 0 for name in ENTRIES}
    total_steps, cases = 0, 0
    peripheral_writes = set()
    for clock in range(16):
        for fixture in (bytes(range(8)), bytes([0xff, 0, 0x80, 0x55, 0, 0xff, 0x12, 0x34])):
            for destination in (0x20000, 0x28000):
                uc.mem_write(0x20000, b'\xa5' * 0x10000)
                uc.mem_write(0xf8560, clock.to_bytes(4, 'little'))
                uc.mem_write(0xf856c, b'\xff' * 4)
                uc.mem_write(0xc8973, b'\x15')
                reads.clear()
                for active, entry in ENTRIES.items():
                    writes.clear()
                    steps, stack_low = 0, SP
                    uc.reg_write(UC_ARM_REG_SP, SP)
                    uc.reg_write(UC_ARM_REG_LR, STOP | 1)
                    uc.reg_write(UC_ARM_REG_R0, destination)
                    uc.emu_start(entry | 1, STOP + 2, count=100000)
                    require(uc.reg_read(UC_ARM_REG_PC) == STOP, 'Instruction budget exhausted')
                    require(uc.reg_read(UC_ARM_REG_SP) == SP, 'Stack not restored')
                    max_stack[active] = max(max_stack[active], SP - stack_low)
                    total_steps += steps
                    peripheral_writes.update((a, n) for a, n in writes if a >= 0xc0000)
                require(reads == list(range(2, 8)), 'Unexpected OTP read sequence')
                ram = bytes(uc.mem_read(0x20000, 0x10000))
                expected = bytearray(b'\xa5' * 0x10000)
                expected[destination-0x20000:destination-0x20000+6] = fixture[2:8]
                # Stack scratch is allowed; every other byte must be preserved.
                expected[SP-32-0x20000:SP-0x20000] = ram[SP-32-0x20000:SP-0x20000]
                require(ram == expected, 'Unexpected RAM mutation')
                require(uc.mem_read(0xc8973, 1) == b'\x15', 'OTP charge-pump bit not cleared')
                cases += 1
    return {
        'cases': cases, 'clock_selector_values': 16, 'synthetic_otp_patterns': 2,
        'destination_addresses': ['0x20000', '0x28000'],
        'chipid_destination_bytes': 6, 'otp_byte_offsets': list(range(2, 8)),
        'max_isolated_stack_bytes': max_stack,
        'other_ram_writes': False, 'instructions_executed': total_steps,
        'delay_loop_executed': 0xc6 in pcs,
        'peripheral_writes': [{'address': hex(a), 'size': n} for a, n in sorted(peripheral_writes)],
        'limitations': ['Synthetic peripheral values; no live OTP access',
                       'No IRQ nesting, timing, radio execution or other RAM owners modeled',
                       'The final 96 ROM bytes are unavailable; this is not a full-ROM audit'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    args = parser.parse_args()
    data = args.rom.read_bytes()
    require(len(data) == PREFIX_SIZE, 'Expected the exact captured 32,672-byte prefix')
    require(hashlib.sha256(data).hexdigest() == PREFIX_SHA256, 'ROM prefix hash mismatch')
    result = {'mode': 'offline_emulation', 'hardware_access': False,
              'rom_prefix_sha256': PREFIX_SHA256, 'rom_prefix_bytes': len(data),
              'unicorn_version': __version__,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'startup_otp': audit(data)}
    output = Path(__file__).resolve().parents[1] / 'build/stock/arm-rom-analysis.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
