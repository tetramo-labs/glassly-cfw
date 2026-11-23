#!/usr/bin/env python3
"""Execute the stock first-run selector and the constructed CFW replacement."""
import argparse
import json
import sys
from pathlib import Path

import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_memomind_minimal_owner import BODY_BASE, apply_first_run_gate
from memomind_ota import sha, unpack_ota


def selection(body, setting):
    machine = u.Uc(u.UC_ARCH_RISCV, u.UC_MODE_RISCV32)
    start = BODY_BASE & ~4095
    machine.mem_map(start, ((BODY_BASE + len(body) - start + 4095) & ~4095))
    machine.mem_write(BODY_BASE, body)
    for register, value in ((r.UC_RISCV_REG_S1, 0x02010000),
                            (r.UC_RISCV_REG_S2, 0x02010000),
                            (r.UC_RISCV_REG_S3, 0x5000)):
        machine.reg_write(register, value)
    reads, selected = [], []

    def step(uc, address, size, _):
        if address == 0x0422b05a:
            reads.append((uc.reg_read(r.UC_RISCV_REG_A0), uc.reg_read(r.UC_RISCV_REG_A1)))
            uc.reg_write(r.UC_RISCV_REG_A0, setting & 0xffffffff)
            uc.reg_write(r.UC_RISCV_REG_PC, uc.reg_read(r.UC_RISCV_REG_RA))
        elif address == 0x0425e07c:
            selected.append(uc.reg_read(r.UC_RISCV_REG_A0))
            uc.emu_stop()
        else:
            assert 0x0425bf44 <= address < 0x0425bf58 or 0x0425bfd8 <= address < 0x0425bfde, hex(address)

    machine.hook_add(u.UC_HOOK_CODE, step)
    machine.emu_start(0x0425bf44, 0, count=32)
    assert reads == [(0x5205, 0)] and len(selected) == 1
    return selected[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    from build_memomind_minimal_owner import construct
    build = json.loads((args.build / 'build.json').read_text())
    assert build['cfw_revision'] >= 11
    source = (ROOT / 'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
    original = unpack_ota(source)[1][3]['raw'][32:]
    image, manifest = construct(source, (args.build / 'graphics.bin').read_bytes(), build)
    body = unpack_ota(image)[1][3]['raw'][32:]
    cases = []
    for setting in (0, 1, 2, -1):
        stock, patched = selection(original, setting), selection(body, setting)
        assert stock == (0x0200fcf4 if setting == 0 else 0x0200fc7c)
        assert patched == 0x0200fc7c
        cases.append(dict(setting=setting, stock=hex(stock), patched=hex(patched)))
    gate = next(row for row in manifest['launcher_edits'] if row['purpose'] == 'first-run-minimal-launcher')
    offset = gate['address'] - BODY_BASE
    for byte in range(4):
        bad = bytearray(original)
        bad[offset + byte] ^= 1
        try:
            apply_first_run_gate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Changed instruction witness accepted')
    report = dict(passed=True, imageSHA256=sha(image), runtimeSHA256=build['blob_sha256'],
                  cases=cases, witnessRejections=4, gate=gate, hardwareTested=False,
                  limitations=['Settings lookup and app-manager entry mocked; actual boot selector instructions executed.',
                               'No pairing, UI appearance or persistent setting writes exercised.'])
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
