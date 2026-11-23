"""Build the bounded FF13 one-byte echo/connected-idle experimental image.

No unbound button components are included. Uses the stock-cleared image tail
only on the hash-pinned stock/name/BLE baselines, preserving original device
backups. See docs/notification-probe.md for the placement audit and limits.
"""
import json
import struct
import subprocess
from build_ble_probe import build as build_ble
from firmware_image import ROOT, load_stock, load_crypto, unpack, sha256
from startup import reconstruct

TAIL = 0x11c04
IDLE = 0x11cc0
HOOKS = {0x1918: bytes.fromhex('09f0cafc'), 0x3e36: bytes.fromhex('03f00bf8')}


def text_section(elf):
    if elf[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', elf, 18)[0] != 40:
        raise ValueError('Expected ELF32 little-endian ARM object')
    offset = struct.unpack_from('<I', elf, 32)[0]
    size, count, names = struct.unpack_from('<3H', elf, 46)
    if size != 40:
        raise ValueError('Unexpected ELF section size')
    sections = [struct.unpack_from('<10I', elf, offset+i*size) for i in range(count)]
    ns = sections[names]
    strings = elf[ns[4]:ns[4]+ns[5]]
    found = []
    for section in sections:
        name = strings[section[0]:].split(b'\0', 1)[0]
        if section[1] in (4, 9) and section[5]:
            raise ValueError('Unresolved assembler relocation')
        if name == b'.text':
            found.append(elf[section[4]:section[4]+section[5]])
    if len(found) != 1:
        raise ValueError('Expected one text section')
    return found[0]


def build():
    raw, sections, payloads = load_stock()
    _, base, _ = build_ble()
    if base[TAIL:] != bytes(len(base)-TAIL):
        raise ValueError('Expected stock-cleared tail; preserve unknown live baselines')
    # The zero initializer's source is the tail, but it only uses destination
    # and length. Pin its implementation, independently exercised in the audit.
    if base[0xb342:0xb350].hex() != '002001e001c1121f002afbd17047':
        raise ValueError('Zero initializer changed; reaudit placement')
    out = ROOT / 'build/notify-probe'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['clang', '--target=arm-none-eabi', '-mcpu=cortex-m0', '-mthumb', '-c',
                    str(ROOT/'firmware/notify_probe.s'), '-o', str(out/'notify_probe.o')], check=True)
    compiled = text_section((out/'notify_probe.o').read_bytes())
    if not IDLE < len(compiled) <= len(base):
        raise ValueError('Probe exceeds audited tail extent')
    patched = bytearray(base)
    for offset, expected in HOOKS.items():
        if base[offset:offset+4] != expected:
            raise ValueError('Hook is not the audited complete BL instruction')
        patched[offset:offset+4] = compiled[offset:offset+4]
    patched[TAIL:len(compiled)] = compiled[TAIL:]
    patched = bytes(patched)
    if reconstruct(base) != reconstruct(patched):
        raise ValueError('Startup RAM contents changed')
    crypto = load_crypto()
    section = sections[1]
    package = raw[:section['offset']] + crypto.build_section(
        patched, crypto.CIPHERS['yichip'], section['id'], section['addr'],
        section['payload_len'], section['pid'])
    headers, decoded = unpack(package, ['gd32', 'yichip'])
    if headers != sections or decoded != [payloads[0], patched]:
        raise ValueError('Independent decode differs')
    report = dict(kind='Experimental one-byte FF13 notification echo and BLE-connected idle policy; no button stream',
                  package_sha256=sha256(package), plaintext_sha256=sha256(patched),
                  baseline_plaintext_sha256=sha256(base),
                  hooks={hex(k): dict(before=base[k:k+4].hex(), after=patched[k:k+4].hex()) for k in HOOKS},
                  tail_offset=hex(TAIL), tail_used_bytes=len(compiled)-TAIL, idle_offset=hex(IDLE),
                  persistent_ram_bytes=0, echo_local_frame_bytes=48, idle_local_frame_bytes=8,
                  gd32_and_headers_unchanged=True, startup_ram_unchanged=True,
                  assembly_sha256=sha256((ROOT/'firmware/notify_probe.s').read_bytes()),
                  limits=['Radio command-09 handle-prefix semantics are the experiment, not yet proven on Zero 2',
                          'Echo drops requests if radio sleep flag is nonzero or IPC capacity is insufficient',
                          'No transport ACK queue or retry; no custom CCC callback',
                          'Any BLE connection suppresses idle shutdown, even when unsubscribed',
                          'Tail execution and complete device behavior require hardware validation'])
    return package, patched, report


if __name__ == '__main__':
    package, payload, report = build()
    out = ROOT/'build/notify-probe'
    (out/'Zero2-v1.08-notify-probe.dat').write_bytes(package)
    (out/'yichip.bin').write_bytes(payload)
    (out/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
