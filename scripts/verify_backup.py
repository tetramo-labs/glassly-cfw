#!/usr/bin/env python3
"""Verify saved originals without opening USB."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('backup', type=Path)
a = p.parse_args()
metadata = a.backup/('backup.json' if (a.backup/'backup.json').exists() else 'metadata.json')
m = json.loads(metadata.read_text())
if not (m.get('complete') is True and m.get('passes_match') is True and m.get('flash_modified') is False):
    p.exit(1, 'Backup was not marked complete and verified.\n')
first = None
names = m.get('files', ['flash-pass1.bin', 'flash-pass2.bin'])
if names not in (['flash-pass1.bin', 'flash-pass2.bin'], ['before-pass1.bin', 'before-pass2.bin']):
    p.exit(1, 'Unexpected backup file names.\n')
for name in names:
    data = (a.backup/name).read_bytes()
    if len(data) != m['size'] or hashlib.sha256(data).hexdigest() != m['sha256']:
        p.exit(1, f'{name}: size/hash mismatch\n')
    if first is not None and data != first:
        p.exit(1, 'Full reads differ\n')
    first = data
print(f"Verified both full reads: {m['size']} bytes, SHA256 {m['sha256']}")
