"""Execute the notification probe and stock dispatcher/IPC/startup offline.

No instruction stubs, device access, interrupts or radio execution. Peripheral
pages are synthetic RAM; asleep sends must exit without touching wake registers.
"""
import itertools
import json
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import *
from build_notify_probe import build, TAIL, IDLE
from firmware_image import ROOT, load_stock, sha256
from startup import reconstruct
from emulate_stock import call, BASE, STOP


def machine(payload):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for address, size in [(BASE, 0x12000), (0x20000, 0x10000), (0xc0000, 0x10000), (0xe000e000, 0x1000)]:
        uc.mem_map(address, size)
    uc.mem_write(BASE, payload)
    for address, data in reconstruct(payload)[1].items():
        uc.mem_write(address, data)
    call(uc, 0x1024044, 0x1029158)
    call(uc, 0x1023f24)
    uc.mem_write(0x2058d, b'\x0a')
    uc.mem_write(0x20034, struct.pack('<I', 0x24000))
    uc.mem_write(0x20648, struct.pack('<H', 0x2345))
    return uc


def verify():
    package, payload, manifest = build()
    stock = load_stock()[2][1]
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    incoming = []
    # Conservative candidate scan includes halfword positions in literal pools.
    for offset in range(0, 0xda00, 2):
        ins = next(md.disasm(stock[offset:offset+4], BASE+offset), None)
        if ins and ins.mnemonic.startswith('b') and ins.op_str.startswith('#0x'):
            target = int(ins.op_str[1:], 16)
            if BASE+TAIL <= target < BASE+len(stock):
                incoming.append(hex(ins.address))
    assert not incoming
    pointers = [i for i in range(0, TAIL, 4) if BASE+TAIL <= struct.unpack_from('<I', stock, i)[0] < BASE+len(stock)]
    assert pointers == [0x1183c], pointers  # Zero initializer's unused source.
    uc = machine(payload)
    tail_reads = []
    def read_tail(emu, access, address, size, value, _):
        tail_reads.append(address)
    hook = uc.hook_add(UC_HOOK_MEM_READ, read_tail, begin=BASE+TAIL, end=BASE+len(payload)-1)
    uc.emu_start(BASE+0x201, BASE+0xcf48, count=500000)
    assert uc.reg_read(UC_ARM_REG_PC) == BASE+0xcf48
    for address, data in reconstruct(stock)[1].items():
        assert bytes(uc.mem_read(address, len(data))) == data
    assert not tail_reads
    uc.hook_del(hook)

    uc = machine(payload)
    minimum_sp = [0x2ff00]
    radio_writes = []
    def observe(emu, address, size, _):
        minimum_sp[0] = min(minimum_sp[0], emu.reg_read(UC_ARM_REG_SP))
    def write(emu, access, address, size, value, _):
        if 0xc0000 <= address < 0xd0000:
            assert 0xc6000 <= address < 0xc6020, 'Unexpected wake/radio register write'
            assert emu.reg_read(UC_ARM_REG_PRIMASK) == 1, 'IPC copy not serialized'
            radio_writes.append((address, size))
    uc.hook_add(UC_HOOK_CODE, observe)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)

    def event(value, matched, read, cursor, sleep, mask):
        packet = b'\x02\x08' + bytes([len(value)]) + value
        uc.mem_write(0x25000, packet)
        uc.mem_write(0x20f8c, struct.pack('<5I', 0x25000, 512, len(packet), 0, len(packet)))
        uc.mem_write(0x20020, struct.pack('<I', 1))
        uc.mem_write(0x24000, struct.pack('<4H', 0x6000, 0x601f, 0x6000+read, 0x6000+cursor))
        uc.mem_write(0xc6000, bytes([0xa5])*32)
        uc.mem_write(0x20038, bytes([sleep]))
        uc.mem_write(0x20198, struct.pack('<I', 12345))
        uc.reg_write(UC_ARM_REG_PRIMASK, mask)
        radio_writes.clear()
        call(uc, 0x101986c)
        assert uc.reg_read(UC_ARM_REG_PRIMASK) == mask
        assert int.from_bytes(uc.mem_read(0x20f94, 4), 'little') == 0
        available = (read-cursor) % 32 or 32
        sends = matched and len(value) == 3 and sleep == 0 and available > 6
        expected = bytearray([0xa5]*32)
        end = cursor
        if sends:
            for byte in b'\x01\x09\x03'+value:
                expected[end] = byte
                end = (end+1) % 32
        assert bytes(uc.mem_read(0xc6000, 32)) == expected
        assert int.from_bytes(uc.mem_read(0x24006, 2), 'little') == 0x6000+end
        assert bool(radio_writes) == sends
        assert int.from_bytes(uc.mem_read(0x20198, 4), 'little') == (0 if matched else 12345)

    cases = 0
    for read, cursor, mask in itertools.product(range(32), range(32), (0, 1)):
        event(bytes.fromhex('4523a7'), True, read, cursor, 0, mask)
        cases += 1
    for sleep, mask, value in itertools.product((0, 1, 2), (0, 1),
            (b'', b'\x45', b'\x45\x23', b'\x45\x23\xa7', b'\x45\x23ab', b'\x46\x23\xa7', b'\x45\x23'+bytes(253))):
        event(value, len(value)>=2 and value[:2]==b'\x45\x23', 0, 0, sleep, mask)
        cases += 1
    # Concrete bytes used by the host echo test.
    for value in (0x31, 0xa5, 0, 255):
        event(b'\x45\x23'+bytes([value]), True, 0, 29, 0, 0)
        cases += 1
    for handle in (0, 1, 0x45, 0xffff):
        uc.mem_write(0x20648, struct.pack('<H', handle))
        event(struct.pack('<HB', handle, 0x5a), True, 0, 29, 0, 0)
        cases += 1
    idle = []
    for state in (0, 1, 2, 3):
        call(uc, 0x1023a5c)  # Arm actual watchdog/list state.
        uc.mem_write(0x20682, bytes([state]))
        uc.mem_write(0x20198, struct.pack('<I', 123))
        call(uc, BASE+IDLE)
        count = int.from_bytes(uc.mem_read(0x20198, 4), 'little')
        active = uc.mem_read(0x21ed0, 1)[0]
        assert count == (0 if state == 2 else 124)
        assert bool(active) == (state != 2)
        idle.append(dict(ble_state=state, idle_count=count, watchdog_active=bool(active)))
    return dict(kind='Offline probe plus actual stock startup, dispatcher, FIFO, timer and IPC code',
                hardware_accessed=False, instruction_stubs=[], package_sha256=sha256(package),
                plaintext_sha256=sha256(payload), event_cases=cases, idle_cases=idle,
                startup_matches_stock=True, startup_reads_tail=False,
                conservative_direct_branch_candidates_into_stock_tail=incoming,
                aligned_stock_tail_pointer_offsets=[hex(i) for i in pointers],
                maximum_observed_dispatcher_and_callees_stack_bytes=0x2ff00-minimum_sp[0],
                irq_mask_restored=True, ipc_exact_fill_rejected=True, sleeping_sends_skipped=True,
                limits=['Synthetic IRQ registers and ring; no interrupt execution or radio consumer',
                        'Measured isolated stack excludes caller/main/exception nesting',
                        'Static reference search cannot exclude arbitrary computed/OEM-ROM references',
                        'No CCC enforcement, radio acknowledgement or on-air notification is simulated'])


if __name__ == '__main__':
    report = verify()
    (ROOT/'build/notify-probe/emulation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
