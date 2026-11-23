#!/usr/bin/env python3
"""Read only the first BR23 loader RAM block after a recorded failed upload.

Separate diagnostic session: INQUIRY, then one FD07 read. No upload, jump,
flash operation, status exception or automatic retry is permitted.
"""
import argparse
import binascii
import ctypes
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time

from backup_controller import INQUIRY, LOADER_SHA, LOADER_SIZE, ROOT, digest, require, save_json
from usb_transport import NativeLink

READ_FIRST_BLOCK = bytes.fromhex('fd07000120000200') + b'\xff' * 8


def validate_failure(folder, location, loader):
    require(len(loader) == LOADER_SIZE and digest(loader) == LOADER_SHA, 'Loader hash mismatch')
    raw = (folder / 'metadata.json').read_bytes()
    meta = json.loads(raw)
    inquiry = (folder / 'inquiry.bin').read_bytes()
    require(len(inquiry) == 36 and inquiry.hex() == meta.get('inquiry'), 'Saved inquiry mismatch')
    require(inquiry[8:16].strip() == b'BR23' and inquiry[16:32].strip() == b'UBOOT1.00',
            'Unsupported saved identity')
    require(meta.get('operation') == 'backup' and meta.get('complete') is False and
            meta.get('flash_modified') is False, 'Expected incomplete backup')
    require(int(meta['usb_location'], 0) == location, 'Failed upload used a different USB location')
    command = meta['last_usb_command']
    expected = (bytes.fromhex('fb0600012000020000') +
                binascii.crc_hqx(loader[:512], 0).to_bytes(2, 'little') + b'\xff' * 5)
    expected_cbw = struct.pack('<4sIIBBB16s', b'USBC', 2, 512, 0, 0, 16, expected)
    expected_csw = struct.pack('<4sIIB', b'USBS', 2, 512, 0)
    require(command.get('cdb') == expected.hex() and command.get('cbw') == expected_cbw.hex() and
            command.get('csw') == expected_csw.hex() and command.get('complete') is False and
            command.get('stage') == 'status', 'Not the reviewed first-block residue failure')
    return dict(path=str(folder.resolve()), metadata_sha256=digest(raw),
                inquiry_sha256=digest(inquiry), loader_sha256=LOADER_SHA)


class ReadOnlyProbe:
    """An exact two-command sequence, including the normal strict BOT checks."""
    def __init__(self, link):
        self.link = link
        self.step = 0

    def execute(self, cdb, out=None, n=0):
        expected = ((INQUIRY, 36), (READ_FIRST_BLOCK, 512))
        require(self.step < len(expected) and out is None and
                (bytes(cdb), n) == expected[self.step], 'Forbidden diagnostic command')
        # Consume the step before I/O, so failure cannot silently retry it.
        self.step += 1
        try:
            data = self.link.execute(cdb, n=n)
            require(len(data) == n, 'Short diagnostic reply')
            if cdb == INQUIRY:
                require(data[8:16].strip() == b'BR23' and data[16:32].strip() == b'UBOOT1.00',
                        'Unsupported live identity')
            return data
        except BaseException:
            self.step = len(expected)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--failed-backup', type=Path, required=True)
    parser.add_argument('--location', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--wait', type=int, default=3)
    args = parser.parse_args()
    require(0 < args.location <= 0xffffffff and 1 <= args.wait <= 30, 'Invalid location/wait')
    loader = (ROOT / 'deps/br23loader.bin').read_bytes()
    source = validate_failure(args.failed_backup, args.location, loader)
    require(sys.platform == 'darwin', 'macOS only')
    require(os.geteuid() == 0 and sys.stdin.isatty(), 'Run with sudo from your interactive terminal')
    folder = ROOT / ('ram-probe-' + time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    meta = dict(operation='diagnose-first-upload', complete=False, flash_modified=False,
                ram_written=False, loader_executed=False, usb_location=hex(args.location),
                source_failure=source, address='0x12000', bytes=512,
                prior_status_mismatch_resolved=False,
                source_hashes={name: digest((ROOT / name).read_bytes()) for name in
                               ('diagnose_upload.py', 'backup_controller.py', 'usb_transport.py',
                                'native-usb.m', 'native-usb.dylib')})
    save_json(folder / 'metadata.json', meta)
    signal.alarm(args.wait + 90)
    link = None
    try:
        print('Output:', folder, flush=True)
        print('Read-only diagnostic: INQUIRY then 512 RAM bytes; no loader execution.', flush=True)
        link = NativeLink.load()
        link.native.gb_set_location.argtypes = [ctypes.c_uint32]
        link.native.gb_set_location(args.location)
        deadline = time.monotonic() + args.wait
        while not link.try_open():
            require(time.monotonic() < deadline, 'No supported update-mode device at this port')
            time.sleep(0.25)
        probe = ReadOnlyProbe(link)
        inquiry = probe.execute(INQUIRY, n=36)
        (folder / 'inquiry.bin').write_bytes(inquiry)
        meta['inquiry'] = inquiry.hex()
        save_json(folder / 'metadata.json', meta)
        data = probe.execute(READ_FIRST_BLOCK, n=512)
        with (folder / 'ram-12000.bin').open('xb') as dest:
            dest.write(data)
            dest.flush()
            os.fsync(dest.fileno())
            os.fchmod(dest.fileno(), 0o444)
        meta.update(sha256=digest(data), expected_sha256=digest(loader[:512]),
                    matches_pinned_loader=data == loader[:512])
        save_json(folder / 'metadata.json', meta)
        require(meta['matches_pinned_loader'], 'RAM differs from pinned first block; diagnostic stopped')
        meta['complete'] = True
        save_json(folder / 'metadata.json', meta)
        print('RAM matches the pinned first block. Prior USB residue mismatch remains unresolved; stopped.', flush=True)
    except Exception as exc:
        meta['error'] = str(exc)
        if link is not None and link.last_command is not None:
            meta['last_usb_command'] = link.last_command
            if link.last_command['cdb'] == READ_FIRST_BLOCK.hex() and link.last_data is not None:
                # Retain rejected bytes as incomplete evidence, never as a successful read.
                data = link.last_data
                with (folder / 'ram-12000-incomplete.bin').open('xb') as dest:
                    dest.write(data)
                    dest.flush()
                    os.fsync(dest.fileno())
                    os.fchmod(dest.fileno(), 0o444)
                meta['rejected_data'] = dict(file='ram-12000-incomplete.bin', bytes=len(data),
                                             sha256=digest(data), expected_sha256=digest(loader[:512]),
                                             matches_pinned_loader=data == loader[:512],
                                             usb_status_valid=False)
                print('Rejected RAM data saved as incomplete evidence; matches pinned block:',
                      data == loader[:512], flush=True)
        save_json(folder / 'metadata.json', meta)
        raise
    finally:
        if link is not None:
            link.close()
        for item in [folder, *folder.iterdir()]:
            os.chown(item, ROOT.stat().st_uid, -1)
        signal.alarm(0)


if __name__ == '__main__':
    main()
