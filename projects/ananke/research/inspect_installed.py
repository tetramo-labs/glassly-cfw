#!/usr/bin/env python3
"""Verify the pinned Ananke backup and extracted layout; never emit firmware."""
import binascii
import json
from pathlib import Path
import struct
from inspect_ananke import parse_profile, characteristics, sha

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT/'research/device-backup-20261103-174931'
EXTRACTED = ROOT/'research/installed-unpacked/stock-0601'
FLASH_SHA = 'da281f118ea0e3dc412b2298ce27c1b73a9cf6bca795814708e900a20a9538bc'
APP_SHA = '3c52fc8cef33ee1d0d402f68dc9a92ed819d406b5e99a9033f8304de69cfdc6f'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def entry(data, offset):
    raw = data[offset:offset+32]
    require(len(raw) == 32, 'Truncated entry')
    hc, dc, address, size, flags, reserved, index, name = struct.unpack('<HHIIBBH16s', raw)
    require(binascii.crc_hqx(raw[2:], 0) == hc, 'Entry header checksum mismatch')
    return dict(header_offset=offset, name=name.split(b'\0')[0].decode('ascii'),
                encoded_offset=address, size=size, flags=flags, index=index,
                data_crc16=dc, header_crc_valid=True)


def inspect():
    metadata_raw = (BACKUP/'metadata.json').read_bytes()
    metadata = json.loads(metadata_raw)
    require(metadata['complete'] and metadata['passes_match'] and
            metadata['flash_modified'] is False and metadata['size'] == 0x100000 and
            metadata['sha256'] == FLASH_SHA, 'Unverified backup metadata')
    originals = [(BACKUP/name).read_bytes() for name in ('flash-pass1.bin', 'flash-pass2.bin')]
    require(originals[0] == originals[1] and len(originals[0]) == 0x100000 and
            sha(originals[0]) == FLASH_SHA, 'Original backup mismatch')
    require(all((BACKUP/name).stat().st_mode & 0o222 == 0
                for name in ('flash-pass1.bin', 'flash-pass2.bin')), 'Original is writable')
    decoded = (EXTRACTED/'decrypted.bin').read_bytes()
    require(len(decoded) == len(originals[0]), 'Decoded image size mismatch')
    top = [entry(decoded, off) for off in range(0x20, 0xc0, 0x20)]
    area = entry(decoded, 0x3020)
    require(top[2]['name'] == 'app_dir_head' and top[2]['encoded_offset'] == 0x3020 and
            area['name'] == 'app_area_head' and area['encoded_offset'] == 0x1e00120,
            'Unexpected installed application layout')
    entries = [entry(decoded, off) for off in range(0x3040, 0x3100, 0x20)]
    files = []
    for record in [top[0], top[1], *entries[:2]]:
        name = record['name']
        path = EXTRACTED/('files' if name in ('app.bin', 'cfg_tool.bin') else 'top')/name
        payload = path.read_bytes()
        require(len(payload) == record['size'], 'Extracted size mismatch')
        require(binascii.crc_hqx(payload, 0) == record['data_crc16'], 'Extracted payload CRC mismatch')
        comparison = ROOT/'research/oem-unpacked/IG05_V0900.ufw'/path.relative_to(EXTRACTED)
        files.append(dict(name=name, bytes=len(payload), sha256=sha(payload), crc_valid=True,
                          matches_v0900=comparison.exists() and comparison.read_bytes() == payload))
    app = (EXTRACTED/'files/app.bin').read_bytes()
    require(sha(app) == APP_SHA, 'Unexpected installed app hash')
    require(app == decoded[0x3140:0x3140+len(app)], 'Application extraction offset mismatch')
    profiles = []
    marker = bytes.fromhex('0a000200010000280018')
    pos = app.find(marker)
    while pos != -1:
        try:
            rows, end = parse_profile(app, pos)
            chars = characteristics(rows)
            if chars:
                profiles.append(dict(file_offset=pos, end_exclusive=end, sha256=sha(app[pos:end]),
                                     attribute_count=len(rows), vendor_characteristics=[
                                         c for c in chars if c['service_uuid'] in (0xae40, 0xae00)]))
        except ValueError:
            pass
        pos = app.find(marker, pos+1)
    return dict(backup=str(BACKUP.relative_to(ROOT)), flash_bytes=len(originals[0]),
                flash_sha256=FLASH_SHA, metadata_sha256=sha(metadata_raw),
                inspector_sha256=sha(Path(__file__).read_bytes()),
                decoded_sha256=sha(decoded), top_entries=top, application_area=area,
                application_entries=entries, verified_files=files, gatt_profiles=profiles,
                limitations=['Reserved-area offsets are encoded fields, not approved write ranges.',
                             'The unpacker does not implement reserved-area semantics.',
                             'No installable image or application-independent restore has been validated.',
                             'Static GATT records do not establish stock button notifications or iOS background behavior.'])


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
