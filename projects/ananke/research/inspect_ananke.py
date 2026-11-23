#!/usr/bin/env python3
"""Inspect the pinned V0900 application offline. Never open USB or emit firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent
APP_SHA = '3f4a6bea1e7901188e7c8a202cbe4916d141ec624db66218139d9f98c01762eb'
APP_SIZE = 338712
TABLE_SHA = 'c8cde854121eddb4ca0ddd996e3f0b40b1ca8744605bab6e0f9651cad2aa3aa1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_profile(data, start):
    """Parse this SDK's 16-bit UUID records; reject unsupported/malformed records."""
    rows = []
    pos = start
    previous = 0
    while True:
        require(0 <= pos <= len(data) - 2, 'Missing profile terminator')
        length = struct.unpack_from('<H', data, pos)[0]
        if length == 0:
            require(bool(rows), 'Empty profile')
            return rows, pos + 2
        require(8 <= length <= 512 and pos + length <= len(data), 'Invalid record bounds')
        _, flags, handle, uuid = struct.unpack_from('<4H', data, pos)
        require(not flags & 0x200, '128-bit UUID records are not supported')
        require(handle > previous, 'Non-increasing attribute handles')
        rows.append(dict(file_offset=pos, length=length, flags=flags,
                         handle=handle, uuid=uuid, value=data[pos + 8:pos + length].hex()))
        previous = handle
        pos += length


def characteristics(rows):
    """Cross-check declarations against value records and descriptor ownership."""
    service = None
    result = []
    current = None
    for index, row in enumerate(rows):
        value = bytes.fromhex(row['value'])
        if row['uuid'] == 0x2800:
            require(len(value) == 2, 'Invalid service declaration')
            service = int.from_bytes(value, 'little')
            current = None
        elif row['uuid'] == 0x2803:
            require(service is not None and len(value) == 5, 'Invalid characteristic declaration')
            properties, handle, uuid = struct.unpack('<BHH', value)
            require(index + 1 < len(rows), 'Missing characteristic value')
            target = rows[index + 1]
            require((target['handle'], target['uuid']) == (handle, uuid),
                    'Characteristic declaration/value mismatch')
            current = dict(service_uuid=service, uuid=uuid, properties=properties,
                           declaration_handle=row['handle'], value_handle=handle,
                           ccc_handle=None)
            result.append(current)
        elif row['uuid'] == 0x2902:
            require(current is not None and current['properties'] & 0x30,
                    'CCC without notify/indicate characteristic')
            require(current['ccc_handle'] is None and len(value) == 2, 'Invalid duplicate CCC')
            current['ccc_handle'] = row['handle']
    require(all(c['ccc_handle'] is not None for c in result if c['properties'] & 0x30),
            'Notify/indicate characteristic missing CCC')
    return result


def inspect(data):
    require(len(data) == APP_SIZE and sha(data) == APP_SHA, 'Unexpected V0900 application size/hash')
    # Scan every byte: the OEM table is not aligned to a 16-bit boundary.
    marker = bytes.fromhex('0a000200010000280018')
    candidates = []
    start = data.find(marker)
    while start != -1:
        try:
            rows, end = parse_profile(data, start)
            chars = characteristics(rows)
            # The OEM also contains a one-record GAP service fragment.
            if chars:
                candidates.append((start, end, rows, chars))
        except ValueError:
            pass
        start = data.find(marker, start + 1)
    require(len(candidates) == 1, 'Expected one unambiguous complete GAP-first profile')
    start, end, rows, chars = candidates[0]
    require(len(rows) == 91 and sha(data[start:end]) == TABLE_SHA, 'Unexpected profile bytes')
    vendor = [c for c in chars if c['service_uuid'] in (0xae40, 0xae00)]
    require([(c['uuid'], c['value_handle'], c['ccc_handle']) for c in vendor] ==
            [(0xae41, 0x52, None), (0xae42, 0x54, 0x55),
             (0xae01, 0x82, None), (0xae02, 0x84, 0x85)], 'Unexpected vendor profile')
    anchors = []
    for text in ('m_app_key.pressed_b', 'm_app_key.double_b', 'm_app_key.three_b',
                 'emf process:BLE_ST_NOTIFY_IDICATE', 'dy_hid_service(%d):',
                 'bt(%d) hid ready=%d...', 'mode=%x,att=%x,r=%4x,t=%4x,k=%8x,x=%3x,y=%3x',
                 'ble_get_gatt_profile_data', 'IG05 Gamepad',
                 '../../../../apps/hid/board/br23/board_ac635n_demo.c'):
        needle = text.encode()
        offsets = []
        pos = data.find(needle)
        while pos != -1:
            offsets.append(pos)
            pos = data.find(needle, pos + 1)
        require(bool(offsets), f'Missing analysis anchor: {text}')
        anchors.append(dict(text=text, file_offsets=offsets))
    return dict(application_sha256=sha(data), application_bytes=len(data),
                scope='Offline OEM V0900 only; not installed 0x0601 or a live GATT capture',
                profile=dict(file_offset=start, end_exclusive=end, sha256=sha(data[start:end]),
                             attributes=rows, characteristics=chars),
                vendor_characteristics=vendor, string_anchors=anchors,
                limitations=['File offsets are not established runtime addresses or patch locations.',
                             'Profile selection, CCC handling and button transmission require code tracing.',
                             'No packet format, installed layout or iOS background delivery is established.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Write analysis JSON; default is stdout')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    selected = lock['selected_cfw_base']
    package = ROOT / selected['file']
    require(sha(package.read_bytes()) == selected['sha256'], 'OEM package hash mismatch')
    app = ROOT / 'research/oem-unpacked/IG05_V0900.ufw/files/app.bin'
    report = inspect(app.read_bytes())
    report['package'] = dict(path=selected['file'], sha256=selected['sha256'])
    report['inspector_sha256'] = sha(Path(__file__).read_bytes())
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        # Never overwrite an original or an existing analysis artifact.
        with args.output.open('x') as dest:
            dest.write(text)
        print(f'Wrote {args.output}: 91 attributes; AE42 notify handle 0x54, CCC 0x55')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
