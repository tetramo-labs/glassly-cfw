#!/usr/bin/env python3
"""Prepare macOS backup helper from the pinned, already-local Gamebrick dependency."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'adb3f18889e88ac512ce0a3c4d8cc3d3cb30696a'
SHA = '7384429e33ee1f340fbffe46aa928a0099c163e1374a40f6f9f27468a6f16ddf'

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--reference', type=Path, default=ROOT.parent/'glassly-mini-gamepad')
args = p.parse_args()
if sys.platform != 'darwin':
    sys.exit('This initial backup workflow supports macOS only.')
repo = args.reference.resolve()/'research/jl-uboot-tool'
head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
if head != COMMIT:
    sys.exit('Reference dependency revision mismatch; stopping.')
data = (repo/'data/loaderblobs/usb/br23loader.bin').read_bytes()
if len(data) != 11264 or hashlib.sha256(data).hexdigest() != SHA:
    sys.exit('Reference loader hash mismatch; stopping.')
target = ROOT/'research/deps/br23loader.bin'
target.parent.mkdir(exist_ok=True)
if target.exists():
    if target.read_bytes() != data:
        sys.exit('Existing local loader differs; refusing to overwrite.')
else:
    with target.open('xb') as f:
        f.write(data)
subprocess.run(['clang', '-fobjc-arc', '-dynamiclib', '-framework', 'Foundation', '-framework', 'IOKit', '-framework', 'IOUSBHost', str(ROOT/'research/native-usb.m'), '-o', str(ROOT/'research/native-usb.dylib')], check=True, timeout=60)
print('Pinned RAM loader verified; native helper compiled. No device accessed.')
