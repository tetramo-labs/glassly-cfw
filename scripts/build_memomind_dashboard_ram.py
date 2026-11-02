#!/usr/bin/env python3
"""Fixed cold-boot retirement of stock card/status/header UI allocations.

Uses the exact diagnostic release as source and leaves CFW runtime, transport,
app descriptors and shared screen intact. No RAM is freed or reassigned by the
patch itself: ordinary boot clears the reviewed owner pointers, and six void
entry gates prevent their construction/use. Not a hot-patch implementation.
"""
import argparse
import json
from pathlib import Path
from build_memomind_graphics import BODY_BASE, _guard_final_bounds
from memomind_ota import require, sha, repack, unpack_ota

FORMAT = 'memomind-dashboard-ram-v1'
SOURCE_SHA = 'a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917'
GATES = (
    (0x04264f26, '011122cc', '01458280', 'card subtree constructor'),
    (0x04265060, '011122cc', '01458280', 'card layout setter without null owner guard'),
    (0x042652e8, '83a7416a', '01458280', 'card visibility setter without null owner guard'),
    (0x0426f2c2, '411122c4', '01458280', 'status subtree constructor'),
    (0x04268336, '011106ce', '01458280', 'DND header content constructor'),
    (0x042683f0, '411122c6', '01458280', 'DND header content update'),
)


def apply_ram_gates(original):
    body = bytearray(original)
    edits = []
    for address, before, after, purpose in GATES:
        offset = address-BODY_BASE
        require(0 <= offset <= len(body)-4 and body[offset:offset+4] == bytes.fromhex(before),
                'Dashboard RAM gate witness differs: '+hex(address))
        body[offset:offset+4] = bytes.fromhex(after)
        edits.append(dict(address=address, body_offset=offset, before=before, after=after, purpose=purpose))
    return bytes(body), edits


def construct_dashboard_ram(source):
    require(sha(source) == SOURCE_SHA, 'Requires exact diagnostic-commands-001 source')
    _, streams = unpack_ota(source)
    original = streams[3]['raw'][32:]
    body, edits = apply_ram_gates(original)
    allowed = {i for row in edits for i in range(row['body_offset'], row['body_offset']+4)}
    require(len(allowed) == 24 and len(body) == len(original), 'Gate overlap or size drift')
    changed = [i for i, (a, b) in enumerate(zip(original, body)) if a != b]
    require(set(changed) <= allowed, 'Modification escaped fixed gates')
    output = repack(source, {3: body})
    _guard_final_bounds(len(output), len(body)+32)
    decoded, final = unpack_ota(output)
    require(final[3]['raw'][32:] == body, 'Reconstructed app differs')
    for i in (0, 1, 2, 4, 5, 6):
        require(streams[i]['raw'] == final[i]['raw'] and streams[i]['packed'] == final[i]['packed'],
                'Unrelated component changed')
    manifest = dict(format=FORMAT, source_sha256=SOURCE_SHA, output_sha256=sha(output),
                    output_body_sha256=sha(body), edits=edits, cold_boot_required=True,
                    requested_base_allocations_avoided_bytes=1440,
                    measured_heap_saving_bytes=None, hardware_validated=False,
                    live_admission='Separate exact native Swift catalog entry required')
    proof = dict(manifest=manifest, output_bytes=len(output), app_body_bytes=len(body),
                 changed_body_byte_offsets=changed, unchanged_component_indices=[0,1,2,4,5,6],
                 runtime_unchanged=True, descriptor_table_unchanged=True,
                 checksums=decoded['checksums'],
                 limits=['1440 bytes sums requested context/base-object sizes, excluding allocator overhead, styles and decoded resources.',
                         'The card/status subsystem is shared by several stock screens; its UI is intentionally retired across them.',
                         'Shared active screen and launcher root/header container remain allocated.',
                         'No hot teardown, static RAM reuse, largest-block guarantee or runtime scratch trimming.'])
    return output, manifest, proof


def verify_dashboard_ram(source, manifest):
    output, expected, proof = construct_dashboard_ram(source)
    require(type(manifest) is dict and json.dumps(manifest, sort_keys=True) ==
            json.dumps(expected, sort_keys=True), 'Dashboard RAM manifest differs')
    return output, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    image, manifest, proof = construct_dashboard_ram(args.source.read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'firmware.bin').write_bytes(image)
    (args.output/'expected-app-header.bin').write_bytes(unpack_ota(image)[1][3]['raw'][:256])
    for name, value in [('manifest.json', manifest), ('verification.json', proof)]:
        (args.output/name).write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
