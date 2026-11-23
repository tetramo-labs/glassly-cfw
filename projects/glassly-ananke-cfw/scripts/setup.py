#!/usr/bin/env python3
"""Fetch pinned public dependencies and prepare the platform USB transport. No device access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(list(map(str, args)), check=True, timeout=180)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, help='Optional existing Gamebrick checkout to copy pinned dependencies from')
    args = parser.parse_args()
    lock = json.loads((ROOT/'sources.lock.json').read_text())
    for field, name in [('jl_uboot_tool', 'jl-uboot-tool'), ('jl_misctools', 'jl-misctools')]:
        pin = lock[field]
        repo = ROOT/'research'/name
        if not repo.exists():
            source = args.reference/'research'/name if args.reference else pin['url']
            run('git', 'clone', '--no-checkout', source, repo)
            run('git', '-C', repo, 'checkout', '--detach', pin['commit'])
        head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
        if head != pin['commit'] or subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], timeout=10).strip():
            sys.exit(f'{name} must be clean at pinned revision {pin["commit"]}')
    data = (ROOT/'research/jl-uboot-tool/data/loaderblobs/usb/br23loader.bin').read_bytes()
    pin = lock['br23_loader_review']
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        sys.exit('Loader hash mismatch')
    target = ROOT/'research/deps/br23loader.bin'
    target.parent.mkdir(exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        sys.exit('Existing loader differs')
    target.write_bytes(data)
    env = ROOT/'.venv'
    if not env.exists():
        venv.create(env, with_pip=True)
    python = env/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    run(python, '-m', 'pip', 'install', '-r', ROOT/'requirements.txt')
    if sys.platform == 'darwin':
        run('clang', '-fobjc-arc', '-dynamiclib', '-framework', 'Foundation', '-framework', 'IOKit',
            '-framework', 'IOUSBHost', ROOT/'research/native-usb.m', '-o', ROOT/'research/native-usb.dylib')
    print('Setup complete. No device accessed. See README.md for the explicit target and platform driver setup.')


if __name__ == '__main__':
    main()
