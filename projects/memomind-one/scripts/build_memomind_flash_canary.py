#!/usr/bin/env python3
"""Construct the fixed flash-canary profile with private boot-cleared registry.

Includes the six reviewed native plugin-owner gates. The 256-byte registry is
removed from the native heap; all preexisting globals and the heap end retain
their addresses. Construction does not itself establish hardware write safety.
"""
import argparse
import json
from pathlib import Path

from build_memomind_graphics import BODY_BASE, _guard_final_bounds
from build_memomind_exclusive_storage import construct_exclusive_storage
from memomind_rx_profile import DEFAULT_RX_PROFILE, rx_limit, mark_manifest, add_rx_argument
from memomind_ota import repack, require, sha, unpack_ota

FORMAT = 'memomind-fixed-flash-canary-v1'
PROFILE = 'H001Y-1.0.3.127-flash-canary-v1'
REGISTRY_START, REGISTRY_END = 0x0205e128, 0x0205e228
HEAP_END = 0x020fedc0
REGISTRY_PATCHES = (
    (0x041fb238, '93878712', '93878722', 'Extend ordinary startup BSS zero endpoint by256'),
    (0x04399550, '28e10502', '28e20502', 'Move sole native pool start above private registry'),
    (0x04399554, '980c0a00', '980b0a00', 'Reduce sole native pool size by256; preserve end'),
)


def apply_registry_carve(original):
    body = bytearray(original)
    edits = []
    for address, old_hex, new_hex, purpose in REGISTRY_PATCHES:
        offset = address - BODY_BASE
        before, after = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
        require(len(before) == len(after) == 4 and 0 <= offset <= len(body) - 4,
                'Invalid fixed registry witness')
        require(body[offset:offset + 4] == before,
                'Registry instruction/table witness differs: ' + hex(address))
        body[offset:offset + 4] = after
        edits.append(dict(address=address, body_offset=offset, before=old_hex, after=new_hex, purpose=purpose))
    table = 0x04399550 - BODY_BASE
    require(int.from_bytes(body[table:table + 4], 'little') == REGISTRY_END
            and int.from_bytes(body[table + 4:table + 8], 'little') == HEAP_END - REGISTRY_END
            and int.from_bytes(body[table + 8:table + 12], 'little') == 2,
            'Registry carve changed heap end/flags')
    return bytes(body), edits


def construct_canary(source, blob, *, rx_profile=DEFAULT_RX_PROFILE):
    require(isinstance(blob, bytes) and (b'"profile":"' + PROFILE.encode() + b'"') in blob,
            'Canary requires the explicit flash-canary runtime profile')
    base, base_manifest, base_proof = construct_exclusive_storage(source, blob, rx_profile=rx_profile)
    _, streams = unpack_ota(base)
    original = streams[3]['raw'][32:]
    body, edits = apply_registry_carve(original)
    result = repack(base, {3: body})
    _guard_final_bounds(len(result), len(body) + 32)
    inspected, final = unpack_ota(result)
    require(final[3]['raw'][32:] == body, 'Canary body reconstruction mismatch')
    for index in (0, 1, 2, 4, 5, 6):
        require(final[index]['raw'] == streams[index]['raw']
                and final[index]['packed'] == streams[index]['packed'], 'Canary changed another component')
    manifest = dict(format=FORMAT, source_sha256=sha(source), output_sha256=sha(result),
                    blob_sha256=sha(blob), blob_bytes=len(blob), reader_profile=PROFILE,
                    owner_gate_base_sha256=sha(base), owner_gate_base_manifest=base_manifest,
                    registry_edits=edits,
                    private_ram=dict(start=REGISTRY_START, end=REGISTRY_END, bytes=256, alignment=8,
                                     zeroed_by_ordinary_boot=True, native_heap_start=REGISTRY_END,
                                     native_heap_end=HEAP_END, native_heap_raw_bytes=HEAP_END - REGISTRY_END),
                    canary=dict(device=1, sector_start=0x7ff000, sector_bytes=4096,
                                neighbor_start=0x7fe000, program_bytes=256,
                                operations='fixed erase/program/readback/erase-restore; no arbitrary address/data',
                                starts_per_boot=1),
                    live_flashing_enabled=True, native_writer_enabled=True,
                    general_mutable_store_enabled=False, exclusive_ownership_proven=False)
    proof = dict(format='memomind-fixed-flash-canary-construction-proof-v1', offline_only=True,
                 output_bytes=len(result), registry_changed_body_offsets=[i for i,(a,b) in enumerate(zip(original,body)) if a!=b],
                 registry_edit_span_bytes=12, source_owner_gate_proof=base_proof,
                 unchanged_component_indices=[0,1,2,4,5,6], checksums=inspected['checksums'],
                 review='analysis/flash-worker-lifecycle-20261101/heap-carve/proposed-edits.json',
                 limitations=['A complete current backup and fresh map/topology/header preflight precede any canary start.',
                              'Native task and flash waits can block or assert; host timeout does not cancel work.',
                              'The canary is not native full-capacity scene storage or a persistent filesystem.'])
    mark_manifest(manifest, rx_profile)
    return result, manifest, proof


def verify_canary(source, blob, manifest, *, rx_profile=DEFAULT_RX_PROFILE):
    result, expected, proof = construct_canary(source, blob, rx_profile=rx_profile)
    require(type(manifest) is dict and manifest == expected
            and json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            'Canary manifest differs from exact construction')
    return result, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('blob', type=Path)
    parser.add_argument('output', type=Path)
    add_rx_argument(parser)
    args = parser.parse_args()
    blob = args.blob.read_bytes()
    result, manifest, proof = construct_canary(args.source.read_bytes(), blob, rx_profile=args.rx_profile)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'firmware.bin').write_bytes(result)
    (args.output / 'runtime.bin').write_bytes(blob)
    _, streams = unpack_ota(result)
    (args.output / 'expected-app-header.bin').write_bytes(streams[3]['raw'][:256])
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (args.output / 'verification.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(dict(output_bytes=len(result), sha256=sha(result))))


if __name__ == '__main__':
    main()
