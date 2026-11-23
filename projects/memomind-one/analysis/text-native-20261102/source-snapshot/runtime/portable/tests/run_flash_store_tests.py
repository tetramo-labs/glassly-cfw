#!/usr/bin/env python3
"""Sanitized transactional flash-store tests and genuine freestanding RV32 audit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--rvcc', type=Path, default=REPO / '.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    files = [ROOT / 'flash_store.c', ROOT / 'flash_store.h', Path(__file__).resolve(),
             *sorted((ROOT / 'tests/flash_store').glob('*.c'))]
    before = {str(path.relative_to(ROOT)): digest(path) for path in files}
    report = {'format': 'memomind-portable-flash-store-tests-v1', 'result': 'failed',
              'hardware_tested': False, 'source_sha256': before, 'commands': [],
              'limits': ['Ephemeral in-RAM maps: no reboot/power-loss persistence',
                         'No native reservation, bad-map acquisition or flash driver binding',
                         'Callbacks mocked on host; target code compiled, not executed on hardware',
                         'Per-function stack audit excludes callback and native task call chains']}

    def run(label, command):
        command = list(map(str, command))
        result = subprocess.run(command, capture_output=True)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label': label, 'argv': command, 'returncode': result.returncode})
        if result.returncode:
            raise RuntimeError(label + ' failed; see captured output')
        return result.stdout.decode()

    try:
        host = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(ROOT)]
        run('host-build', [args.cc, *host, ROOT / 'flash_store.c',
                          ROOT / 'tests/flash_store/test_flash_store.c', '-o', out / 'test_flash_store'])
        report['host_result'] = run('host-run', [out / 'test_flash_store']).strip()
        faults = re.search(r'fault_boundaries=(\d+) fault_runs=(\d+) read_faults=(\d+) erase_faults=(\d+) program_faults=(\d+)', report['host_result'])
        if not faults or tuple(map(int, faults.groups())) != (2112, 4224, 2048, 128, 2048):
            raise RuntimeError('Incomplete exhaustive fault coverage')
        report['fault_injection'] = dict(zip(('boundaries', 'runs', 'read', 'erase', 'program'), map(int, faults.groups())))
        passed = re.search(r'PASS checks=(\d+) context_bytes=(\d+) workspace_bytes=(\d+)', report['host_result'])
        if not passed or int(passed[3]) != 4096 or int(passed[2]) > 512:
            raise RuntimeError('Missing successful resource-bound test')
        report['host'] = dict(zip(('assertion_evaluations', 'context_bytes', 'workspace_bytes'), map(int, passed.groups())))
        common = ['-march=rv32imafc', '-mabi=ilp32f', '-mstrict-align', '-mno-relax',
                  '-msmall-data-limit=0', '-std=c11', '-O2', '-ffreestanding', '-fno-builtin',
                  '-fno-common', '-fno-pic', '-fno-pie', '-ffunction-sections', '-fdata-sections',
                  '-fstack-usage', '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT)]
        run('rv32-build', [args.rvcc, *common, '-c', ROOT / 'flash_store.c', '-o', out / 'flash_store.o'])
        prefix = str(args.rvcc).removesuffix('gcc')
        header = run('rv32-elf', [prefix + 'readelf', '-h', out / 'flash_store.o'])
        if not re.search(r'Class:\s+ELF32', header) or not re.search(r'Machine:\s+RISC-V', header) or 'little endian' not in header:
            raise RuntimeError('Object is not actual RV32 little endian ELF')
        undefined = run('rv32-undefined', [prefix + 'nm', '-u', out / 'flash_store.o'])
        if undefined.strip():
            raise RuntimeError('Core has unresolved imports: ' + undefined)
        symbols = run('rv32-symbols', [prefix + 'nm', '--defined-only', out / 'flash_store.o'])
        if re.search(r'^\w+\s+[BbCcDdGgSsVv]\s+', symbols, re.M):
            raise RuntimeError('Core has writable/global common symbols')
        sections = run('rv32-sections', [prefix + 'size', '-A', out / 'flash_store.o'])
        sizes = {name: int(size) for name, size in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+', sections, re.M)}
        writable = {name: size for name, size in sizes.items() if size and name.startswith(('.data', '.bss', '.sdata', '.sbss', '.tdata', '.tbss'))}
        if writable:
            raise RuntimeError('Writable sections: ' + str(writable))
        stack = (out / 'flash_store.su').read_text().splitlines()
        if not stack or any(line.split('\t')[2] != 'static' for line in stack):
            raise RuntimeError('Unbounded or missing stack entries')
        maximum = max(int(line.split('\t')[1]) for line in stack)
        if maximum > 256:
            raise RuntimeError('Individual frame exceeds 256-byte offline bound')
        run('rv32-disassembly', [prefix + 'objdump', '-dr', out / 'flash_store.o'])
        run('rv32-layout-build', [args.rvcc, *common, '-c', ROOT / 'tests/flash_store/layout.c', '-o', out / 'layout.o'])
        run('rv32-layout-extract', [prefix + 'objcopy', '-O', 'binary', '--only-section=.rodata.mm_flash_store_layout', out / 'layout.o', out / 'layout.bin'])
        layout = dict(zip(('context_bytes', 'callbacks_bytes', 'workspace_bytes', 'minimum_usable_sectors'), struct.unpack('<4I', (out / 'layout.bin').read_bytes())))
        if layout != {'context_bytes': 320, 'callbacks_bytes': 16, 'workspace_bytes': 4096, 'minimum_usable_sectors': 129}:
            raise RuntimeError('Target resource layout changed: ' + str(layout))
        report['rv32'] = {'architecture': 'RV32IMAFC / ilp32f / little endian', 'undefined_symbols': [],
                          'writable_global_bytes': 0, 'text_bytes': sum(v for k, v in sizes.items() if k.startswith('.text')),
                          'rodata_bytes': sum(v for k, v in sizes.items() if k.startswith('.rodata')),
                          'layout': layout, 'stack_frames': stack, 'max_individual_stack_bytes': maximum}
        report['tools'] = {'cc': run('cc-version', [args.cc, '--version']).splitlines()[0],
                           'rvcc': run('rvcc-version', [args.rvcc, '--version']).splitlines()[0]}
        after = {str(path.relative_to(ROOT)): digest(path) for path in files}
        if before != after:
            raise RuntimeError('Source changed during validation')
        report['source_drift'] = False
        report['artifact_sha256'] = {path.name: digest(path) for path in out.iterdir() if path.is_file() and
                                    (path.suffix in ('.o', '.bin', '.su') or path.name == 'test_flash_store')}
        report['result'] = 'passed'
    except Exception as exc:
        report['error'] = str(exc)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('commands', 'source_sha256', 'artifact_sha256')}, indent=2))
    return report['result'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
