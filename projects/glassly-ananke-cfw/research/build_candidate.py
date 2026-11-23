#!/usr/bin/env python3
"""Build an OFFLINE EXPERIMENTAL image; contains no transport or flash writer.

The existing app file's size and every partition offset stay fixed. The shorter
V0900 app plus payload fit within it. The device key is read locally and never
written to a report. Passing these checks does not authorize installation.
"""
import binascii
import json
import re
from pathlib import Path
import struct
import sys

from inspect_ananke import APP_SHA as OEM_SHA, inspect as inspect_oem, sha, require
from inspect_installed import BACKUP, EXTRACTED, FLASH_SHA, ROOT, entry, inspect

TOOLS = ROOT.parent/'glassly-mini-gamepad/research/jl-misctools/firmware'
sys.path.insert(0, str(TOOLS))

ORIGIN = 0x1e00120
BASE = 0x3020
APP_OFFSET = 0x120
APP_BYTES = 343208
AREA_BYTES = 0x5415c
PAYLOAD_ADDRESS = 0x1e52c38
OUT = ROOT/'research/cfw-candidate'
ELF = ROOT/'research/pi32v2-analysis/ananke-cfw.elf'

BLOCKERS = [
    'Application-independent recovery entry and sector restore are not demonstrated.',
    'Worst-case stack usage and live critical-section latency remain unmeasured.',
    'HID coexistence, standby/wake and real iPhone background/locked delivery remain untested.',
]



def read_elf(blob):
    require(len(blob) >= 52 and blob[:7] == b'\x7fELF\x01\x01\x01', 'Not ELF32 little endian')
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', blob)
    require(h[1:3] == (2, 241) and h[11] == 40, 'Unexpected ELF type/machine/section size')
    shoff, count, string_index = h[6], h[12], h[13]
    require(0 < count < 100 and shoff + count * 40 <= len(blob) and string_index < count,
            'Truncated ELF section table')
    sections = [struct.unpack_from('<10I', blob, shoff + i * 40) for i in range(count)]
    def data(section):
        start, size = section[4:6]
        require(start + size <= len(blob), 'Truncated ELF section')
        return blob[start:start+size]
    def name(table, offset):
        require(offset < len(table) and b'\0' in table[offset:], 'Bad ELF string offset')
        return table[offset:table.index(b'\0', offset)].decode('ascii')
    names = data(sections[string_index])
    allocated = [s for s in sections if s[2] & 2 and s[5]]
    require(len(allocated) == 1 and name(names, allocated[0][0]) == '.text' and
            allocated[0][3] == PAYLOAD_ADDRESS and allocated[0][2] == 6,
            'Unexpected allocated payload sections or base')
    require(not any(s[1] in (4, 9) and s[5] for s in sections), 'Unresolved relocations')
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        require(section[9] == 16 and section[6] < len(sections), 'Invalid symbol table')
        strings = data(sections[section[6]])
        for off in range(0, section[5], 16):
            n, value, size, info, other, index = struct.unpack_from('<IIIBBH', data(section), off)
            symbol = name(strings, n)
            require(not symbol or index != 0, 'Unresolved symbol: ' + symbol)
            if symbol:
                symbols[symbol] = value
    expected = dict(ag_state=0xc280, stock_connection=0x7920, stock_keys=0x79e4,
                    stock_scan=0x20018c6, stock_ccc_get=0x1e169d8,
                    stock_ccc_set=0x1e17178, stock_ccc_clear=0x1e1704e,
                    stock_att_queue=0x1e16af4, stock_critical_enter=0x200351c,
                    stock_critical_exit=0x2003538, stock_bt_wake=0x1e16678)
    require(all(symbols.get(k) == v for k, v in expected.items()), 'Binding symbol mismatch')
    payload = data(allocated[0])
    for symbol in ('ag_scan_hook', 'ag_ccc_set_hook', 'ag_ccc_clear_hook'):
        require(PAYLOAD_ADDRESS <= symbols.get(symbol, 0) < PAYLOAD_ADDRESS + len(payload)
                and symbols[symbol] % 2 == 0, 'Hook outside payload')
    require(h[4] == symbols['ag_scan_hook'], 'Unexpected ELF entry')
    return payload, symbols


def call_target(address, instruction):
    require(len(instruction) == 4, 'Expected a four-byte call')
    hi, lo = struct.unpack('<HH', instruction)
    require(hi & 0xffc0 == 0xea80, 'Not a pi32v2 long call')
    words = ((hi & 0x3f) << 16) | lo
    if words & 0x200000:
        words -= 0x400000
    return (address + 4 + words * 2) & 0x1ffffff


def encode_call(address, target):
    delta = target - address - 4
    require(delta % 2 == 0 and -(1 << 22) <= delta < (1 << 22), 'Call out of range/alignment')
    words = (delta // 2) & 0x3fffff
    result = struct.pack('<HH', 0xea80 | (words >> 16), words & 0xffff)
    require(call_target(address, result) == target, 'Call encoding failed')
    return result


def audit_listing(payload, symbols, listing):
    """Cross-check every linked instruction against the official disassembler.

    This is a static branch/coverage audit, not CPU emulation or a stack proof.
    """
    instructions = {}
    for line in listing.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*(.*)$', line)
        if not match:
            continue
        address, raw, assembly = int(match[1], 16), bytes.fromhex(match[2]), match[3]
        require(address not in instructions, 'Duplicate instruction address')
        require('<unknown instruction>' not in assembly, 'Unknown payload instruction')
        instructions[address] = (raw, assembly)
    cursor = PAYLOAD_ADDRESS
    for address, (raw, assembly) in sorted(instructions.items()):
        require(address == cursor and len(raw) in (2, 4, 6), 'Disassembly coverage gap')
        offset = address - PAYLOAD_ADDRESS
        require(payload[offset:offset+len(raw)] == raw, 'Stale disassembly or changed payload')
        cursor += len(raw)
    require(cursor == PAYLOAD_ADDRESS + len(payload), 'Incomplete disassembly')
    external = {symbols[k] & 0x1ffffff for k in
                ('stock_scan', 'stock_ccc_get', 'stock_ccc_set', 'stock_ccc_clear',
                 'stock_att_queue', 'stock_critical_enter', 'stock_critical_exit', 'stock_bt_wake')}
    branches = []
    for address, (raw, assembly) in instructions.items():
        branch = re.search(r'\b(call|goto) (-?\d+)', assembly)
        if branch:
            target = (address + len(raw) + int(branch[2])) & 0x1ffffff
            tail_exit = (branch[1] == 'goto' and target == (symbols['stock_critical_exit'] & 0x1ffffff)
                         and symbols['ag_ccc_set_hook'] <= address < symbols['ag_ccc_clear_hook']
                         and instructions.get(address-2, (b'',))[0] == bytes.fromhex('3604'))
            require(target in instructions or (branch[1] == 'call' and target in external) or tail_exit,
                    'Branch to unknown target or instruction interior')
            if branch[1] == 'call' and len(raw) == 4:
                require(call_target(address, raw) == target, 'Compiler/disassembler branch disagreement')
            branches.append(dict(address=address, operation=branch[1], target=target))
        elif re.search(r'\b(call|goto) r\d+', assembly):
            require(assembly.strip().startswith('call r6') and address >= symbols['ag_stream_poll'],
                    'Unexpected indirect branch')
    return dict(instruction_count=len(instructions), branches=branches,
                all_payload_bytes_disassembled=True, direct_targets_on_instruction_boundaries=True,
                indirect_call='ag_stream_poll callback; ag_scan_hook supplies send_packet',
                stack_proven=False)


def patch_application(oem, payload, symbols):
    inspect_oem(oem)
    require(ORIGIN + len(oem) == PAYLOAD_ADDRESS and 0 < len(payload) <= APP_BYTES - len(oem),
            'Payload exceeds existing application allocation')
    patched = bytearray(oem + payload)
    patches = []
    def patch(address, before, after, purpose):
        offset = address - ORIGIN
        require(len(before) == len(after) and patched[offset:offset+len(before)] == before,
                'Patch preimage mismatch: ' + purpose)
        patched[offset:offset+len(before)] = after
        patches.append(dict(address=address, file_offset=offset, before=before.hex(),
                            after=after.hex(), purpose=purpose))
    def immediate(address, register, old, new, purpose):
        patch(address, struct.pack('<HI', 0xffc0 | register, old),
              struct.pack('<HI', 0xffc0 | register, new), purpose)
    immediate(0x1e0016c, 3, 0x2d200, 0xc280, 'Secondary BSS destination: reserved heap page')
    immediate(0x1e00174, 2, 0, 128, 'Zero exactly one reserved page at startup')
    immediate(0x1e23532, 6, 0xc270, 0xc300, 'Reserve one 128-byte aligned heap page')
    immediate(0x1e23944, 1, 0x1e4c54c, PAYLOAD_ADDRESS + len(payload),
              'Extend flash execution upper limit to include payload')
    # This immediate is paired with the following store; retain its width and
    # parallel marker. RAM 0x4daa forwards r3 as r2 to 0x4be8, which allocates
    # r2 << 2 bytes. Add 128 words (512 bytes) to the input task's 4096 bytes.
    patch(0x1e37a5c, bytes.fromhex('43f00004'), bytes.fromhex('43f08004'),
          'Input task stack: 1024 to 1152 words')
    hooks = [(0x1e3b5b6, 0x18c6, 'ag_scan_hook'),
             (0x1e33854, 0x1e17178, 'ag_ccc_set_hook'),
             (0x1e32618, 0x1e1704e, 'ag_ccc_clear_hook')]
    for address, original_target, symbol in hooks:
        before = oem[address-ORIGIN:address-ORIGIN+4]
        require(call_target(address, before) == original_target, 'Original hook target mismatch')
        patch(address, before, encode_call(address, symbols[symbol]), symbol)
    # The RAM relocation instructions and complete copied source remain exact.
    require(patched[0x62:0x76] == oem[0x62:0x76], 'RAM relocation changed')
    require(patched[0x4c42c:0x52af0] == oem[0x4c42c:0x52af0], 'RAM initializer changed')
    allowed = {i for p in patches for i in range(p['file_offset'], p['file_offset']+len(bytes.fromhex(p['after'])))}
    require(all(a == b or i in allowed for i, (a, b) in enumerate(zip(oem, patched))),
            'Unexpected OEM byte mutation')
    patched.extend(b'\xff' * (APP_BYTES - len(patched)))
    return bytes(patched), patches


def crc(data):
    return binascii.crc_hqx(data, 0)


def package(original, replacement, key):
    from jltech.cipher import jl_sfc_cipher
    require(len(original) == 0x100000 and sha(original) == FLASH_SHA, 'Wrong original flash')
    require(len(replacement) == APP_BYTES, 'Replacement must retain installed file size')
    decoded = bytearray(original)
    jl_sfc_cipher(decoded, BASE, AREA_BYTES, BASE, key)
    area, app, cfg = (entry(decoded, BASE + off) for off in (0, 32, 64))
    require((area['name'], area['encoded_offset'], area['size'], area['index']) ==
            ('app_area_head', ORIGIN, AREA_BYTES, 1), 'Unexpected active area')
    require((app['name'], app['encoded_offset'], app['size']) ==
            ('app.bin', APP_OFFSET, APP_BYTES), 'Unexpected installed app')
    require((cfg['name'], cfg['encoded_offset'], cfg['size']) ==
            ('cfg_tool.bin', APP_OFFSET + APP_BYTES, 916), 'Unexpected config allocation')
    require(cfg['encoded_offset'] + cfg['size'] == AREA_BYTES, 'Unexpected trailing area data')
    require(crc(decoded[BASE+32:BASE+AREA_BYTES]) == area['data_crc16'], 'Area checksum mismatch')
    require(crc(decoded[BASE+APP_OFFSET:BASE+APP_OFFSET+APP_BYTES]) == app['data_crc16'],
            'Installed app checksum mismatch')
    require(crc(decoded[BASE+cfg['encoded_offset']:BASE+AREA_BYTES]) == cfg['data_crc16'],
            'Config checksum mismatch')
    before = bytes(decoded)
    decoded[BASE+APP_OFFSET:BASE+APP_OFFSET+APP_BYTES] = replacement
    for off, checksum in ((BASE+32, crc(replacement)), (BASE, None)):
        if checksum is None:
            checksum = crc(decoded[BASE+32:BASE+AREA_BYTES])
        struct.pack_into('<H', decoded, off+2, checksum)
        struct.pack_into('<H', decoded, off, crc(decoded[off+2:off+32]))
    require(decoded[BASE+64:BASE+APP_OFFSET] == before[BASE+64:BASE+APP_OFFSET],
            'Config/reserved partition records changed')
    require(decoded[BASE+APP_OFFSET+APP_BYTES:] == before[BASE+APP_OFFSET+APP_BYTES:],
            'Config payload or later storage changed')
    jl_sfc_cipher(decoded, BASE, AREA_BYTES, BASE, key)
    result = bytes(decoded)
    require(result[:BASE] == original[:BASE] and result[BASE+AREA_BYTES:] == original[BASE+AREA_BYTES:],
            'Bytes outside active used area changed')
    check = bytearray(result)
    jl_sfc_cipher(check, BASE, AREA_BYTES, BASE, key)
    require(check[BASE+APP_OFFSET:BASE+APP_OFFSET+APP_BYTES] == replacement, 'Payload roundtrip failed')
    for off in (BASE, BASE+32, BASE+64):
        entry(check, off)
    require(crc(check[BASE+32:BASE+AREA_BYTES]) == entry(check, BASE)['data_crc16'],
            'Rebuilt area checksum mismatch')
    return result


def main():
    import yaml
    inspect()
    original = (BACKUP/'flash-pass1.bin').read_bytes()
    installed = (EXTRACTED/'files/app.bin').read_bytes()
    key = yaml.safe_load((EXTRACTED/'jlfw.yaml').read_text())['chip-key']
    require(package(original, installed, key) == original, 'Original full-image roundtrip failed')
    oem = (ROOT/'research/oem-unpacked/IG05_V0900.ufw/files/app.bin').read_bytes()
    elf = ELF.read_bytes()
    payload, symbols = read_elf(elf)
    audit = audit_listing(payload, symbols, (ELF.with_suffix('.asm')).read_text())
    app, patches = patch_application(oem, payload, symbols)
    image = package(original, app, key)
    sectors = [i for i in range(0, len(image), 4096) if image[i:i+4096] != original[i:i+4096]]
    changes = [i for i, (a, b) in enumerate(zip(original, image)) if a != b]
    inputs = ['firmware/ananke_v0900.c', 'firmware/ananke_v0900.ld', 'firmware/button_stream.c',
              'firmware/button_stream.h', 'research/build_candidate.py', 'scripts/build-candidate.sh',
              'scripts/pi32v2-tool.sh']
    report = dict(status='EXPERIMENTAL IMAGE — REQUIRES EXPLICIT RISK ACCEPTANCE',
                  installable=False, flashed=False, blockers=BLOCKERS,
                  target='IINE Mini Retro Ananke Gen 2 / Purple, Gray, Cream Yellow / HID BLE',
                  base_release='IG05_V0900', original_flash_sha256=FLASH_SHA,
                  oem_application_sha256=OEM_SHA, original_roundtrip_identical=True,
                  candidate_sha256=sha(image), application_sha256=sha(app),
                  payload_sha256=sha(payload), elf_sha256=sha(elf), payload_bytes=len(payload),
                  payload_address=PAYLOAD_ADDRESS, payload_end_exclusive=PAYLOAD_ADDRESS+len(payload),
                  application_bytes=len(app), flash_bytes=len(image), patches=patches, code_audit=audit,
                  symbols=symbols, state=dict(address=0xc280, reserved_bytes=128,
                                             binding_bytes=96, initialized_by='secondary BSS clear'),
                  input_task_stack=dict(before_words=1024, after_words=1152, word_bytes=4,
                                        before_bytes=4096, after_bytes=4608,
                                        allocation_trace=[0x1e37a5c, 0x4daa, 0x4be8, 0x4bf2]),
                  changed_sectors_4096=sectors, first_changed_byte=min(changes), last_changed_byte=max(changes),
                  preservation='Every byte outside the original used application area; all partition offsets and sizes; cfg_tool payload; stock RAM initializer',
                  protocol=dict(service='AE40', characteristic='AE42', value_handle=0x54,
                                ccc_handle=0x55, bytes=8, format='47 02 sequence flags keys32LE'),
                  sources={p:sha((ROOT/p).read_bytes()) for p in inputs},
                  cipher_source_sha256=sha((TOOLS/'jltech/cipher.py').read_bytes()))
    OUT.mkdir(exist_ok=True)
    (OUT/'ananke-v0900-gatt-experimental.bin').write_bytes(image)
    (OUT/'application-experimental.bin').write_bytes(app)
    (OUT/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status', 'installable', 'payload_bytes', 'candidate_sha256')}, indent=2))
    print('Local candidate:', OUT/'ananke-v0900-gatt-experimental.bin')


if __name__ == '__main__':
    main()
