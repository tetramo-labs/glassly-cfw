#!/usr/bin/env python3
"""Identify a Jieli bootloader, or back up a confirmed BR23. Never program flash."""
import argparse
import binascii
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time
from usb_transport import NativeLink, ROM_RAM_POLICY, BR23_INQUIRY

ROOT = Path(__file__).resolve().parent
LOADER_SHA = '7384429e33ee1f340fbffe46aa928a0099c163e1374a40f6f9f27468a6f16ddf'
LOADER_SIZE = 11264
INQUIRY = bytes.fromhex('120000002400')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_prepared_backup(folder, location, loader):
    """Validate the complete pinned RAM transcript and rejected FB08 acknowledgement."""
    require(len(loader) == LOADER_SIZE and digest(loader) == LOADER_SHA, 'Loader hash mismatch')
    raw = (folder/'metadata.json').read_bytes()
    meta = json.loads(raw)
    inquiry = (folder/'inquiry.bin').read_bytes()
    require(inquiry == BR23_INQUIRY and meta.get('inquiry') == inquiry.hex(), 'Prepared identity mismatch')
    require(meta.get('operation') == 'backup' and meta.get('complete') is False and
            meta.get('flash_modified') is False and meta.get('ram_readback_verified') is True and
            meta.get('loader_sha256') == LOADER_SHA and meta.get('loader_address') == '0x12000' and
            int(meta['usb_location'], 0) == location, 'Invalid prepared backup or USB location')
    records = meta.get('ram_commands', [])
    require(len(records) == 44, 'Missing complete RAM transcript')
    for index, command in enumerate(records):
        offset = (index // 2) * 512
        block = loader[offset:offset+512]
        write = index % 2 == 0
        cdb = ((0xfb06 if write else 0xfd07).to_bytes(2, 'big') +
               struct.pack('>IH', 0x12000+offset, 512))
        cdb += b'\0' + binascii.crc_hqx(block, 0).to_bytes(2, 'little') + b'\xff'*5 if write else b'\xff'*8
        tag = index + 2
        cbw = struct.pack('<4sIIBBB16s', b'USBC', tag, 512, 0 if write else 0x80, 0, 16, cdb)
        csw = struct.pack('<4sIIB', b'USBS', tag, 512, 0)
        require(command.get('cdb') == cdb.hex() and command.get('cbw') == cbw.hex() and
                command.get('csw') == csw.hex() and command.get('complete') is True and
                command.get('residue_policy') == ROM_RAM_POLICY, 'Prepared RAM command mismatch')
        if not write:
            require(command.get('data_sha256') == digest(block), 'Prepared RAM hash mismatch')
    jump = meta['last_usb_command']
    cdb = bytes.fromhex('fb08000120000001') + b'\xff'*8
    cbw = struct.pack('<4sIIBBB16s', b'USBC', 46, 16, 0x80, 0, 16, cdb)
    csw = struct.pack('<4sIIB', b'USBS', 46, 16, 0)
    require(jump.get('cdb') == cdb.hex() and jump.get('cbw') == cbw.hex() and
            jump.get('csw') == csw.hex() and jump.get('complete') is False,
            'Not the reviewed rejected loader jump')
    data = (folder/'rejected-data-incomplete.bin').read_bytes()
    require(len(data) == 16 and data[:2] == b'\xfb\x08' and
            digest(data) == meta['rejected_data']['sha256'], 'Prepared jump data mismatch')
    return dict(path=str(folder.resolve()), metadata_sha256=digest(raw),
                jump_data_sha256=digest(data), loader_sha256=LOADER_SHA,
                ram_transcript_verified=True, original_jump_status_rejected=True)


class Transport:
    """Fail-closed CDB allowlist; identity, pinned RAM loader and flash reads only."""
    def __init__(self, link):
        self.link = link
        self.loader = None
        self.size = None
        self.verified = set()
        self.read_only = False

    def execute(self, cdb, out=None, n=0):
        cdb = bytes(cdb)
        require(0 < len(cdb) <= 16 and n >= 0 and not (out is not None and n), 'Invalid command')
        op = int.from_bytes(cdb[:2], 'big')
        if self.read_only:
            require(cdb == INQUIRY or op in (0xfc0a, 0xfc0b, 0xfc14, 0xfd05),
                    'Read-loaded session forbids RAM writes and execution')
        addr = int.from_bytes(cdb[2:6], 'big')
        if cdb == INQUIRY:
            require(out is None and n == 36, 'Invalid inquiry')
        else:
            require(self.loader is not None, 'Identity and loader checks required')
            require(len(cdb) == 16, 'Invalid vendor CDB')
            if op in (0xfb06, 0xfd07):
                length = len(out) if out is not None else n
                off = addr - 0x12000
                require(0 <= off < LOADER_SIZE and off % 512 == 0 and length == 512 and off + length <= LOADER_SIZE, 'Invalid RAM bounds')
                require(int.from_bytes(cdb[6:8], 'big') == length, 'Invalid RAM length')
                if op == 0xfb06:
                    require(out == self.loader[off:off+length] and n == 0, 'Only pinned loader bytes permitted')
                    require(cdb[8:11] == b'\0' + binascii.crc_hqx(out, 0).to_bytes(2, 'little') and cdb[11:] == b'\xff'*5, 'Invalid loader CRC/padding')
                    self.verified.discard(off)
                else:
                    require(out is None and cdb[8:] == b'\xff'*8, 'Invalid RAM read')
            elif op == 0xfb08:
                require(cdb[2:] == bytes.fromhex('000120000001') + b'\xff'*8 and out is None and n == 16, 'Invalid RAM jump')
                require(self.verified == set(range(0, LOADER_SIZE, 512)), 'RAM loader not fully verified')
            elif op == 0xfd05:
                require(self.size is not None and out is None and n == 256 and addr % 256 == 0 and addr+n <= self.size, 'Invalid flash read bounds')
                require(cdb[6:] == struct.pack('>H', n) + b'\xff'*8, 'Invalid flash read length')
            else:
                require(op in (0xfc0a, 0xfc0b, 0xfc14) and cdb[2:] == b'\xff'*14 and out is None and n == 16, 'Forbidden command (no flash/fuse writes)')
        data = self.link.execute(cdb, out=out, n=n)
        require(len(data) == n, 'Short reply')
        if op == 0xfd07:
            require(data == self.loader[addr-0x12000:addr-0x12000+n], 'RAM readback mismatch; stopping')
            self.verified.add(addr-0x12000)
        return data

    def command(self, op, args=b'', out=None, n=16):
        return self.execute((op.to_bytes(2, 'big')+args).ljust(16, b'\xff'), out, 0 if out is not None else n)

    def reply(self, op, args=b''):
        data = self.command(op, args)
        require(data[:2] == op.to_bytes(2, 'big'), 'Response opcode mismatch')
        return data[2:]

    def prepare(self, inquiry, loader, record=None):
        require(inquiry[8:16].strip() == b'BR23' and inquiry[16:32].strip() == b'UBOOT1.00', 'Unsupported bootloader; no RAM code loaded')
        require(len(loader) == LOADER_SIZE and digest(loader) == LOADER_SHA, 'Loader hash mismatch')
        self.loader = loader
        if isinstance(self.link, NativeLink):
            self.link.enable_br23_rom_ram(inquiry, loader)
            if record is not None:
                record(dict(rom_ram_residue_policy=ROM_RAM_POLICY))
        ram_commands = []
        print('BR23 identity and pinned loader verified; uploading 11264 bytes to RAM at 0x12000.', flush=True)
        for off in range(0, len(loader), 512):
            block = loader[off:off+512]
            args = struct.pack('>IH', 0x12000+off, len(block))
            self.command(0xfb06, args+b'\0'+binascii.crc_hqx(block, 0).to_bytes(2, 'little'), out=block)
            if isinstance(self.link, NativeLink):
                ram_commands.append(dict(self.link.last_command))
            self.command(0xfd07, args, n=len(block))
            if isinstance(self.link, NativeLink):
                ram_commands.append(dict(self.link.last_command, data_sha256=digest(block)))
        if record is not None:
            record(dict(loader_sha256=LOADER_SHA, loader_address='0x12000',
                        ram_readback_verified=True, ram_commands=ram_commands))
        print('All 22 RAM blocks match. Starting BR23 loader with SPI NOR argument 1.', flush=True)
        jump_reply = self.reply(0xfb08, bytes.fromhex('000120000001'))
        if record is not None and isinstance(self.link, NativeLink):
            record(dict(loader_jump=dict(self.link.last_command),
                        loader_jump_reply=(b'\xfb\x08'+jump_reply).hex()))
        return self.flash_identity(record)

    def flash_identity(self, record=None):
        responses = []
        commands = []
        for op in (0xfc0a, 0xfc0b, 0xfc14):
            responses.append(self.reply(op))
            if isinstance(self.link, NativeLink):
                commands.append(dict(self.link.last_command, reply=(op.to_bytes(2, 'big')+responses[-1]).hex()))
                if record is not None:
                    record(dict(flash_identity_commands=commands))
        online, fid, buf = responses
        replies = dict(online=online.hex(), flash_id=fid.hex(), buffer_size=buf.hex(), loader_sha256=LOADER_SHA, loader_address='0x12000', ram_readback_verified=True)
        if record is not None:
            record(replies)
        print('Flash identity replies:', replies, flush=True)
        jedec = int.from_bytes(online[2:6], 'little')
        require(online[0] == 3 and 0 < jedec <= 0xffffff, 'Invalid SPI NOR identity')
        require(int.from_bytes(fid[:3], 'big') == jedec >> 8, 'Flash identity replies disagree')
        require(16 <= (jedec & 255) <= 24, 'Unknown flash density')
        require(256 <= int.from_bytes(buf[:4], 'big') <= 65535, 'Invalid loader buffer size')
        self.size = 1 << (jedec & 255)
        if isinstance(self.link, NativeLink):
            self.link.enable_br23_flash_reads(self.size)
        print(f'JEDEC {jedec:06x}; flash size {self.size} bytes. Reading twice in 256-byte blocks.', flush=True)
        return dict(replies, jedec_id=f'{jedec:06x}', size=self.size)


def save_json(path, value):
    with path.open('w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def capture(transport, folder):
    hashes = []
    for passno in (1, 2):
        dest = folder/f'flash-pass{passno}.bin'
        with dest.open('xb') as f:
            try:
                for addr in range(0, transport.size, 256):
                    f.write(transport.command(0xfd05, struct.pack('>IH', addr, 256), n=256))
                    if addr % 65536 == 0:
                        print(f'Pass {passno}: {addr:#x}/{transport.size:#x}', flush=True)
                f.flush()
                os.fsync(f.fileno())
            finally:
                if hasattr(os, "fchmod"):
                    os.fchmod(f.fileno(), 0o444)
                else:
                    os.chmod(dest, 0o444)
        data = dest.read_bytes()
        require(len(data) == transport.size and len(set(data)) >= 8, 'Implausible/incomplete readback')
        hashes.append(digest(data))
        print(f'Pass {passno} SHA256: {hashes[-1]}', flush=True)
    require(hashes[0] == hashes[1] and (folder/'flash-pass1.bin').read_bytes() == (folder/'flash-pass2.bin').read_bytes(), 'Full reads differ; backup NOT verified')
    return dict(sha256=hashes[0], passes_match=True, flash_modified=False, complete=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['identify', 'backup', 'read-loaded'])
    p.add_argument('--prepared-backup', type=Path, help='Exact saved verified RAM upload with rejected FB08 status; read-loaded only')
    p.add_argument('--location', required=True, type=lambda s: int(s, 0), help='Observed USB locationID, e.g. 0x00100000')
    p.add_argument('--wait', type=int, default=120, help='Seconds to wait for update mode (1..300)')
    args = p.parse_args()
    require(0 < args.location <= 0xffffffff and 1 <= args.wait <= 300, 'Invalid location/wait')
    require((args.operation == 'read-loaded') == (args.prepared_backup is not None),
            'read-loaded requires --prepared-backup; other operations forbid it')
    loader = (ROOT/'deps/br23loader.bin').read_bytes() if args.operation != 'identify' else None
    prepared = validate_prepared_backup(args.prepared_backup, args.location, loader) if args.prepared_backup else None
    require(sys.platform == 'darwin', 'This initial Ananke probe supports macOS only')
    require(os.geteuid() == 0, 'Run with sudo from your interactive terminal')
    require(sys.stdin.isatty(), 'Use an interactive terminal; background admin launches are unsupported')
    signal.alarm(args.wait+600)
    prefix = 'probe-' if args.operation == 'identify' else 'device-backup-'
    folder = ROOT/(prefix+time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    meta = dict(operation=args.operation, usb_location=hex(args.location), complete=False, flash_modified=False,
                source_hashes={name: digest((ROOT/name).read_bytes()) for name in
                               ('backup_controller.py', 'usb_transport.py', 'native-usb.m', 'native-usb.dylib')})
    save_json(folder/'metadata.json', meta)
    if prepared:
        meta['prepared_source'] = prepared
        save_json(folder/'metadata.json', meta)
    link = None
    try:
        print('Output:', folder, flush=True)
        link = NativeLink.load()
        link.native.gb_set_location.argtypes = [ctypes.c_uint32]
        link.native.gb_set_location(args.location)
        deadline = time.monotonic()+args.wait
        print('Waiting for 4c4a:2342 on the specified physical port. No automatic mode-switch command.', flush=True)
        while not link.try_open():
            require(time.monotonic() < deadline, 'No supported update-mode device at this port')
            time.sleep(0.25)
        transport = Transport(link)
        inquiry = transport.execute(INQUIRY, n=36)
        (folder/'inquiry.bin').write_bytes(inquiry)
        meta.update(inquiry=inquiry.hex(), vendor=inquiry[8:16].decode('ascii', 'replace').strip(), product=inquiry[16:32].decode('ascii', 'replace').strip())
        save_json(folder/'metadata.json', meta)
        print('SCSI identity:', meta['vendor'], meta['product'], flush=True)
        if args.operation == 'identify':
            meta['complete'] = True
        else:
            def record(values):
                meta.update(values)
                save_json(folder/'metadata.json', meta)
            if args.operation == 'read-loaded':
                require(inquiry == BR23_INQUIRY, 'Read-loaded live identity mismatch')
                transport.read_only = True
                transport.loader = loader
                print('Prepared RAM transcript verified. Read-only loader queries and flash reads only.', flush=True)
                meta.update(transport.flash_identity(record=record))
            else:
                meta.update(transport.prepare(inquiry, loader, record=record))
            save_json(folder/'metadata.json', meta)
            meta.update(capture(transport, folder))
        save_json(folder/'metadata.json', meta)
        print('COMPLETE:', args.operation, flush=True)
    except Exception as exc:
        meta['error'] = str(exc)
        if link is not None and link.last_command is not None:
            meta['last_usb_command'] = link.last_command
            if link.last_data is not None:
                dest = folder/'rejected-data-incomplete.bin'
                with dest.open('xb') as f:
                    f.write(link.last_data)
                    f.flush()
                    os.fsync(f.fileno())
                    os.fchmod(f.fileno(), 0o444)
                meta['rejected_data'] = dict(file=dest.name, bytes=len(link.last_data),
                                             sha256=digest(link.last_data), complete=False)
        save_json(folder/'metadata.json', meta)
        raise
    finally:
        if link is not None:
            link.close()
        for item in [folder, *folder.iterdir()]:
            os.chown(item, ROOT.stat().st_uid, -1)
        signal.alarm(0)


if __name__ == '__main__':
    main()
