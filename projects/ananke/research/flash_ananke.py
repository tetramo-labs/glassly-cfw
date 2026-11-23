#!/usr/bin/env python3
"""Experimental Ananke Gen 2 backup/install/restore with verified per-unit plans."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import time

from ananke_flasher import applications, plan
from backup_controller import Transport, INQUIRY, ROOT, digest, require, save_json
from flash_controller import InstallLink, Writer, read_full, changed_sectors
from usb_transport import BR23_INQUIRY, PyUsbLink, list_usb_targets


class PyUsbInstallLink(InstallLink, PyUsbLink):
    def __init__(self, target):
        PyUsbLink.__init__(self, target)
        self.pending_write = None


def target_pair(value):
    try:
        bus, address = (int(part, 10) for part in value.split(':'))
        if bus < 0 or address < 0:
            raise ValueError()
        return bus, address
    except ValueError:
        raise argparse.ArgumentTypeError('Expected decimal BUS:ADDRESS from --list')


def readonly(path, data):
    with path.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    path.chmod(0o444)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', nargs='?', choices=['identify', 'backup', 'install', 'restore'])
    p.add_argument('--list', action='store_true', help='List Windows/Linux libusb target addresses; no interface claim')
    targets = p.add_mutually_exclusive_group()
    targets.add_argument('--location', type=lambda value: int(value, 0), help='macOS physical USB locationID')
    targets.add_argument('--device', type=target_pair, help='Windows/Linux decimal BUS:ADDRESS from --list')
    p.add_argument('--wait', type=int, default=3)
    p.add_argument('--ufw', type=Path, help='Official IG05_V0900.ufw; required for install/restore')
    p.add_argument('--accept-unrecoverable-risk', action='store_true')
    args = p.parse_args()
    if args.list:
        require(sys.platform != 'darwin', 'On macOS use system_profiler SPUSBDataType for locationID')
        for target in list_usb_targets():
            print(f"{target['bus']}:{target['address']}  {target['vid']}:{target['pid']}")
        return
    require(args.operation is not None and 1 <= args.wait <= 30, 'Operation and wait between 1 and 30 required')
    require(sys.stdin.isatty(), 'Run USB operations in an interactive terminal')
    if sys.platform == 'darwin':
        require(args.location is not None and 0 < args.location <= 0xffffffff and args.device is None,
                'macOS requires an explicit --location')
        require(os.geteuid() == 0, 'Run with sudo in your terminal')
    else:
        require(sys.platform.startswith('linux') or sys.platform == 'win32', 'Unsupported OS')
        require(args.device is not None and args.location is None, 'Windows/Linux requires --device BUS:ADDRESS')
    stock = custom = None
    if args.operation in ('install', 'restore'):
        require(args.accept_unrecoverable_risk, 'Experimental firmware has no demonstrated independent recovery; explicit risk acceptance required')
        require(args.ufw is not None, '--ufw IG05_V0900.ufw required')
        stock, custom = applications(args.ufw)
    # A unique local output directory is retained even on failures.
    folder = ROOT/('flash-attempt-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
    folder.mkdir(mode=0o700)
    meta = dict(operation=args.operation, complete=False, backup_complete=False,
                flash_write_attempted=False, flash_modified=False, size=0x100000,
                target=args.device if args.device else hex(args.location), platform=sys.platform,
                source_hashes={name: digest((ROOT/name).read_bytes()) for name in
                               ('flash_ananke.py', 'ananke_flasher.py', 'flash_controller.py', 'usb_transport.py', 'backup_controller.py')})
    link = None
    def record(values):
        meta.update(values)
        save_json(folder/'metadata.json', meta)
    def journal(event):
        with (folder/'commands.jsonl').open('a') as f:
            f.write(json.dumps(event)+'\n'); f.flush(); os.fsync(f.fileno())
    def expired():
        # No further USB commands after the watchdog; retained metadata stays incomplete.
        os._exit(124)
    watchdog = threading.Timer(600 + args.wait, expired)
    watchdog.daemon = True
    record({})
    watchdog.start()
    print('Output:', folder, flush=True)
    try:
        if sys.platform == 'darwin':
            link = InstallLink.load()
            link.native.gb_set_location.argtypes = [ctypes.c_uint32]
            link.native.gb_set_location(args.location)
        else:
            link = PyUsbInstallLink(args.device)
        deadline = time.monotonic() + args.wait
        while not link.try_open():
            require(time.monotonic() < deadline, 'No update-mode controller at explicit target')
            time.sleep(.25)
        reader = Transport(link)
        inquiry = reader.execute(INQUIRY, n=36)
        require(inquiry == BR23_INQUIRY, 'Unexpected identity; no loader uploaded')
        record(dict(inquiry=inquiry.hex()))
        print('BR23 / UBOOT1.00 identity verified.', flush=True)
        if args.operation == 'identify':
            record(dict(complete=True))
            return
        record(reader.prepare(inquiry, (ROOT/'deps/br23loader.bin').read_bytes(), record))
        before = read_full(reader, folder/'before-pass1.bin')
        second = read_full(reader, folder/'before-pass2.bin')
        require(before == second, 'Full backup reads disagree; no flash write')
        require(len(set(before)) >= 8, 'Implausible flash contents; retain incomplete capture')
        # Separate immutable backup metadata stays valid even if a later installation fails.
        backup_meta = dict(complete=True, passes_match=True, flash_modified=False, size=len(before), sha256=digest(before),
                           files=['before-pass1.bin', 'before-pass2.bin'], inquiry=inquiry.hex())
        readonly(folder/'backup.json', (json.dumps(backup_meta, indent=2)+'\n').encode())
        record(dict(backup_complete=True, before_sha256=digest(before), passes_match=True))
        if args.operation == 'backup':
            record(dict(complete=True))
            print('BACKUP VERIFIED. Reconnect for normal boot.', flush=True)
            return
        desired = plan(before, stock, custom, args.operation)
        sectors = changed_sectors(before, desired)
        readonly(folder/'desired.bin', desired)
        record(dict(desired_sha256=digest(desired), sectors=[hex(a) for a in sectors]))
        writer = Writer(link, reader, before, desired, journal)
        print(f'Preflight verified. Writing {len(sectors)} application sectors; header last.', flush=True)
        record(dict(flash_write_attempted=bool(sectors), flash_modified=bool(sectors)))
        for i, address in enumerate(sectors):
            writer.sector(address)
            record(dict(verified_sectors=i+1))
            print(f'Verified sector {i+1}/{len(sectors)}: {address:#x}', flush=True)
        after = read_full(reader, folder/'after.bin')
        require(after == desired, 'Full flash readback mismatch; stop')
        record(dict(complete=True, full_readback_verified=True, after_sha256=digest(after)))
        print('FLASH VERIFIED. Reconnect for normal boot; Pair + Right for Glassly.', flush=True)
    except BaseException as exc:
        record(dict(error=str(exc), last_usb_command=link.last_command if link else None))
        raise
    finally:
        try:
            if link:
                link.close()
        finally:
            watchdog.cancel()
            if sys.platform != 'win32' and os.geteuid() == 0:
                uid = int(os.environ.get('SUDO_UID', ROOT.stat().st_uid))
                for path in [*folder.iterdir(), folder]:
                    os.chown(path, uid, -1)


if __name__ == '__main__':
    main()
