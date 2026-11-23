"""Build a one-instruction BLE-visibility experiment on the verified name probe.

This is a complete experimental image, not a button-stream implementation.
Related Yichip sources identify command 02 bit 2 as BLE advertising enable;
its effect on this Zero 2 must be measured on hardware.
"""
import json
from build_name_probe import build as build_name
from firmware_image import ROOT, load_stock, load_crypto, unpack, sha256
from startup import reconstruct

OFFSET = 0x2310
OLD = bytes.fromhex('0026')  # movs r6, #0, inside 0x0101a304
NEW = bytes.fromhex('0126')  # movs r6, #1


def build():
    raw, sections, payloads = load_stock()
    _, base, _ = build_name()
    if base[OFFSET:OFFSET+2] != OLD or base[0x2304:0x2314].hex() != 'feb504460d4616460020009000260125':
        raise ValueError('Visibility routine does not match audited v1.08 instructions')
    patched = base[:OFFSET] + NEW + base[OFFSET+2:]
    crypto = load_crypto()
    section = sections[1]
    package = raw[:section['offset']] + crypto.build_section(
        patched, crypto.CIPHERS['yichip'], section['id'], section['addr'],
        section['payload_len'], section['pid'])
    headers, decoded = unpack(package, ['gd32', 'yichip'])
    if headers != sections or decoded != [payloads[0], patched]:
        raise ValueError('Independent package decode differs from intended changes')
    differences = [i for i, (a, b) in enumerate(zip(base, patched)) if a != b]
    if differences != [OFFSET] or reconstruct(base) != reconstruct(patched):
        raise ValueError('Unexpected change outside immediate operand')
    report = {
        'kind': 'Experimental BLE visibility image; no custom GATT button stream',
        'stock_package_sha256': sha256(raw), 'package_sha256': sha256(package),
        'plaintext_sha256': sha256(patched), 'name_probe_plaintext_sha256': sha256(base),
        'instruction_address': '0x0101a310', 'old_instruction': OLD.hex(), 'new_instruction': NEW.hex(),
        'changed_offsets_from_name_probe': differences,
        'effect_verified_offline': 'Command 02 payload adds bit 2; other bits and length preserved',
        'hypothesis': 'Related YC1021/YC1121 protocols assign bit 2 to BLE advertising',
        'gd32_section_and_both_headers_unchanged': True,
        'startup_ram_layout_stack_and_instruction_size_unchanged': True,
        'limits': ['No live advertising or GATT result yet',
                   'Forces the flag at every call to this wrapper, including stop-visibility requests',
                   'Sleep, power use, coexistence and reconnect require hardware checks',
                   'No new code placement, RAM state, GPIO hook or stream component'],
    }
    return package, patched, report


if __name__ == '__main__':
    package, payload, report = build()
    out = ROOT / 'build/ble-probe'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'Zero2-v1.08-ble-probe.dat').write_bytes(package)
    (out / 'yichip.bin').write_bytes(payload)
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
