"""Verify pinned vendor updater selection and read-query blocks offline.

Runs selected x86 instructions in Unicorn with explicit transport stubs. No Windows runtime,
file APIs, USB enumeration, callbacks, updater initialization or flashing run.
"""
import hashlib
import io
import json
import struct
import zipfile

from firmware_image import ROOT, load_stock


def verify():
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
    from unicorn import __version__ as unicorn_version
    from unicorn.x86_const import (UC_X86_REG_EBP, UC_X86_REG_EDI, UC_X86_REG_EIP,
                                  UC_X86_REG_ESP, UC_X86_REG_EAX)

    lock = json.loads((ROOT / 'sources.lock.json').read_text())['updater_research']
    raw = (ROOT / lock['path']).read_bytes()
    if len(raw) != lock['size'] or hashlib.sha256(raw).hexdigest() != lock['sha256']:
        raise ValueError('Updater ZIP differs from pinned research copy')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = {}
        for name, pin in lock['members'].items():
            blob = archive.read(name)
            if len(blob) != pin['size'] or hashlib.sha256(blob).hexdigest() != pin['sha256']:
                raise ValueError('Updater member differs from pin')
            members[name.rsplit('/', 1)[-1]] = blob
    dll = members['8BitDoFirmwareUpdaterTools.dll']
    # Exact pinned PE32 .text mapping, confirmed from its section headers.
    pe = struct.unpack_from('<I', dll, 0x3c)[0]
    optional_size = struct.unpack_from('<H', dll, pe + 20)[0]
    section = pe + 24 + optional_size
    if (dll[section:section+8] != b'.text\0\0\0' or
            struct.unpack_from('<III', dll, section+12) != (0x1000, 0x178c00, 0x400) or
            struct.unpack_from('<I', dll, pe+24+28)[0] != 0x10000000):
        raise ValueError('Unsupported updater mapping')
    stock, sections, _ = load_stock()
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    uc.mem_map(0x10001000, 0x179000)
    uc.mem_write(0x10001000, dll[0x400:0x179000])
    uc.mem_protect(0x10001000, 0x179000, UC_PROT_READ | UC_PROT_EXEC)
    uc.mem_map(0x20000000, 0x1000)  # Synthetic stack locals, not target RAM.
    frame = 0x20000800
    uc.reg_write(UC_X86_REG_EBP, frame)
    uc.hook_add(UC_HOOK_CODE, lambda emu, *_: emu.emu_stop(), begin=0x10007379, end=0x10007379)
    results, comparisons = [], 0
    for pid, expected in ((0, 0), (0x9018, 0xc81c), (0xffffffff, None)):
        offset, selected = 0, None
        for s in sections:
            if offset != s['offset']:
                raise AssertionError('Native header advance disagrees with strict container parser')
            uc.mem_write(frame-0x58, stock[offset:offset+28])
            uc.mem_write(frame+12, struct.pack('<I', pid))
            uc.reg_write(UC_X86_REG_EDI, offset)
            uc.emu_start(0x10007265, 0x10007279, count=16)
            pc, new_offset = uc.reg_read(UC_X86_REG_EIP), uc.reg_read(UC_X86_REG_EDI)
            comparisons += 1
            if pc == 0x10007379:
                if new_offset != offset:
                    raise AssertionError('Match changed offset')
                selected = offset
                break
            if pc != 0x10007279 or new_offset != offset + 28 + s['payload_len']:
                raise AssertionError('Unexpected selection block boundary or next offset')
            offset = new_offset
        if selected != expected:
            raise AssertionError('Selected section differs')
        results.append(dict(header_pid=pid, selected_offset=selected))
    uc.mem_map(0x101d4000, 0x2000)
    uc.mem_map(0x101cb000, 0x1000)
    gates = []
    for vid, pid, expected in ((0x2dc8, 0x9018, 0), (0x0483, 0x5760, 0),
                               (0x2dc8, 0x3208, 1), (0x2dc8, 0x3002, 1)):
        uc.reg_write(UC_X86_REG_EBP, frame)
        uc.mem_write(frame-0x28, struct.pack('<HH', vid, pid))
        uc.mem_write(0x101d49bc, struct.pack('<I', 99))
        uc.emu_start(0x10004f4e, 0x10004fa2, count=100)
        flag = int.from_bytes(uc.mem_read(0x101d49bc, 4), 'little')
        if uc.reg_read(UC_X86_REG_EIP) != 0x10004fa2 or flag != expected:
            raise AssertionError('Unexpected boot-version protocol selection')
        gates.append(dict(vid=vid, pid=pid, address_read_version_path=bool(flag)))

    # Execute the actual packet constructor for the vendor's four-byte version
    # read. The memory initializer, transport and stack-cookie check are stubbed;
    # no Windows API or hardware code executes. Packet packing and CRC run stock.
    packets = []
    def read32(address):
        return int.from_bytes(uc.mem_read(address, 4), 'little')

    def packet_hook(emu, address, size, _):
        if address not in (0x10149e30, 0x100053a0, 0x101477e2):
            return
        sp = emu.reg_read(UC_X86_REG_ESP)
        ret = read32(sp)
        cleanup = 4
        if address == 0x10149e30:
            dest, byte, length = (read32(sp + i) for i in (4, 8, 12))
            emu.mem_write(dest, bytes([byte & 255]) * length)
            emu.reg_write(UC_X86_REG_EAX, dest)
        elif address == 0x100053a0:
            dest, length = read32(sp+4), read32(sp+8)
            packets.append(dict(logical_length=length,
                                hid_output_hex=bytes(emu.mem_read(dest, 64)).hex()))
            emu.reg_write(UC_X86_REG_EAX, 1)
            cleanup += 8
        emu.reg_write(UC_X86_REG_ESP, sp + cleanup)
        emu.reg_write(UC_X86_REG_EIP, ret)

    hook = uc.hook_add(UC_HOOK_CODE, packet_hook)
    stop, sp = 0x10001000, 0x20000400
    uc.mem_write(0x101d5a00, struct.pack('<I', 0x9018))
    uc.mem_write(sp, struct.pack('<7I', stop, 0, 4, 0x08014034, 4, 5, 0))
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(0x100091c0, stop, count=10000)
    if uc.reg_read(UC_X86_REG_EIP) != stop or uc.reg_read(UC_X86_REG_ESP) != sp + 28 or len(packets) != 1:
        raise AssertionError('Version-read constructor did not return cleanly')
    version_packets = list(packets)
    packets.clear()
    uc.mem_write(sp, struct.pack('<7I', stop, 0, 32, 0x01018000, 32, 5, 0))
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(0x100091c0, stop, count=10000)
    if uc.reg_read(UC_X86_REG_EIP) != stop or len(packets) != 1:
        raise AssertionError('Application-entry read constructor failed')
    application_packets = list(packets)
    packets.clear()
    uc.reg_write(UC_X86_REG_EBP, frame)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(0x1000bef0, 0x1000bf72, count=10000)
    uc.hook_del(hook)
    if uc.reg_read(UC_X86_REG_EIP) != 0x1000bf72 or len(packets) != 1:
        raise AssertionError('Product identification constructor failed')
    anchors = {
        'pid_9018_dispatches_header_scanner': (0x1000795f, 0x10007979),
        'seek_read_28_byte_header': (0x10007248, 0x10007265),
        'compare_header_pid_and_advance': (0x10007265, 0x10007279),
        'seek_selected_header': (0x10007ac8, 0x10007af1),
        'boot_version_protocol_gate': (0x10004f4e, 0x10004fa2),
        'address_read_packet_constructor': (0x100091c0, 0x1000928a),
        'address_read_response_validation': (0x10009290, 0x10009325),
        'boot_version_four_byte_read': (0x1000938e, 0x10009415),
        'product_identity_query': (0x1000bef0, 0x1000bfaa),
    }
    return {
        'kind': 'Isolated native selection and read-query construction; updater application never launched',
        'unicorn_version': unicorn_version,
        'tool_sha256': hashlib.sha256((ROOT / 'tools/inspect_updater.py').read_bytes()).hexdigest(),
        'updater_zip_sha256': lock['sha256'],
        'dll_sha256': hashlib.sha256(dll).hexdigest(),
        'stock_sha256': hashlib.sha256(stock).hexdigest(),
        'anchors': {name: dict(virtual_address=a, size=b-a,
                              file_offset=a-0x10001000+0x400,
                              sha256=hashlib.sha256(dll[a-0x10000c00:b-0x10000c00]).hexdigest())
                    for name, (a, b) in anchors.items()},
        'native_comparisons': comparisons, 'cases': results,
        'boot_version_protocol_cases': gates,
        'vendor_version_read': {'address': 0x08014034, 'size': 4,
                                'constructor_packets': version_packets,
                                'stubs': ['memset', 'WriteHid capture', 'stack-cookie check'],
                                'hardware_executed': False,
                                'limit': 'Proves host packet construction, not target memory mapping or readback support'},
        'product_identity_query': {'constructor_packets': packets, 'expected_response_command': 8,
                                   'response_product_word_offset': 18, 'hardware_executed': False},
        'application_entry_read': {'address': 0x01018000, 'size': 32,
                                   'constructor_packets': application_packets, 'hardware_executed': False,
                                   'address_source': 'Pinned Zero 2 section-1 load address'},
        'finding': 'When the updater takes its PID 0x9018 path, header PID matching selects the v1.08 Yichip section at 0xc81c',
        'limits': ['This offline tool observes no device identity or silicon; live findings are separate',
                   'GD32 hardware selection path unresolved; PID zero case tests scanner arithmetic only',
                   'Whole updater, malformed-file handling, Windows APIs and flashing were not executed'],
    }


if __name__ == '__main__':
    report = verify()
    target = ROOT / 'build/stock/updater-selection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print('Verified 5 native header comparisons across 3 scanner cases; PID 0x9018 selects section 1.')
    print('Verified boot-version protocol gate and captured the vendor four-byte read request in virtual memory.')
    print('This tool launches no updater and accesses no hardware; live evidence is recorded separately.')
