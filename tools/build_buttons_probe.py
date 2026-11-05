"""Build the experimental queued button snapshot image; see docs/buttons-probe.md."""
import json
import subprocess
from build_ble_probe import build as build_ble
from build_notify_probe import text_section, TAIL
from firmware_image import ROOT, load_stock, load_crypto, unpack, sha256
from startup import reconstruct

HOOKS = {0x1918: bytes.fromhex('09f0cafc'), 0x1ae0: bytes.fromhex('02f0c8fe'),
         0x3e28: bytes.fromhex('00f00afe'), 0x3e36: bytes.fromhex('03f00bf8'),
         0xbbba: bytes.fromhex('0322')}
STATE = 0x22514
STATE_BYTES = 48


def build():
    raw, sections, payloads = load_stock()
    _, base, _ = build_ble()
    if any(base[TAIL:]) or base[0xb342:0xb350].hex() != '002001e001c1121f002afbd17047':
        raise ValueError('Tail/startup no longer matches audit')
    out = ROOT/'build/buttons-probe'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['clang', '--target=arm-none-eabi', '-mcpu=cortex-m0', '-mthumb', '-c',
                    str(ROOT/'firmware/buttons_probe.s'), '-o', str(out/'buttons_probe.o')], check=True)
    compiled = text_section((out/'buttons_probe.o').read_bytes())
    if not TAIL < len(compiled) <= len(base):
        raise ValueError('Code exceeds existing image extent')
    patched = bytearray(base)
    for offset, expected in HOOKS.items():
        if base[offset:offset+len(expected)] != expected:
            raise ValueError(f'Hook changed: {offset:#x}')
        patched[offset:offset+len(expected)] = compiled[offset:offset+len(expected)]
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
    report = dict(kind='Experimental button streaming; independent compact implementation, not the unbound C components',
                  package_sha256=sha256(package), plaintext_sha256=sha256(patched),
                  baseline_plaintext_sha256=sha256(base),
                  hooks={hex(k): dict(before=v.hex(), after=patched[k:k+len(v)].hex()) for k,v in HOOKS.items()},
                  tail_offset=hex(TAIL), tail_used_bytes=len(compiled)-TAIL,
                  state_address=hex(STATE), state_bytes=STATE_BYTES, reserved_pool_block_bytes=600,
                  pool_600_byte_blocks_before=3, pool_600_byte_blocks_after=2,
                  startup_ram_unchanged=True, gd32_and_headers_unchanged=True,
                  assembly_sha256=sha256((ROOT/'firmware/buttons_probe.s').read_bytes()),
                  protocol_version=4, queue_snapshots=16, packet_bytes=8,
                  limits=['Offline build only; hardware results are recorded separately in docs/buttons-probe.md',
                          'Host must subscribe then write A1; write A0 before unsubscribing; connect resets session',
                          'Whole-mask two-sample qualification at stock timer cadence, not the unbound 8 ms filter',
                          'Nonzero/missing radio ACK stalls sending; queued states remain and overflow is marked',
                          'One OEM 600-byte pool block is reserved, reducing OEM allocation capacity',
                          'No iOS background, long-term battery or complete stack ownership claim'])
    return package, patched, report


if __name__ == '__main__':
    package, payload, report = build()
    out = ROOT/'build/buttons-probe'
    (out/'Zero2-v1.08-buttons-probe.dat').write_bytes(package)
    (out/'yichip.bin').write_bytes(payload)
    (out/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
