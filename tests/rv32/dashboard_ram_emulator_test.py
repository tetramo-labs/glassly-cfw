#!/usr/bin/env python3
"""Keep both frozen native UI-retirement harnesses in the required regression.

Harness gate recipes must equal production before execution. Analysis exports
are pinned stock-machine-code fixtures, not replacement implementations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from build_memomind_dashboard_ram import GATES


def main():
    assert __debug__, 'Assertions required'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    card = ROOT/'analysis/dashboard-ram-card-20261102/emulate-null-state.py'
    status = ROOT/'analysis/dashboard-ram-status-20261102/emulate_retirement.py'
    a, b = runpy.run_path(str(card)), runpy.run_path(str(status))
    production = {address: (before, after) for address, before, after, _ in GATES}
    assert production == {address: (before, '01458280') for address, before in b['PATCHES']}
    assert all(production[address] == (before.hex(), a['GATE'].hex()) for address, before in a['GATES'].items())
    for name, script, arguments in [('card', card, ['--output', str(out/'card.json')]),
                                     ('status', status, [str(out/'status.json')])]:
        with (out/(name+'.stdout')).open('xb') as stdout, (out/(name+'.stderr')).open('xb') as stderr:
            subprocess.run([sys.executable, str(script), *arguments], cwd=ROOT,
                           stdout=stdout, stderr=stderr, check=True)
    ca, st = [json.loads((out/(name+'.json')).read_text()) for name in ('card', 'status')]
    assert ca['passed'] and st['passed'] and ca['cases'] == 90 and st['native_calls'] == 140
    report = dict(passed=True, native_calls=230, production_gates_match=True,
                  hardware_tested=False, logging_predicate_mocked=True,
                  scope='Cold-zero owner state; full task/app lifecycle and unknown indirect aliases are not emulated',
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [card, status, ROOT/'scripts/build_memomind_dashboard_ram.py']})
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
