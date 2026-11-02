#!/usr/bin/env python3
"""Compile the pinned RV32 diagnostic extension and retain its ELF/assembly."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path, help='New build directory')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source, entry, linker = ROOT/'runtime/probe.c', ROOT/'runtime/entry.S', ROOT/'runtime/probe.ld'

    def run(tool, *arguments):
        result = subprocess.run([str(COMPILER/f'riscv-none-elf-{tool}'), *map(str, arguments)],
                                check=True, capture_output=True)
        if result.stderr:
            print(result.stderr.decode(), end='')
        return result.stdout

    flags = ['-march=rv32imafc', '-mabi=ilp32f', '-mcmodel=medany', '-mno-relax',
             '-msmall-data-limit=0', '-O2', '-ffreestanding', '-fno-builtin',
             '-fno-common', '-fno-pic', '-fno-pie', '-fno-stack-protector',
             '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-ffunction-sections', '-fdata-sections', '-fvisibility=hidden',
             '-fstack-usage', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-std=c11']
    run('gcc', *flags, '-c', source, '-o', out/'probe.o')
    run('gcc', *flags, '-c', entry, '-o', out/'entry.o')
    run('gcc', *flags, '-Wl,--no-relax,--gc-sections,--build-id=none,--fatal-warnings',
        '-Wl,-Map='+str(out/'probe.map'), '-T', linker, out/'entry.o', out/'probe.o', '-o', out/'probe.elf')
    undefined = run('nm', '-u', out/'probe.elf').strip()
    if undefined:
        raise RuntimeError('Unresolved symbols: '+undefined.decode())
    for tool, arguments, name in [
        ('objdump', ['-d', out/'probe.elf'], 'probe.asm'),
        ('readelf', ['-h', '-S', '-l', '-r', out/'probe.elf'], 'probe.readelf.txt'),
        ('nm', ['-n', out/'probe.elf'], 'probe.symbols.txt'),
        ('size', ['-A', out/'probe.elf'], 'probe.size.txt')]:
        (out/name).write_bytes(run(tool, *arguments))
    usage = (out/'probe.su').read_text().splitlines()
    for row in usage:
        columns = row.split('\t')
        if len(columns) != 3 or columns[2] != 'static' or int(columns[1]) > 64:
            raise RuntimeError('Unexpected stack use: '+row)
    run('objcopy', '-O', 'binary', out/'probe.elf', out/'probe.bin')
    blob = (out/'probe.bin').read_bytes()
    if not 0 < len(blob) <= 4096:
        raise RuntimeError('First diagnostic exceeds bounded blob size')
    report = {'compiler': run('gcc', '--version').decode().splitlines()[0],
              'flags': flags, 'entry_address': '0x0439bea0',
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'entry_source_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(),
              'linker_sha256': hashlib.sha256(linker.read_bytes()).hexdigest(),
              'blob_bytes': len(blob), 'blob_sha256': hashlib.sha256(blob).hexdigest(),
              'stack_usage': usage, 'undefined_symbols': [],
              'writable_sections': 'linker asserts .data and .bss empty',
              'device_execution': 'not tested by compilation'}
    (out/'build.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
