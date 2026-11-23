#!/usr/bin/env python3
"""Exercise the native record carrier with bounded allocators and sanitizers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = ['runtime/graphics/tests/test_record_session.c',
               'runtime/graphics/record_session.c', 'runtime/portable/transport.c',
               'runtime/portable/inflater.c']
    vendor = ROOT / 'runtime/vendor/zlib'
    pin = json.loads((vendor / 'UPSTREAM.json').read_text())
    for name, digest in pin['files'].items():
        assert hashlib.sha256((vendor / name).read_bytes()).hexdigest() == digest, name
    sources += ['runtime/vendor/zlib/' + n + '.c'
                for n in ('inflate', 'inffast', 'inftrees', 'adler32', 'zutil')]
    command = ['clang', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
               '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
               '-DZ_SOLO', '-DNO_GZIP', '-Iruntime/graphics', '-Iruntime/portable',
               '-Iruntime/vendor/zlib', *sources, '-lz', '-o', str(out / 'record-session')]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([str(out / 'record-session')], cwd=ROOT, check=True)
    (out / 'report.json').write_text(json.dumps(dict(passed=True,
        command=command, sourceSHA256={s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources},
        sanitizers=['address', 'undefined'], hardwareTested=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
