#!/usr/bin/env python3
"""Build a candidate that disables the identified native CUS8 owners.

This does not enable a CFW flash writer or prove exclusive physical ownership.
The original v1 remains offline-only. The explicit full-store-reader v2 profile
can use the exact-reproduction OTA path for backup and boot validation.
"""
import argparse
import json
from pathlib import Path

from build_memomind_graphics import BODY_BASE, construct_graphics, _guard_final_bounds
from memomind_ota import repack, require, sha, unpack_ota

FORMAT = 'memomind-exclusive-store-owner-gates-v1'
READER_FORMAT = 'memomind-exclusive-store-reader-v2'
READER_PROFILE = 'H001Y-1.0.3.127-full-store-read-v1'
# Complete original instructions at the six reviewed entry points. Replacements
# are C.LI a0,error; C.JR ra; optionally C.NOP to cover the whole original span.
# No stack adjustment, pointer dereference, lock, allocation or I/O precedes RET.
GATES = (
    (0x042a43c8, '1971a2dc', '6d558280', -5, 'CUS8 mount/repair/format unavailable'),
    (0x042a3e20, 'b7073000', '7d558280', -1, 'CUS8 read callback unavailable'),
    (0x042a40c4, 'b7073000', '7d558280', -1, 'CUS8 program callback unavailable'),
    (0x042a411e, 'b7073000', '7d558280', -1, 'CUS8 erase callback unavailable'),
    (0x0423e8b4, '61712324811a', '7d5582800100', -1, 'CUS8 whole-store reset unavailable'),
    (0x042a9dd4, '757122c5', '7d558280', -1, 'CUS8 badmap saver unavailable'),
)


def apply_owner_gates(original, hooks=()):
    body = bytearray(original)
    occupied = set()
    edits = []
    for address, old_hex, new_hex, error, purpose in GATES:
        offset = address - BODY_BASE
        before, after = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
        require(len(before) == len(after) and len(before) in (4, 6) and address % 2 == 0,
                'Owner gate must replace complete witnessed instructions')
        require(0 <= offset and offset + len(before) <= len(original), 'Owner gate outside body')
        require(not any(offset < end and start < offset + len(before) for start, end in hooks),
                'Owner gate overlaps runtime hook')
        sites = set(range(offset, offset + len(before)))
        require(not occupied.intersection(sites), 'Owner gates overlap')
        require(body[offset:offset + len(before)] == before,
                'Owner gate instruction witness differs: ' + hex(address))
        body[offset:offset + len(before)] = after
        occupied.update(sites)
        edits.append(dict(address=address, body_offset=offset, before=old_hex,
                          after=new_hex, return_code=error, purpose=purpose))
    require(len(edits) == 6 and len(occupied) == 26, 'Incomplete fixed owner gate set')
    return bytes(body), edits


def construct_exclusive_storage(source, blob):
    base, base_manifest, base_proof = construct_graphics(source, blob)
    _, streams = unpack_ota(base)
    original = streams[3]['raw'][32:]
    hooks = [(row['body_offset'], row['body_offset'] + 8) for row in base_manifest['hooks']]
    body, edits = apply_owner_gates(original, hooks)
    changed = [i for i, (a, b) in enumerate(zip(original, body)) if a != b]
    result = repack(base, {3: body})
    _guard_final_bounds(len(result), len(body) + 32)
    inspected, final = unpack_ota(result)
    require(final[3]['raw'][32:] == body, 'Owner gate body reconstruction mismatch')
    for i in (0, 1, 2, 4, 5, 6):
        require(final[i]['raw'] == streams[i]['raw'] and final[i]['packed'] == streams[i]['packed'],
                'Owner gate construction modified another component')
    manifest = dict(format=FORMAT, source_sha256=sha(source), output_sha256=sha(result),
                    blob_sha256=sha(blob), blob_bytes=len(blob), graphics_base_sha256=sha(base),
                    graphics_base_manifest=base_manifest, edits=edits,
                    proposed_storage=dict(device=1, physical_start=0x500000,
                                          physical_end=0x800000, bytes=0x300000,
                                          xip_start=0x05500000, physical_badmap_bytes=96),
                    stock_plugin_compatibility=False, native_writer_enabled=False,
                    exclusive_ownership_proven=False, live_flashing_enabled=False)
    proof = dict(format='memomind-exclusive-store-owner-gates-proof-v1', offline_only=True,
                 output_bytes=len(result), changed_body_byte_offsets=changed,
                 additional_gate_sites=len(edits), additional_instruction_span_bytes=26,
                 source_graphics_proof=base_proof, checksums=inspected['checksums'],
                 unchanged_component_indices=[0, 1, 2, 4, 5, 6],
                 unresolved=[
                     'Caller failure handling and startup behavior require native review and hardware validation.',
                     'Entry gates cover identified CUS8 paths, not raw flash APIs, OTA/factory paths or unknown indirect owners.',
                     'A fresh boot with no old plugin context and full-region backup/preflight are required before reuse.',
                     'The effective badmap must retain absent/default provenance and all physical exclusions.',
                     'No CFW native flash writer, canary, full-capacity hardware test or persistence contract is supplied.'])
    return result, manifest, proof


def verify_exclusive_storage(source, blob, manifest):
    result, expected, proof = construct_exclusive_storage(source, blob)
    require(type(manifest) is dict and manifest == expected
            and json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            'Exclusive storage manifest differs from exact construction')
    return result, proof


def construct_exclusive_reader(source, blob):
    """The reviewed owner gates plus the explicit read-only full-region runtime.

    The profile witness prevents accidentally promoting the earlier limited
    reader. Executable correctness is validated by the separate build/native
    suites; a string witness is not a code-correctness proof.
    """
    require(isinstance(blob, bytes) and (b'"profile":"' + READER_PROFILE.encode() + b'"') in blob,
            'Exclusive reader requires the full-store-reader runtime profile')
    result, manifest, proof = construct_exclusive_storage(source, blob)
    manifest.update(format=READER_FORMAT, reader_profile=READER_PROFILE,
                    live_flashing_enabled=True,
                    permitted_runtime_storage_operations=['query', 'read', 'topology', 'badmap'])
    proof.update(format='memomind-exclusive-store-reader-construction-proof-v2',
                 deployment_scope='Owner-disabled boot validation and read-only full-region acquisition; no CFW writer',
                 caller_review='analysis/exclusive-store-review-20261101/report.md')
    return result, manifest, proof


def verify_exclusive_reader(source, blob, manifest):
    result, expected, proof = construct_exclusive_reader(source, blob)
    require(type(manifest) is dict and manifest == expected
            and json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            'Exclusive reader manifest differs from exact construction')
    return result, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('blob', type=Path)
    parser.add_argument('output', type=Path, help='New directory, exclusive creation')
    parser.add_argument('--full-store-reader', action='store_true',
                        help='Explicit v2 read-only acquisition/boot-validation profile')
    args = parser.parse_args()
    source, blob = args.source.read_bytes(), args.blob.read_bytes()
    construct = construct_exclusive_reader if args.full_store_reader else construct_exclusive_storage
    result, manifest, proof = construct(source, blob)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'firmware.bin').write_bytes(result)
    (args.output / 'runtime.bin').write_bytes(blob)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (args.output / 'verification.json').write_text(json.dumps(proof, indent=2) + '\n')
    if args.full_store_reader:
        _, components = unpack_ota(result)
        (args.output / 'expected-app-header.bin').write_bytes(components[3]['raw'][:256])
    print(json.dumps(dict(output_bytes=len(result), sha256=sha(result),
                          live_flashing_enabled=manifest['live_flashing_enabled'])))


if __name__ == '__main__':
    main()
