#!/usr/bin/env python3
"""One-unit experimental BR23 installation. Separate from the backup allowlist.

Requires explicit acceptance of unproven recovery. Only the pinned candidate,
4 KiB changed application sectors, and 256-byte pages are writable. No chip
erase, fuse, protection-register write, automatic retry or reset command.
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

from backup_controller import Transport, INQUIRY, ROOT, digest, require, save_json
from usb_transport import NativeLink, BR23_INQUIRY, LinkError

ORIGINAL_SHA = 'da281f118ea0e3dc412b2298ce27c1b73a9cf6bca795814708e900a20a9538bc'
METADATA_SHA = 'c3caa88d12d125ebf63d00f0ded5fa6387f9239534478f052e2ca362cc3cd520'
CANDIDATE_SHA = '574f6542ef749741721d8bf040aa0b45eb8837d9357b900865473400027d2c59'
PREVIOUS_SHA = 'a93b93a788452026e2b155a8797805ef7d1d55be0af1e2eb7fcdd9fda49388d3'
PREVIOUS = ROOT/'flash-attempt-20261104-100838/after.bin'
BACKUP = ROOT/'device-backup-20261103-174931'
SIZE, SECTOR, PAGE = 0x100000, 4096, 256
AREA_START, AREA_END = 0x3020, 0x3020 + 0x5415c
SECTORS = tuple(range(0x4000, 0x57000, SECTOR)) + (0x3000,)
WRITE_POLICY = 'br23-pinned-loader-application-write-full-residue-v1'


def load_inputs():
    raw = (BACKUP/'metadata.json').read_bytes()
    require(digest(raw) == METADATA_SHA, 'Original backup metadata changed')
    meta = json.loads(raw)
    require(meta['complete'] and meta['passes_match'] and not meta['flash_modified'],
            'Original backup incomplete')
    originals = [(BACKUP/name).read_bytes() for name in ('flash-pass1.bin', 'flash-pass2.bin')]
    require(originals[0] == originals[1] and len(originals[0]) == meta['size'] == SIZE and
            digest(originals[0]) == meta['sha256'] == ORIGINAL_SHA, 'Original backups mismatch')
    for name in ('flash-pass1.bin', 'flash-pass2.bin', 'metadata.json'):
        require((BACKUP/name).stat().st_mode & 0o222 == 0, 'Original must remain read-only')
    candidate = (ROOT/'cfw-candidate/ananke-v0900-gatt-experimental.bin').read_bytes()
    require(len(candidate) == SIZE and digest(candidate) == CANDIDATE_SHA, 'Wrong candidate')
    original = originals[0]
    require(candidate[:AREA_START] == original[:AREA_START] and
            candidate[AREA_END:] == original[AREA_END:], 'Out-of-area candidate mutation')
    sectors = {a for a in range(0, SIZE, SECTOR) if candidate[a:a+SECTOR] != original[a:a+SECTOR]}
    require(sectors == set(SECTORS), 'Unexpected changed sectors')
    return original, candidate


def make_plan(original, candidate, live):
    require(len(live) == len(original) == len(candidate) == SIZE, 'Wrong image length')
    require(digest(original) == ORIGINAL_SHA and digest(candidate) == CANDIDATE_SHA,
            'Unpinned source images')
    # Stock application, map, bootloader and resource must match. Mutable
    # settings farther up flash are preserved from the fresh full reads.
    previous = PREVIOUS.read_bytes()
    require(len(previous) == SIZE and digest(previous) == PREVIOUS_SHA,
            'Previous verified installation readback changed')
    require(live[:AREA_END] in (original[:AREA_END], previous[:AREA_END]),
            'Live boot/application differs from original or verified previous installation')
    desired = live[:AREA_START] + candidate[AREA_START:AREA_END] + live[AREA_END:]
    require(all(desired[a:a+SECTOR] == live[a:a+SECTOR]
                for a in range(0, SIZE, SECTOR) if a not in SECTORS), 'Unplanned sector change')
    return desired


def changed_sectors(before, desired):
    require(len(before) == len(desired) == SIZE, 'Invalid plan image size')
    changed = {a for a in range(0, SIZE, SECTOR) if before[a:a+SECTOR] != desired[a:a+SECTOR]}
    require(changed <= set(SECTORS), 'Change outside allowed application sectors')
    return tuple(a for a in SECTORS if a in changed)


class InstallLink(NativeLink):
    """Additional allowlist; the backup Transport itself remains read-only."""
    def __init__(self, native):
        super().__init__(native)
        self.pending_write = None

    def expected_residue(self, cdb, out, n):
        op = int.from_bytes(cdb[:2], 'big')
        if op in (0xfb01, 0xfb04):
            if self.flash_read_size != SIZE or self.pending_write != (cdb, out, n):
                raise LinkError('Write not armed for this exact command/data')
            addr = int.from_bytes(cdb[2:6], 'big')
            if op == 0xfb01:
                valid = (addr in SECTORS and out is None and n == 16 and
                         cdb == b'\xfb\x01' + struct.pack('>I', addr) + b'\xff'*10)
            else:
                valid = (out is not None and len(out) == PAGE and n == 0 and addr % PAGE == 0 and
                         addr // SECTOR * SECTOR in SECTORS and
                         cdb == b'\xfb\x04'+struct.pack('>IH', addr, PAGE)+b'\0'+
                         binascii.crc_hqx(out, 0).to_bytes(2, 'little')+b'\xff'*5)
            if not valid:
                raise LinkError('Invalid sector/page write framing or bounds')
            # The pinned hook consumes the data through ROM callbacks without
            # updating the CBW transfer count, as on the verified loader reads.
            # Require full residue, signature/tag/status and exact readback.
            return n if out is None else len(out)
        if cdb != INQUIRY and op not in (0xfb06, 0xfd07, 0xfb08, 0xfc0a, 0xfc0b, 0xfc14, 0xfd05):
            raise LinkError('Command forbidden by experimental installer')
        return super().expected_residue(cdb, out, n)


def read_range(transport, address, size):
    return b''.join(transport.command(0xfd05, struct.pack('>IH', a, PAGE), n=PAGE)
                    for a in range(address, address+size, PAGE))


def read_full(transport, path):
    with path.open('xb') as f:
        try:
            for a in range(0, SIZE, PAGE):
                f.write(read_range(transport, a, PAGE))
                if a % 0x20000 == 0:
                    print(f'{path.name}: {a:#x}/{SIZE:#x}', flush=True)
            f.flush()
            os.fsync(f.fileno())
        finally:
            if hasattr(os, "fchmod"):
                os.fchmod(f.fileno(), 0o444)
            else:
                os.chmod(path, 0o444)
    return path.read_bytes()


class Writer:
    def __init__(self, link, reader, before, desired, journal):
        self.link, self.reader = link, reader
        require(len(before) == len(desired) == SIZE, 'Invalid writer image size')
        self.before, self.desired, self.journal = bytes(before), bytes(desired), journal
        self.sectors = changed_sectors(self.before, self.desired)
        self.attempted = set()

    def command(self, cdb, out=None, n=0):
        require(self.link.pending_write is None, 'Nested write')
        self.journal(dict(event='command-start', cdb=cdb.hex(),
                          data_sha256=digest(out) if out is not None else None))
        self.link.pending_write = (cdb, out, n)
        try:
            data = self.link.execute(cdb, out=out, n=n)
            require(len(data) == n, 'Short write acknowledgement')
            if n:
                require(data[:2] == cdb[:2], 'Write acknowledgement opcode mismatch')
            self.link.last_command['residue_policy'] = WRITE_POLICY
            self.journal(dict(event='command-complete', command=self.link.last_command))
            return data
        finally:
            self.link.pending_write = None

    def sector(self, address):
        require(address in self.sectors and address not in self.attempted, 'Invalid/repeated sector')
        require(read_range(self.reader, address, SECTOR) == self.before[address:address+SECTOR],
                'Sector changed since preflight')
        self.attempted.add(address)
        self.command(b'\xfb\x01'+struct.pack('>I', address)+b'\xff'*10, n=16)
        require(read_range(self.reader, address, SECTOR) == b'\xff'*SECTOR,
                'Sector did not erase completely; stopping')
        for a in range(address, address+SECTOR, PAGE):
            block = self.desired[a:a+PAGE]
            cdb = b'\xfb\x04'+struct.pack('>IH', a, PAGE)+b'\0'+binascii.crc_hqx(block, 0).to_bytes(2, 'little')+b'\xff'*5
            self.command(cdb, out=block)
            require(read_range(self.reader, a, PAGE) == block, 'Program readback mismatch; stopping')
        require(read_range(self.reader, address, SECTOR) == self.desired[address:address+SECTOR],
                'Final sector mismatch')
        self.journal(dict(event='sector-verified', address=hex(address),
                          sha256=digest(self.desired[address:address+SECTOR])))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--location', required=True, type=lambda x: int(x, 0))
    p.add_argument('--wait', type=int, default=3)
    p.add_argument('--accept-unrecoverable-risk', action='store_true')
    args = p.parse_args()
    require(args.accept_unrecoverable_risk, 'Explicit experimental risk acceptance required')
    require(0 < args.location <= 0xffffffff and 1 <= args.wait <= 30, 'Invalid target/wait')
    original, candidate = load_inputs()
    require(sys.platform == 'darwin' and os.geteuid() == 0 and sys.stdin.isatty(),
            'Requires macOS sudo in an interactive terminal')
    folder = ROOT/('flash-attempt-'+time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(mode=0o700)
    meta = dict(complete=False, flash_write_attempted=False, flashed=False,
                usb_location=hex(args.location), candidate_sha256=CANDIDATE_SHA,
                independent_recovery=False, unrecoverable_risk_explicitly_accepted=True,
                source_hashes={name: digest((ROOT/name).read_bytes()) for name in
                    ('flash_controller.py', 'backup_controller.py', 'usb_transport.py', 'native-usb.m', 'native-usb.dylib')})
    link = None
    def record(values):
        meta.update(values)
        save_json(folder/'metadata.json', meta)
    def journal(event):
        with (folder/'commands.jsonl').open('a') as f:
            f.write(json.dumps(event)+'\n'); f.flush(); os.fsync(f.fileno())
    signal.alarm(600 + args.wait)
    record({})
    try:
        print('Output:', folder, flush=True)
        link = InstallLink.load()
        link.native.gb_set_location.argtypes = [ctypes.c_uint32]
        link.native.gb_set_location(args.location)
        deadline = time.monotonic()+args.wait
        while not link.try_open():
            require(time.monotonic() < deadline, 'No update-mode controller at target port')
            time.sleep(.25)
        reader = Transport(link)
        inquiry = reader.execute(INQUIRY, n=36)
        require(inquiry == BR23_INQUIRY, 'Live identity mismatch')
        record(dict(inquiry=inquiry.hex()))
        record(reader.prepare(inquiry, (ROOT/'deps/br23loader.bin').read_bytes(), record))
        before = read_full(reader, folder/'before-pass1.bin')
        second = read_full(reader, folder/'before-pass2.bin')
        require(before == second, 'Fresh full reads disagree')
        desired = make_plan(original, candidate, before)
        sectors = changed_sectors(before, desired)
        with (folder/'desired.bin').open('xb') as f:
            f.write(desired); f.flush(); os.fsync(f.fileno()); os.fchmod(f.fileno(), 0o444)
        record(dict(before_sha256=digest(before), before_passes_match=True,
                    desired_sha256=digest(desired), sectors=[hex(a) for a in sectors]))
        writer = Writer(link, reader, before, desired, journal)
        print(f'Preflight verified. Writing {len(sectors)} application sectors; header sector last.', flush=True)
        record(dict(flash_write_attempted=bool(sectors)))
        for i, address in enumerate(sectors):
            writer.sector(address)
            record(dict(verified_sectors=i+1, last_verified_sector=hex(address)))
            print(f'Verified sector {i+1}/{len(sectors)}: {address:#x}', flush=True)
        after = read_full(reader, folder/'after.bin')
        require(after == desired, 'Full post-flash readback mismatch')
        record(dict(complete=True, flashed=True, full_readback_verified=True, after_sha256=digest(after)))
        print('FLASH VERIFIED. No reset command sent; close/reconnect for normal boot.', flush=True)
    except Exception as exc:
        record(dict(error=str(exc), last_usb_command=link.last_command if link else None))
        print('STOPPED:', exc, flush=True)
        raise
    finally:
        if link:
            link.close()
        for path in [*folder.iterdir(), folder]:
            os.chown(path, ROOT.stat().st_uid, -1)
        signal.alarm(0)


if __name__ == '__main__':
    main()
