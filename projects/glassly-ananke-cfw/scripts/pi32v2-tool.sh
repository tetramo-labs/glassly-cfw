#!/bin/sh
# Pinned Jieli Linux tools; analysis outputs only, with no device/network access.
set -eu
cd "$(dirname "$0")/.."
project_dir=$(pwd)
toolchain_dir=$(cd ../glassly-mini-gamepad/.tools/jieli/jieli-linux-toolchains-20260730.1 && pwd)
python3 - "$toolchain_dir" <<'PY'
import hashlib
from pathlib import Path
import sys
root = Path(sys.argv[1])
expected = {'clang': 'c45189ee624de0430deb0db02e6dce171fb5538e7fe323e3964dc8ac6236240f',
            'objdump': 'f7e449e2c8001d5ed4493a45d1f5f304c8910418e4074acdc8715079ef64e08a'}
for name, digest in expected.items():
    if hashlib.sha256((root/'common/bin'/name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Pinned tool hash mismatch: ' + name)
if hashlib.sha256((root/'pi32v2/bin/ld').read_bytes()).hexdigest() != 'fd61aff15616bb6f6b58fd2e9ede7af741c7bf05facb3e0cb3d3c9817c268fd9':
    raise SystemExit('Pinned linker hash mismatch')
PY
mkdir -p research/pi32v2-analysis
exec docker run --rm --platform linux/amd64 --network none --cap-drop ALL \
  --security-opt no-new-privileges \
  --mount "type=bind,src=$toolchain_dir,dst=/opt/jieli,readonly" \
  --mount "type=bind,src=$project_dir,dst=/work,readonly" \
  --mount "type=bind,src=$project_dir/research/pi32v2-analysis,dst=/work/research/pi32v2-analysis" \
  -w /work -e PATH=/opt/jieli/pi32v2/bin:/opt/jieli/common/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  debian@sha256:cba95a21c96c1f5fc2470081829363eed57706634f7dc26e8c6712934303d57a "$@"
