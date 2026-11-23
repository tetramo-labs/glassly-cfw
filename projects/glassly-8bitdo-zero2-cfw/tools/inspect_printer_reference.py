"""Compare pinned YC3121 printer firmware and emulate its BLE packet builder.

Offline only. Printer offsets, handles, limits and ROM semantics are not Zero 2
bindings. IPC submission and time are explicitly stubbed; no radio is emulated.
Requires the ignored reference files pinned in docs/evidence/references.json.
"""
import json
import struct

from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS,
                     UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC, __version__)
from unicorn.arm_const import (UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_R0, UC_ARM_REG_R1)

from firmware_image import ROOT, sha256, load_stock
from radio_config import parse_script
from radio_disasm import decode_blob

BASE, STOP, SP = 0x1010000, 0x1010100, 0x2ff00
INPUT, HANDLE, ACK = 0x28000, 0x20110, 0x20108
SEND, WRAPPER, SUBMIT = 0x101a4a8, 0x101922e, 0x101a15c
NOW, EXPIRED = 0x1018382, 0x1018388
SERVICE, CHARACTERISTIC, REGISTER = 0x1019942, 0x1019992, 0x101a48a


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def emulate_sender(data):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(BASE, (len(data) + 4095) & ~4095, UC_PROT_READ | UC_PROT_EXEC)
    uc.mem_write(BASE, data)
    uc.mem_map(0x20000, 0x10000)
    packets, registration = [], []
    mode = 'immediate'
    ticks = 0
    expected_handle = 0

    def return_value(value):
        uc.reg_write(UC_ARM_REG_R0, value)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def hook(emu, address, size, _):
        nonlocal ticks
        if address in (SERVICE, CHARACTERISTIC):
            registration.append((address, emu.reg_read(UC_ARM_REG_R0),
                                 emu.reg_read(UC_ARM_REG_R1)))
            return_value(expected_handle if address == CHARACTERISTIC else 0)
        elif address == SUBMIT:
            descriptor = bytes(emu.mem_read(emu.reg_read(UC_ARM_REG_R0), 7))
            _, opcode, length, pointer = struct.unpack('<BBBI', descriptor)
            require(opcode == 9, 'Unexpected printer opcode')
            require(int.from_bytes(emu.mem_read(ACK, 4), 'little') == 1,
                    'Wrapper failed to clear stale bit 6 or changed unrelated bits')
            packets.append(bytes(emu.mem_read(pointer, length)))
            if mode == 'immediate':
                emu.mem_write(ACK, struct.pack('<I', 1 | (1 << 6)))
            elif mode == 'wrong_bit':
                emu.mem_write(ACK, struct.pack('<I', 1 | (1 << 9)))
            return_value(0 if mode == 'rejected' else 1)
        elif address == NOW:
            return_value(100)
        elif address == EXPIRED:
            require(emu.reg_read(UC_ARM_REG_R0) == 100 and
                    emu.reg_read(UC_ARM_REG_R1) == 500,
                    'Unexpected timeout arguments')
            ticks += 1
            if mode == 'delayed' and ticks == 2:
                emu.mem_write(ACK, struct.pack('<I', 1 | (1 << 6)))
            return_value(int(ticks >= 3))

    uc.hook_add(UC_HOOK_CODE, hook)

    def call(address, arg0=0, arg1=0):
        uc.reg_write(UC_ARM_REG_SP, SP)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.reg_write(UC_ARM_REG_R0, arg0)
        uc.reg_write(UC_ARM_REG_R1, arg1)
        uc.emu_start(address | 1, STOP, count=20000)
        require(uc.reg_read(UC_ARM_REG_PC) == STOP, 'Instruction budget exhausted')
        require(uc.reg_read(UC_ARM_REG_SP) == SP, 'Stack not restored')
        return uc.reg_read(UC_ARM_REG_R0)

    cases = []
    for expected_handle in (0, 0x2345, 0xffff):
        registration.clear()
        require(call(REGISTER) == 0, 'Unexpected registration return')
        require(registration == [(SERVICE, 0x20112, 17),
                                 (CHARACTERISTIC, 0x20123, 20)],
                'Registration arguments changed')
        require(int.from_bytes(uc.mem_read(HANDLE, 2), 'little') == expected_handle,
                'Characteristic return handle was not saved')
        for length in (0, 1, 8, 20, 253, 254):
            payload = bytes((i * 37 + 11) & 255 for i in range(length))
            uc.mem_write(INPUT, payload or b'\xa5')
            uc.mem_write(ACK, struct.pack('<I', 1 | (1 << 6)))
            packets.clear()
            ticks = 0
            result = call(SEND, INPUT, length)
            expected = [struct.pack('<H', expected_handle) + payload] if length <= 253 else []
            require(packets == expected, 'Handle prefix, copy or length rejection differs')
            require(result == int(length <= 253), 'Unexpected send return')
            require(bytes(uc.mem_read(INPUT, len(payload))) == payload,
                    'Caller payload was modified')
            cases.append(dict(handle=expected_handle, data_length=length,
                              submitted=bool(packets), result=result))

    packets.clear()
    require(call(SEND, 0, 8) == 0 and not packets, 'Null payload was not rejected')
    completion = []
    for mode in ('delayed', 'wrong_bit', 'timeout', 'rejected'):
        packets.clear()
        ticks = 0
        uc.mem_write(ACK, struct.pack('<I', 1 | (1 << 6)))
        result = call(SEND, INPUT, 8)
        require(len(packets) == 1, 'Unexpected submission count')
        require(result == int(mode == 'delayed'), 'Acknowledgement result differs')
        require(ticks == (2 if mode == 'delayed' else 3), 'Unexpected timeout checks')
        completion.append(dict(injected_condition=mode, timeout_checks=ticks, result=result))
    return dict(packet_cases=cases, null_payload_rejected=True, completion_cases=completion,
                registration_return_handle_used=True, stale_ack_bit_cleared=True,
                caller_payload_unchanged=True, acknowledgement_bit=6,
                timeout_argument=500, timeout_units_established=False,
                stubs=[dict(address=SUBMIT, purpose='capture IPC descriptor; inject selected acknowledgement'),
                       dict(address=NOW, purpose='synthetic timestamp'),
                       dict(address=EXPIRED, purpose='bounded synthetic timeout and delayed acknowledgement'),
                       dict(address=SERVICE, purpose='capture service registration arguments'),
                       dict(address=CHARACTERISTIC, purpose='supply synthetic returned handle')],
                radio_delivery_tested=False, zero2_contract_proven=False)


def inspect():
    lock = json.loads((ROOT / 'docs/evidence/references.json').read_text())['niimbot_yc3121']
    images, scripts, metadata = {}, {}, {}
    for name, offset in (('D110_6.10.bin', 0x11ca4), ('B1_2.03.bin', 0x14390)):
        data = (ROOT / 'research/downloads/niimbot-reference' / name).read_bytes()
        require(sha256(data) == lock['files'][name]['sha256'], 'Reference hash mismatch')
        require(data[:4] == bytes.fromhex('49480047') and
                struct.unpack_from('<I', data, 0x128)[0] == BASE + 0x201,
                'Unexpected printer entry/load address')
        records, consumed = parse_script(data, offset)
        images[name], scripts[name] = data, records[0]['payload']
        metadata[name] = dict(sha256=sha256(data), size=len(data), inferred_load_address=BASE,
                              script_offset=offset, script_size=consumed, records=len(records),
                              microcode_size=len(records[0]['payload']),
                              microcode_sha256=sha256(records[0]['payload']))
    require(scripts['D110_6.10.bin'] == scripts['B1_2.03.bin'], 'Printer radio patches differ')
    printer_radio = decode_blob(scripts['D110_6.10.bin'])
    _, _, stock = load_stock()
    stock_radio = parse_script(stock[1], 0xda6e)[0][0]['payload']
    # Common instruction bytes support comparison, not a complete ROM identity.
    common = scripts['D110_6.10.bin'][0x1b5 * 4:0x1b8 * 4]
    require(common == stock_radio[0x280 * 4:0x283 * 4], 'Handle lookup sequence differs')
    require(printer_radio[0x1bf]['target'] == 0x4f01, 'Notification continuation differs')
    anchors = {name: dict(offset=start, size=end-start,
                         sha256=sha256(images['D110_6.10.bin'][start:end]))
               for name, start, end in (
                   ('registration_and_payload_builder', 0xa48a, 0xa4ee),
                   ('opcode09_wrapper', 0x922e, 0x9280),
                   ('ipc_submit', 0xa15c, 0xa186))}
    return dict(kind='offline printer comparison; not a Zero 2 binding',
                tool_sha256={name: sha256((ROOT / 'tools' / name).read_bytes())
                             for name in ('inspect_printer_reference.py', 'radio_config.py',
                                          'radio_disasm.py', 'firmware_image.py')},
                unicorn_version=__version__, references=metadata, d110_anchors=anchors,
                printer_microcode_identical=True,
                printer_microcode_equals_zero2=scripts['D110_6.10.bin'] == stock_radio,
                common_handle_lookup=dict(printer_pc=0x1b5, zero2_pc=0x280,
                                          words=3, sha256=sha256(common)),
                printer_notification_continuation=printer_radio[0x1bf],
                radio_tail_hex=scripts['D110_6.10.bin'][-2:].hex(),
                d110_emulation=emulate_sender(images['D110_6.10.bin']),
                limits=['Different application and radio patch; no matching ROM identity established',
                        'IPC and time stubbed; no FIFO acceptance, CCC semantics or radio delivery proved',
                        'Printer payload length limit and timeout are not Zero 2 limits',
                        'B1 has static comparison only; its ARM routines are not emulated',
                        'No hardware access, patch, full boot or firmware image produced'])


def main():
    report = inspect()
    output = ROOT / 'build/references/niimbot.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('Verified D110 registration-handle reuse, LE16 payload prefix, length boundaries and acknowledgement bit 6.')
    print('Printer radio patches match each other, but differ from Zero 2. CCC and radio delivery remain unproven.')
    print(output)


if __name__ == '__main__':
    main()
