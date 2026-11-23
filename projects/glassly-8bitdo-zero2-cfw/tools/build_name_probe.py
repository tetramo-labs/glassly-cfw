"""Build a pinned, same-length identity-string probe; no device access.

This deliberately does not link the unbound GATT components. The model name is
shared data, so Bluetooth naming may change too; USB is the verification target.
"""
import json
from firmware_image import ROOT, load_stock, load_crypto, unpack, sha256
from startup import reconstruct

OFFSET = 0x117cc
OLD = b'8BitDo Zero 2 gamepad'
NEW = b'Glassly Zero 2 test01'


def build():
    raw, sections, payloads = load_stock()
    original = payloads[1]
    if len(OLD) != len(NEW) or original[OFFSET:OFFSET+len(OLD)+1] != OLD + b'\0':
        raise ValueError('Unexpected stock name or replacement length')
    _, regions, _ = reconstruct(original)
    if int.from_bytes(regions[0x20000][0x6a0:0x6a4], 'little') != 0x1018000 + OFFSET:
        raise ValueError('USB product-name pointer no longer references the audited string')
    patched = original[:OFFSET] + NEW + original[OFFSET+len(OLD):]
    crypto = load_crypto()
    section = sections[1]
    package = raw[:section['offset']] + crypto.build_section(
        patched, crypto.CIPHERS['yichip'], section['id'], section['addr'],
        section['payload_len'], section['pid'])
    headers, decoded = unpack(package, ['gd32', 'yichip'])
    if headers != sections or decoded != [payloads[0], patched]:
        raise ValueError('Independent package decode differs from intended payloads')
    differences = [i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    if any(not OFFSET <= i < OFFSET+len(OLD) for i in differences):
        raise ValueError('Unexpected payload difference')
    report = {
        'kind': 'Experimental name-only firmware package; no custom GATT stream',
        'stock_sha256': sha256(raw), 'package_sha256': sha256(package),
        'payload_sha256': sha256(patched), 'size': len(package),
        'section_offset': section['offset'], 'name_payload_offset': OFFSET,
        'old_name': OLD.decode(), 'new_name': NEW.decode(),
        'changed_plaintext_offsets': differences,
        'gd32_section_and_both_headers_unchanged': True,
        'tail_matches_stock_zeros': patched[0x11c04:] == bytes(508),
        'startup_data_unchanged': reconstruct(original) == reconstruct(patched),
        'usb_name_callback': '0x010221c0 reads pointer 0x206a0; conversion at 0x01021320',
        'limits': ['Shared model name may affect Bluetooth naming',
                   'No button-stream or CCC integration',
                   'Hardware result must be recorded separately'],
    }
    return package, patched, report


if __name__ == '__main__':
    package, payload, report = build()
    out = ROOT / 'build/name-probe'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'Zero2-v1.08-name-probe.dat').write_bytes(package)
    (out / 'yichip.bin').write_bytes(payload)
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
