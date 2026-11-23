#!/usr/bin/env python3
"""Record reviewed V0900 code ranges and hypotheses, never patch an application."""
import json
from pathlib import Path
from inspect_ananke import ROOT, inspect, sha

APP_BASE = 0x1e00120
RAM_SOURCE = 0x4c42c


def main():
    app = (ROOT/'research/oem-unpacked/IG05_V0900.ufw/files/app.bin').read_bytes()
    inspect(app)
    table_base = 0x1e16d82
    entry_offset = table_base - APP_BASE + (26 - 3) * 2
    entry = int.from_bytes(app[entry_offset:entry_offset+2], 'little')
    if entry != 0x82 or table_base + 2 * entry != 0x1e16e86:
        raise ValueError('Unexpected multi-ATT dispatch table entry')
    ranges = [
        ('startup', APP_BASE, 0x9a, 'flash'),
        ('gpio_scan', 0x14ba, 0x10e, 'ram'),
        ('scan_task_candidate', 0x18c6, 0x30, 'ram'),
        ('ae42_sender', 0x1e332a0, 0x24, 'flash'),
        ('hid_or_vendor_ccc_ready', 0x1e331fc, 0x5e, 'flash'),
        ('att_send_wrapper', 0x1e3181c, 0x82, 'flash'),
        ('ble_command_dispatch', 0x1e16cfe, 0xdc, 'flash'),
        ('multi_att_send_case', 0x1e16e86, 0x16, 'flash'),
        ('att_send_queue', 0x1e16af4, 0xf0, 'flash'),
        ('att_queue_record', 0x1e16ab0, 0x44, 'flash'),
        ('circular_buffer_write_candidate', 0x1e00ac2, 0x64, 'flash'),
        ('ccc_lookup', 0x1e169d8, 0x36, 'flash'),
        ('input_scan_callsite', 0x1e3b5b6, 4, 'flash'),
        ('key_decode_callsite', 0x1e3b7f6, 4, 'flash'),
    ]
    functions = []
    for name, address, length, region in ranges:
        offset = address - APP_BASE if region == 'flash' else RAM_SOURCE + address
        data = app[offset:offset+length]
        if len(data) != length:
            raise ValueError('Invalid code range')
        functions.append(dict(name=name, runtime_address=hex(address), file_offset=hex(offset),
                              bytes=length, sha256=sha(data), region=region))
    pins = [(19,0), (16,1), (23,3), (25,4), (1,6), (21,7), (27,8), (24,9),
            (26,10), (22,11), (17,12), (18,15), (3,16), (7,17), (6,18),
            (5,19), (8,23), (17,24), (12,31)]
    # GPIO 17 is intentionally queried twice and contributes two logical bits.
    report = dict(application_sha256=sha(app), inspector_sha256=sha(Path(__file__).read_bytes()),
        scope='Static OEM V0900 analysis only',
        ranges=functions,
        ram_copy=dict(source_file_offset=hex(RAM_SOURCE), destination='0x0', bytes=0x66c4),
        bss=dict(start='0x6f40', end_exclusive='0xbfc8'),
        candidate_state=dict(shared_base='0x78e0', connection_u16='0x7920',
                             raw_keys_u32='0x79e4', scan_tick_u32='0x79e8', tick_u32='0x7a4c'),
        gpio_scan=[dict(gpio=pin, mask=hex(1 << bit), active_low=True) for pin,bit in pins],
        direct_calls=[dict(site='0x1e332bc', target='0x1e3181c', role='AE42 to ATT wrapper'),
                      dict(site='0x1e31860', target='0x1e16cfe', role='ATT wrapper dispatches command 26 with five arguments'),
                      dict(site='0x1e16ef6', target='0x1e16af4', role='shared multi-ATT send case to queue'),
                      dict(site='0x1e16bb2', target='0x1e16ab0', role='queue payload chunk'),
                      dict(site='0x1e16ad8', target='0x1e00ac2', role='copy payload into circular buffer candidate'),
                      dict(site='0x1e00af0', target='0x1127a8', role='external ROM copy candidate; symbol unconfirmed'),
                      dict(site='0x1e3324c', target='0x1e331f8', role='vendor CCC getter wrapper'),
                      dict(site='0x1e3b5b6', target='0x18c6', role='scan task candidate'),
                      dict(site='0x1e3b7f6', target='0x192a', role='key decode candidate')],
        att_lifetime=dict(
            status='Static copy-path candidate; ROM routine and live behavior unconfirmed',
            dispatch_command=26, table_base='0x1e16d82', table_index=23,
            table_entry='0x82', case_target='0x1e16e86',
            automatic_ccc='Operation type zero looks up value handle + 1 for the current connection',
            record_header_bytes=6,
            queue_behavior='Writes header then payload, checks combined count, returns zero only on successful queueing',
            copy_candidate='0x1e00ac2 checks capacity, calls ROM 0x1127a8 once or twice for wraparound, then advances write counters',
            limitation='No installed-image equivalence, ROM symbol verification or hardware send validation yet'),
        branch_rule='For reviewed direct calls: (instruction address + instruction bytes + signed displacement) & 0x1ffffff; verified against scanner/helper structure, not a complete ISA audit.',
        unresolved=['Installed 0x0601 backup and partition map',
                    'Physical labels and contact debounce for all GPIOs',
                    'All paths reaching input task, independent of HID readiness',
                    'Confirm ROM copy routine and live ATT lifetime; CCC resets, disconnect and standby behavior',
                    'Execution limits, branch-target audit, task stack/state reservation and recovery',
                    'Live GATT capture and actual iPhone foreground/background/locked delivery'])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
