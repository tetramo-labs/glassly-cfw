#!/usr/bin/env python3
"""Execute the six owner gates from the reconstructed candidate in RV32.

All RAM, stack and MMIO are deliberately unmapped during gate execution: a
dereference or prologue is a failure. This is entry-point control evidence,
not caller/boot, physical ownership, timing or hardware validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_memomind_exclusive_storage as constructor
from memomind_ota import unpack_ota

BASE = 0x041eb020
APP_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
RETURN = 0x05000000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out == ROOT / 'analysis/ghidra' or ROOT / 'analysis/ghidra' in out.parents:
        parser.error('Do not overwrite frozen native evidence')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(format='memomind-exclusive-owner-gates-emulation-v1', all_passed=False,
                  hardware_tested=False, device_actions=0, cases=[], provenance={},
                  limitations=['Only the six identified native entry points are gated.',
                               'No whole-boot, concurrent caller, raw/factory/OTA owner or physical ownership proof.',
                               'Candidate has no CFW native writer and is not eligible for the live flasher.'])
    status = 1
    try:
        if not __debug__:
            raise RuntimeError('Assertions must be enabled')
        import unicorn as u
        from unicorn import riscv_const as r
        assert u.__version__ == '2.1.4'
        report['unicorn'] = u.__version__
        paths = [Path(__file__), Path(constructor.__file__),
                 ROOT / 'analysis/extracted/validated-1.0.3.127/segment-3.body.bin',
                 ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin',
                 ROOT / 'runtime/build/storage-diag-001/graphics.bin']
        for path in paths:
            report['provenance'][str(path.relative_to(ROOT))] = sha(path.read_bytes())
        assert sha(paths[2].read_bytes()) == APP_SHA
        image, manifest, _ = constructor.construct_exclusive_storage(paths[3].read_bytes(), paths[4].read_bytes())
        _, streams = unpack_ota(image)
        body = streams[3]['raw'][32:]
        report['candidate_sha256'] = sha(image)
        report['candidate_manifest'] = manifest
        rng = random.Random(0x43555338)
        patterns = [[0] * 8, [0xffffffff] * 8,
                    [0, 0, 0x03001000, 256, 0, 0, 0, 0],
                    [0, 0x2fff00, 0x03001000, 256, 0, 0, 0, 0],
                    [0, 0x300000, 0x03001000, 4096, 0, 0, 0, 0],
                    [0, 0xffffffff, 0x03001000, 4096, 0, 0, 0, 0],
                    [0, 0x03001000, 96, 0, 0, 0, 0, 0],
                    [1, 1, 1, 1, 1, 1, 1, 1]]
        patterns += [[rng.getrandbits(32) for _ in range(8)] for _ in range(8)]
        reg = lambda i: getattr(r, 'UC_RISCV_REG_X' + str(i))
        for entry, _, _, expected, purpose in constructor.GATES:
            for index, arguments in enumerate(patterns):
                m = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
                m.mem_map(0x041eb000, 0x200000, u.UC_PROT_READ | u.UC_PROT_EXEC)
                m.mem_write(BASE, body)
                m.mem_map(RETURN, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
                m.mem_write(RETURN, bytes.fromhex('67800000'))
                initial = {i: rng.getrandbits(32) for i in range(1, 32)}
                initial.update({1: RETURN, 2: 0x0300fff0, 3: 0x02011688})
                initial.update({10 + i: value for i, value in enumerate(arguments)})
                for i, value in initial.items():
                    m.reg_write(reg(i), value)
                trace = []
                def instruction(mu, address, size, _):
                    trace.append((address, size))
                    assert address in (entry, entry + 2, RETURN), 'Unexpected native execution'
                    if address == RETURN:
                        mu.emu_stop()
                def memory(*_):
                    raise AssertionError('Owner gate accessed data memory')
                m.hook_add(u.UC_HOOK_CODE, instruction)
                m.hook_add(u.UC_HOOK_MEM_READ | u.UC_HOOK_MEM_WRITE, memory)
                m.emu_start(entry, 0, count=8)
                assert [a for a, _ in trace] == [entry, entry + 2, RETURN]
                assert trace[:2] == [(entry, 2), (entry + 2, 2)]
                for i, value in initial.items():
                    assert m.reg_read(reg(i)) == ((expected & 0xffffffff) if i == 10 else value)
                report['cases'].append(dict(entry=hex(entry), purpose=purpose,
                                            argument_case=index, return_code=expected,
                                            data_accesses=0, registers_preserved_except_a0=True))
        assert len(report['cases']) == 96
        report.update(all_passed=True, case_count=96)
        status = 0
    except Exception as exc:
        report.update(error=str(exc), traceback=traceback.format_exc())
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(all_passed=report['all_passed'], cases=len(report['cases']), output=str(out))))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
