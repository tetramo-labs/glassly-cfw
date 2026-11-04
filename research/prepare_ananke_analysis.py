#!/usr/bin/env python3
"""Wrap pinned V0900 bytes in an analysis-only ELF. No flashable output."""
from pathlib import Path
import json
import struct

from inspect_ananke import ROOT, inspect, sha


def analysis_elf(sections):
    names = b'\0' + b'\0'.join(name.encode() for name, _, _ in sections) + b'\0.shstrtab\0'
    body = bytearray(52)
    headers = [bytes(40)]
    for name, address, data in sections:
        body.extend(bytes(-len(body) % 4))
        offset = len(body)
        body.extend(data)
        headers.append(struct.pack('<10I', names.index(name.encode()), 1, 6, address,
                                   offset, len(data), 0, 0, 2, 0))
    offset = len(body)
    body.extend(names)
    headers.append(struct.pack('<10I', names.index(b'.shstrtab'), 3, 0, 0, offset,
                               len(names), 0, 0, 1, 0))
    body.extend(bytes(-len(body) % 4))
    shoff = len(body)
    body.extend(b''.join(headers))
    # EM=241 independently confirmed by the pinned compiler's pi32v2/r3 probe.o.
    # No program headers: this file is for disassembly, never installation.
    body[:52] = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01'+bytes(9),
                           2, 241, 1, 0x1e00120, 0, shoff, 0, 52, 0, 0, 40,
                           len(headers), len(headers)-1)
    return bytes(body)


def main():
    app = (ROOT/'research/oem-unpacked/IG05_V0900.ufw/files/app.bin').read_bytes()
    inspect(app)
    output = ROOT/'research/pi32v2-analysis'
    output.mkdir(exist_ok=True)
    # Independently decoded startup at 0x01e00182: r4=destination, r1=source,
    # r2=byte count, followed by the word-copy loop. Pin the instructions too.
    if app[0x62:0x76].hex() != 'c4ff00000000c1ff4cc5e401c2ffc4660000a2a2':
        raise ValueError('Unexpected startup RAM relocation')
    source_address = 0x1e4c54c
    source_offset = source_address - 0x1e00120
    ram_length = 0x66c4
    if source_offset + ram_length > len(app):
        raise ValueError('RAM image exceeds application')
    ram = app[source_offset:source_offset + ram_length]
    elf = analysis_elf([('.app_storage', 0x1e00120, app), ('.ram_initial', 0, ram)])
    (output/'v0900.analysis.elf').write_bytes(elf)
    manifest = dict(application_sha256=sha(app), analysis_elf_sha256=sha(elf),
                    elf_machine=241, origin='OEM entry-point metadata: 0x01e00120',
                    ram_copy=dict(source_file_offset=source_offset, source_address=source_address,
                                  destination=0, bytes=ram_length, sha256=sha(ram)),
                    bss=dict(start=0x6f40, bytes=0x5088, end_exclusive=0xbfc8),
                    warning='Analysis views include data as well as code; function discovery needs review. Not flashable.')
    (output/'analysis.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(output/'v0900.analysis.elf')


if __name__ == '__main__':
    main()
