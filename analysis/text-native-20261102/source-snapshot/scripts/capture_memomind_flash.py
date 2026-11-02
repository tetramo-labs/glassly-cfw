#!/usr/bin/env python3
"""Save fixed, read-only flash regions from the optional acquisition firmware.

Default is query-only. Named --region options opt into reads. Captures have a
durable chunk journal and a completion manifest; interrupted files stay partial.
An independently known app-header prefix is required before other regions.
This does not install firmware or invoke write/erase functions.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from memomind_flash_read import FlashReadClient, REGIONS, PROFILE, PROFILES
from memomind_transport import RfcommBridge
from probe_memomind import probe


def private_file(path, mode='wb'):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), mode)


def sync(output):
    output.flush()
    os.fsync(output.fileno())


def acquire(client, regions, output, save, *, expected_app_prefix=None):
    """output exists, save(row) must fsync; no read retries or partial resumption."""
    regions = list(regions)
    allowed = client.regions
    if len(set(regions)) != len(regions) or any(name not in allowed for name in regions):
        raise ValueError('Select distinct named acquisition regions')
    if expected_app_prefix is not None and (
            type(expected_app_prefix) is not bytes or not 32 <= len(expected_app_prefix) <= 256):
        raise ValueError('Known app-header prefix must contain 32..256 bytes')
    if any(name != 'app-header' for name in regions) and expected_app_prefix is None:
        raise ValueError('Acquire and independently verify the app header before other regions')
    # Avoid beginning any read if an output would be overwritten.
    names = list(regions)
    if regions and 'app-header' not in names:
        names.insert(0, 'app-header')
    elif 'app-header' in names:
        names.remove('app-header')
        names.insert(0, 'app-header')
    for name in names:
        if (output / (name + '.bin')).exists():
            raise FileExistsError(name + '.bin')
    identity = client.query()
    save({'kind': 'query', 'reply': identity})
    artifacts = []
    for name in names:
        device, start, end = allowed[name]
        digest = hashlib.sha256()
        path = output / (name + '.bin')
        with private_file(path) as binary:
            for offset in range(start, end, 256):
                length = min(256, end - offset)
                save({'kind': 'read-intent', 'region': name, 'device': device,
                      'offset': offset, 'length': length})
                raw = client.read(device, offset, length)
                if type(raw) is not bytes or len(raw) != length:
                    raise ValueError('Flash client returned an incomplete chunk')
                binary.write(raw)
                sync(binary)
                digest.update(raw)
                save({'kind': 'chunk', 'region': name, 'device': device, 'offset': offset,
                      'file_offset': offset - start, 'length': length,
                      'sha256': hashlib.sha256(raw).hexdigest()})
                if name == 'app-header' and expected_app_prefix is not None:
                    if not raw.startswith(expected_app_prefix):
                        raise ValueError('App-header mismatch; unknown flash regions were not read')
                    save({'kind': 'app-header-verified', 'prefix_bytes': len(expected_app_prefix),
                          'prefix_sha256': hashlib.sha256(expected_app_prefix).hexdigest()})
        artifacts.append({'path': path.name, 'device': device, 'start': start, 'end': end,
                          'bytes': end - start, 'sha256': digest.hexdigest()})
        save({'kind': 'region-complete', 'artifact': artifacts[-1]})
    return {'format': 'memomind-flash-acquisition-v1', 'complete': True,
            'profile': identity, 'requested_regions': regions, 'artifacts': artifacts,
            'app_header_verified': bool(regions and expected_app_prefix is not None),
            'flash_mutations': 0, 'automatic_retries': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=38741)
    parser.add_argument('--output', type=Path, required=True, help='New private directory')
    parser.add_argument('--profile', choices=tuple(PROFILES), default=PROFILE)
    parser.add_argument('--region', choices=tuple(sorted({name for ranges in PROFILES.values() for name in ranges})), action='append', default=[])
    parser.add_argument('--expected-app-prefix', type=Path, help='Independently known 32..256 header bytes')
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error('timeout must be positive and at most 60 seconds')
    expected = args.expected_app_prefix.read_bytes() if args.expected_app_prefix else None
    if expected is not None and not 32 <= len(expected) <= 256:
        parser.error('expected-app-prefix must contain 32..256 bytes')
    if any(name != 'app-header' for name in args.region) and expected is None:
        parser.error('Non-header regions require --expected-app-prefix')
    if len(set(args.region)) != len(args.region):
        parser.error('Duplicate region')
    if any(name not in PROFILES[args.profile] for name in args.region):
        parser.error('Region is not present in the selected profile')
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    with private_file(args.output / 'journal.jsonl', 'w') as journal:
        def save(row):
            journal.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), **row}) + '\n')
            sync(journal)
        try:
            with RfcommBridge(args.host, args.port, timeout=args.timeout,
                              trace=lambda row: save({'kind': 'wire', 'data': row})) as transport:
                baseline = probe(transport, args.address, legacy_repeat_fa=True)
                save({'kind': 'stock-baseline', 'result': baseline})
                result = acquire(FlashReadClient(transport, timeout=args.timeout, profile=args.profile), args.region,
                                 args.output, save, expected_app_prefix=expected)
            with private_file(args.output / 'manifest.json', 'w') as manifest:
                manifest.write(json.dumps(result, indent=2) + '\n')
                sync(manifest)
        except Exception as exc:
            save({'kind': 'failed', 'complete': False, 'error_type': type(exc).__name__,
                  'error': str(exc), 'automatic_retries': 0})
            raise
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
