#!/usr/bin/env python3
"""Construct the fixed external-cache reservation candidate, offline only.

The live flasher deliberately does not recognize this manifest yet. Physical
topology, current-state preflight and native badmap acquisition remain separate
requirements. This constructor never reads or changes a device.
"""
import argparse
import json
from pathlib import Path

from build_memomind_graphics import construct_graphics, BODY_BASE, _guard_final_bounds
from memomind_ota import repack, require, sha, unpack_ota

FORMAT = 'memomind-external-store-runtime-v1'
# Reviewed H001Y 1.0.3.127 instruction witnesses. No caller-supplied edits.
PATCHES = (
    (0x042a44d8, '37063000', '37062000', 'primary mount capacity'),
    (0x042a4516, '37063000', '37062000', 'repair mount capacity'),
    (0x042a452a, '37063000', '37062000', 'format capacity'),
    (0x042a4572, '37073000', '37072000', 'advisory empty-context capacity'),
    (0x042a3e20, 'b7073000', 'b7072000', 'read callback bound'),
    (0x042a40c4, 'b7073000', 'b7072000', 'program callback bound'),
    (0x042a411e, 'b7073000', 'b7072000', 'erase callback bound'),
    (0x042a41ae, 'b7073000', 'b7072000', 'package verifier bound'),
    (0x0423e9be, 'b7073000', 'b7072000', 'whole-store wipe end'),
    (0x0423ea4a, 'b7063000', 'b7062000', 'whole-store wipe block remainder'),
    (0x042a0998, '63ee2701', '6f00c001', 'physical badmap validity independent of reduced logical capacity; JAL zero,+28'),
)


def construct_storage(source, blob):
    base, base_manifest, base_proof = construct_graphics(source, blob)
    _, streams = unpack_ota(base)
    original = streams[3]['raw'][32:]
    body = bytearray(original)
    occupied = set()
    hooks = [(row['body_offset'], row['body_offset'] + 8) for row in base_manifest['hooks']]
    edits = []
    for address, before_hex, after_hex, purpose in PATCHES:
        offset = address - BODY_BASE
        before, after = bytes.fromhex(before_hex), bytes.fromhex(after_hex)
        require(len(before) == len(after) == 4 and address % 2 == 0,
                'Reservation edit must be one witnessed four-byte instruction')
        require(0 <= offset and offset + 4 <= len(original) - len(blob) - 8,
                'Reservation edit must lie in original application code')
        require(not any(offset < end and start < offset + 4 for start, end in hooks),
                'Reservation edit overlaps runtime hook')
        sites = set(range(offset, offset + 4))
        require(not occupied.intersection(sites), 'Reservation edits overlap')
        require(body[offset:offset + 4] == before, 'Reservation instruction witness differs: ' + hex(address))
        body[offset:offset + 4] = after
        occupied.update(sites)
        edits.append(dict(address=address, body_offset=offset, before=before_hex, after=after_hex, purpose=purpose))
    require(len(edits) == 11 and len(occupied) == 44, 'Incomplete fixed reservation patch')
    changed = [i for i, (a, b) in enumerate(zip(original, body)) if a != b]
    require(set(changed) <= occupied, 'Unexpected application change')
    result = repack(base, {3: bytes(body)})
    _guard_final_bounds(len(result), len(body) + 32)
    inspected, final = unpack_ota(result)
    require(final[3]['raw'][32:] == body, 'Reservation body reconstruction mismatch')
    for i in (0, 1, 2, 4, 5, 6):
        require(final[i]['raw'] == streams[i]['raw'] and final[i]['packed'] == streams[i]['packed'],
                'Reservation modified another component or partition metadata')
    manifest = dict(format=FORMAT, source_sha256=sha(source), output_sha256=sha(result),
                    blob_sha256=sha(blob), blob_bytes=len(blob), graphics_base_sha256=sha(base),
                    graphics_base_manifest=base_manifest, edits=edits,
                    reservation=dict(device=1, physical_start=0x700000, physical_end=0x800000,
                                     bytes=0x100000, native_store_start=0x500000,
                                     native_capacity=0x200000, directory_bytes=0x10000,
                                     physical_badmap_bytes=96, reserved_badmap_slice=[64, 96]),
                    live_flashing_enabled=False)
    proof = dict(format='memomind-external-store-construction-proof-v1', offline_only=True,
                 manifest=manifest, output_bytes=len(result), changed_body_byte_offsets=changed,
                 additional_instruction_sites=len(edits), additional_instruction_span_bytes=44,
                 source_graphics_proof=base_proof, checksums=inspected['checksums'],
                 unchanged_component_indices=[0, 1, 2, 4, 5, 6],
                 final_bounds=dict(payload_bytes=len(result) - 18,
                                   rounded_payload_bytes=(len(result) - 18 + 4095) & ~4095,
                                   app_raw_bytes=len(body) + 32),
                 unresolved=['Current directory and live-context migration preconditions must be enforced.',
                             'Real badmap must be acquired and preserved before mutable storage use.',
                             'Separate SPI staging backend physical topology remains under investigation.',
                             'No canary, storage write, reset or full-capacity native cache test is established by construction.'])
    return result, manifest, proof


def verify_storage(source, blob, manifest):
    result, expected, proof = construct_storage(source, blob)
    require(type(manifest) is dict and manifest == expected
            and json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            'Storage manifest differs from exact fixed construction')
    return result, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('blob', type=Path)
    parser.add_argument('output', type=Path, help='New directory, exclusive creation')
    args = parser.parse_args()
    result, manifest, proof = construct_storage(args.source.read_bytes(), args.blob.read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'firmware.bin').write_bytes(result)
    (args.output / 'runtime.bin').write_bytes(args.blob.read_bytes())
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (args.output / 'verification.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'output_bytes': len(result), 'sha256': sha(result), 'live_flashing_enabled': False}))


if __name__ == '__main__':
    main()
