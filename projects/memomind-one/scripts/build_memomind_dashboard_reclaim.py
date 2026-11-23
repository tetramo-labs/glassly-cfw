#!/usr/bin/env python3
"""Offline six-renderer retirement/reuse profile for the pinned diagnostics OTA.

Each original callback entry returns the native unavailable result (-1). Its
remaining body is a separate RX island; entries, table and launcher lifecycle
stay at their original addresses. Payloads must already be linked for that
island. This constructor enforces fixed byte witnesses and edit intervals;
executable correctness and live admission remain separate. See
analysis/dashboard-reclaim-review-20261102/report.md.
"""
import argparse
import json
from pathlib import Path

from build_memomind_graphics import BODY_BASE, _guard_final_bounds
from memomind_ota import repack, require, sha, unpack_ota

FORMAT = 'memomind-dashboard-renderer-islands-v1'
SOURCE_SHA = 'a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917'
# Entry, exclusive end, complete original instruction prefix, whole body hash.
RENDERERS = (
    (0x042708e2, 0x04270ace, '2d71232e1110', 'fa69b39af67090767b9c39b898553e0ac4a45edf0b4bcbf1f0e9cdb796ad588c'),
    (0x04270ace, 0x04270c82, '2971232e1112', 'e97ef6676f60d4aec3b34965748f5135d8cbee3377f26350936a95ac3999b310'),
    (0x04270c82, 0x04270dd2, '157186cf', '065b46cdbfd265abcd2c220bd4da3970f6ec76f745adeb370fd40c6c0caa0113'),
    (0x04270dd2, 0x04270f98, '5571a2c5', 'dc1a59a810931b2a18353ef5509ff67c90ae6e742568248f78cb9e0a438c7cec'),
    (0x04270f98, 0x042711a4, '497123248116', '100c520bf4b1f849c680d7d2032b055f9d89f5990c2213a734deb271ec2cada5'),
    (0x042711a4, 0x042713bc, '2971232e1112', 'bad031484ef0957c8c6405a06f2ac728b5db966e597b8d1244a6ced4de230ddd'),
)


def apply_renderer_islands(original, payloads=None):
    """Whole-function witnesses remain mandatory even for an empty payload."""
    payloads = {} if payloads is None else payloads
    require(type(payloads) is dict and all(type(k) is int for k in payloads),
            'Payloads must map fixed integer renderer entries to bytes')
    require(set(payloads) <= {r[0] for r in RENDERERS}, 'Unknown renderer island')
    body = bytearray(original)
    edits = []
    for entry, end, before_hex, expected_sha in RENDERERS:
        before = bytes.fromhex(before_hex)
        offset, stop = entry-BODY_BASE, end-BODY_BASE
        require(0 <= offset < stop <= len(original), 'Renderer outside application')
        require(original[offset:offset+len(before)] == before and
                sha(original[offset:stop]) == expected_sha, 'Renderer body witness differs')
        gate = bytes.fromhex('7d558280') + bytes.fromhex('0100') * ((len(before)-4)//2)
        start, capacity = entry+len(gate), end-entry-len(gate)
        payload = payloads.get(entry, b'')
        require(type(payload) is bytes and len(payload) <= capacity and len(payload) % 2 == 0,
                'RX island requires an even, bounded bytes payload')
        # Zero fill is intentionally non-executable padding, not writable storage.
        body[offset:stop] = gate + payload + bytes(capacity-len(payload))
        edits.append(dict(entry=entry, end=end, body_sha256=expected_sha,
                          before=before_hex, gate=gate.hex(), return_code=-1,
                          rx_start=start, rx_end=end, rx_capacity=capacity,
                          payload_bytes=len(payload), payload_sha256=sha(payload)))
    require(sum(e['rx_capacity'] for e in edits) == 2746, 'Fixed island budget differs')
    return bytes(body), edits


def construct_dashboard_reclaim(source, payloads=None):
    require(sha(source) == SOURCE_SHA, 'Requires exact installed diagnostic-commands-001 OTA')
    _, streams = unpack_ota(source)
    original = streams[3]['raw'][32:]
    body, edits = apply_renderer_islands(original, payloads)
    output = repack(source, {3: body})
    _guard_final_bounds(len(output), len(body)+32)
    checked, final = unpack_ota(output)
    require(final[3]['raw'][32:] == body, 'Repacked body differs')
    unchanged = [0, 1, 2, 4, 5, 6]
    for index in unchanged:
        require(final[index]['raw'] == streams[index]['raw'] and
                final[index]['packed'] == streams[index]['packed'], 'Unrelated component changed')
    start, end = RENDERERS[0][0]-BODY_BASE, RENDERERS[-1][1]-BODY_BASE
    require(original[:start] == body[:start] and original[end:] == body[end:] and
            len(body) == len(original), 'Edit escaped fixed renderer bodies')
    manifest = dict(format=FORMAT, source_sha256=SOURCE_SHA, output_sha256=sha(output),
                    output_body_sha256=sha(body), islands=edits, rx_capacity=2746,
                    live_flashing_enabled=False, hardware_validated=False,
                    dashboard_fully_removed=False)
    proof = dict(manifest=manifest, offline_only=True, output_bytes=len(output),
                 body_bytes=len(body), checksums=checked['checksums'],
                 unchanged_component_indices=unchanged,
                 launcher_descriptor_and_callback_table_unchanged=True,
                 installed_runtime_and_shared_navigation_unchanged=True,
                 limitations=[
                     'Six fragmented RX islands, not a contiguous allocation or writable flash store.',
                     'Caller fallback is retained; this does not remove all dashboard UI or free its heap.',
                     'Payload ABI, linking and behavior need separate validation before use.',
                     'Static references and mocked execution do not exclude every computed interior entry.',
                     'No live catalog admission, hardware behavior or RAM saving is established.'])
    return output, manifest, proof


def verify_dashboard_reclaim(source, manifest, payloads=None):
    output, expected, proof = construct_dashboard_reclaim(source, payloads)
    require(type(manifest) is dict and json.dumps(manifest, sort_keys=True) ==
            json.dumps(expected, sort_keys=True), 'Renderer island manifest differs')
    return output, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output_directory', type=Path)
    parser.add_argument('--payload', action='append', default=[], metavar='ENTRY=FILE',
                        help='Already-linked RX bytes for one fixed island; repeatable')
    args = parser.parse_args()
    payloads = {}
    for spec in args.payload:
        entry, filename = spec.split('=', 1)
        address = int(entry, 0)
        require(address not in payloads, 'Duplicate island payload')
        payloads[address] = Path(filename).read_bytes()
    image, manifest, proof = construct_dashboard_reclaim(args.source.read_bytes(), payloads)
    args.output_directory.mkdir(parents=True, exist_ok=False)
    for name, value in [('manifest.json', manifest), ('verification.json', proof)]:
        (args.output_directory/name).write_text(json.dumps(value, indent=2)+'\n')
    (args.output_directory/'firmware.bin').write_bytes(image)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
