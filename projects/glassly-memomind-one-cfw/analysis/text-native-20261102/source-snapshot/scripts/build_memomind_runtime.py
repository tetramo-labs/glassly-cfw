#!/usr/bin/env python3
"""Build/reproduce the fixed first executable extension; no device operations.

The profile permits only the visually verified text OTA, a bounded appended
blob at its pinned link address, and one guarded callback-address replacement.
"""
import argparse
import json
from pathlib import Path
import struct

from append_memomind_app import append_app
from memomind_ota import repack, sha, unpack_ota, require

SOURCE_SHA = '941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876'
ENTRY = 0x0439bea0
HOOK_ADDRESS = 0x042e82e0
BODY_BASE = 0x041eb020
HOOK_BEFORE = bytes.fromhex('b7472e0493870768')
STORE_AFTER = bytes.fromhex('bcd8')
FORMAT = 'memomind-runtime-probe-v1'


def address_pair(address):
    """RISC-V LUI a5,high20 + ADDI a5,a5,signed-low12, no relaxation."""
    high = (address + 0x800) >> 12
    low = address - (high << 12)
    require(-2048 <= low <= 2047, 'Invalid RISC-V low immediate')
    return struct.pack('<II', (high << 12) | (15 << 7) | 0x37,
                       ((low & 0xfff) << 20) | (15 << 15) | (15 << 7) | 0x13)


def construct_runtime(source, blob):
    require(sha(source) == SOURCE_SHA, 'Runtime requires exact visually verified text-patch source')
    require(isinstance(blob, bytes) and 0 < len(blob) <= 4096 and len(blob) % 16 == 0,
            'First diagnostic blob must contain 16-aligned length, 16..4096 bytes')
    grown, audit = append_app(source, blob, expected_source_sha256=SOURCE_SHA, alignment=16)
    require(audit['mapping']['payload_xip_start'] == ENTRY, 'Append address differs from linked entry')
    _, streams = unpack_ota(grown)
    body = streams[3]['raw'][32:]
    offset = HOOK_ADDRESS - BODY_BASE
    require(body[offset:offset+10] == HOOK_BEFORE + STORE_AFTER, 'Callback initializer byte witness differs')
    replacement = address_pair(ENTRY)
    require(address_pair(0x042e4680) == HOOK_BEFORE, 'Original callback instruction encoding differs')
    changed = body[:offset] + replacement + body[offset+8:]
    output = repack(grown, {3: changed})
    report, rebuilt = unpack_ota(output)
    require(len(output)-18 <= 0x25e000, 'Final recompression exceeds staging capacity')
    require(rebuilt[3]['raw'][32:] == changed, 'Rebuilt application differs')
    for i in (0, 1, 2, 4, 5, 6):
        require(rebuilt[i]['packed'] == streams[i]['packed'], 'Hook changed an unrelated stream')
    manifest = {'format': FORMAT, 'source_sha256': SOURCE_SHA, 'output_sha256': sha(output),
                'blob_sha256': sha(blob), 'blob_bytes': len(blob), 'entry_address': ENTRY,
                'hook_address': HOOK_ADDRESS, 'hook_before': HOOK_BEFORE.hex(),
                'hook_after': replacement.hex()}
    proof = {'manifest': manifest, 'append_audit_before_hook': audit,
             'final_output_bytes': len(output), 'final_body_sha256': sha(changed),
             'hook_body_offset': offset, 'hook_bytes': 8,
             'callback_store_preserved': rebuilt[3]['raw'][32+offset+8:32+offset+10] == STORE_AFTER,
             'checksums': report['checksums'], 'offline_only': True,
             'execution': 'not established by construction'}
    return output, manifest, proof


def verify_runtime(source, blob, manifest):
    output, expected, proof = construct_runtime(source, blob)
    require(manifest == expected, 'Runtime manifest differs from exact reproduced fixed profile')
    return output, proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('blob', type=Path)
    p.add_argument('output_directory', type=Path, help='New directory')
    args = p.parse_args()
    output, manifest, proof = construct_runtime(args.source.read_bytes(), args.blob.read_bytes())
    args.output_directory.mkdir(parents=True, exist_ok=False)
    (args.output_directory/'firmware.bin').write_bytes(output)
    (args.output_directory/'runtime.bin').write_bytes(args.blob.read_bytes())
    (args.output_directory/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (args.output_directory/'verification.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
