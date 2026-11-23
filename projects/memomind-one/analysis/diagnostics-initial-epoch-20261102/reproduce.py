#!/usr/bin/env python3
"""Read frozen RV32 image; reproduce epoch seeding with mocked native ticks/APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PIN = 'c1d8a1ffdd4f2799de4149d2e113527b29716886f6530549e56f68f61333d3b3'
BUILD = ROOT/'runtime/build/diagnostic-commands-001'
TICKS = (0, 33148, 65535, 0x12345678)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def following(epoch):
    return ((epoch + 1) & 0xffff) or 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path(__file__).with_name('report.json'))
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError('Use a new report path to preserve prior evidence: '+str(args.report))
    manifest = json.loads((BUILD/'build.json').read_text())
    assert sha(BUILD/'graphics.bin') == PIN == manifest['blob_sha256']
    paths = [ROOT/p for p in manifest['source_sha256']]
    paths += sorted((ROOT/'tests/rv32').glob('*.py'))
    before = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    assert all(before[p] == digest for p, digest in manifest['source_sha256'].items())
    sys.path.insert(0, str(ROOT/'tests/rv32'))
    import diagnostic_command_runtime_emulator_test as D
    assert D.PINNED_SHA == PIN and D.G.u.__version__ == '2.1.4'
    D.G.BUILD = BUILD
    D.G.PINNED_SHA = PIN
    D.G.RESULTS.clear()
    rows = []
    for tick in TICKS:
        call_start = len(D.G.RESULTS)
        machine = D.DiagnosticMachine()
        machine.now = tick
        machine.send_scene(b'\x0b')  # initial cleanup with no graphics owner
        initial = machine.diagnostic(0)
        reply, _ = machine.send_scene(bytes([41, 0, 0, 1, 0, 0]), patch_epoch=False)
        first = int.from_bytes(reply[4:6], 'little')
        seed = ((tick ^ (tick >> 16)) & 0xffff) or 1
        after_first = machine.diagnostic()['epoch']
        assert first == following(seed) and initial['epoch'] == 0 and after_first == 0
        machine.send_scene(b'\x0b')
        saved = machine.diagnostic()['epoch']
        assert saved == following(first)
        reply, _ = machine.send_scene(bytes([41, 0, 0, 2, 0, 0]), patch_epoch=False)
        second = int.from_bytes(reply[4:6], 'little')
        after_second = machine.diagnostic()['epoch']
        assert second == following(saved) and after_second == saved
        machine.assert_clear()
        calls = D.G.RESULTS[call_start:]
        rows.append({'native_tick_mock': tick, 'folded_seed': seed,
                     'initial_saved_epoch': initial['epoch'], 'first_reset_reply': first,
                     'snapshot_after_first_reset': after_first, 'saved_after_cleanup': saved,
                     'second_zero_reset_reply': second, 'snapshot_after_second_reset': after_second,
                     'handler_calls': len(calls),
                     'instructions': sum(c['instructions'] for c in calls)})
    drift = [p for p, digest in before.items() if sha(ROOT/p) != digest]
    assert not drift
    witness_ranges = {
        'runtime/portable/scene_cache.inc': [(221, 235), (240, 253), (439, 446), (1934, 1955)],
        'runtime/portable/scene.c': [(19, 19), (163, 168)],
        'runtime/graphics/scene_session.c': [(40, 42)],
        'runtime/graphics/graphics.c': [(141, 141), (187, 193), (382, 389)],
        'runtime/graphics/native.c': [(108, 111)],
        'runtime/graphics/diagnostics.c': [(88, 89)],
    }
    witnesses = []
    for filename, ranges in witness_ranges.items():
        lines = (ROOT/filename).read_text().splitlines()
        witnesses.append({'path': filename, 'sha256': sha(ROOT/filename),
                          'excerpts': [{'first_line': lo, 'last_line': hi,
                                        'text': '\n'.join(lines[lo-1:hi])} for lo, hi in ranges]})
    report = {
        'format': 'memomind-initial-epoch-rv32-v1', 'passed': True,
        'runtime': str((BUILD/'graphics.bin').relative_to(ROOT)),
        'blob_sha256': PIN, 'build_manifest_sha256': sha(BUILD/'build.json'),
        'actual_rv32_execution': True, 'unicorn_version': D.G.u.__version__,
        'native_clock_and_external_APIs_mocked': True, 'device_actions': False,
        'production_or_test_edits': False, 'source_drift': drift,
        'reproduction_script': str(Path(__file__).resolve().relative_to(ROOT)),
        'reproduction_script_sha256': sha(Path(__file__).resolve()),
        'command': ['.tools/rv32-tests-venv/bin/python',
                    'analysis/diagnostics-initial-epoch-20261102/reproduce.py',
                    '--report', str(args.report)],
        'rows': rows, 'source_witnesses': witnesses,
        'conclusion': {
            'fresh_epoch': 'Fold native millisecond tick into16 bits; replace zero with1; first zero-epoch RESET increments that seed, skipping zero.',
            'live33149': 'Reproduced with mocked tick33148. This is consistent with source behavior, not proof of the exact tick sampled on hardware.',
            'saved_epoch': 'Diagnostic snapshot is saved cleanup epoch, not a mirror of active scene cache epoch.',
            'helper_v2': 'Accept the first valid APPLIED nonzero RESET reply and anchor E there; assert cleanup next(E) and subsequent zero-epoch RESET next(next(E)). Snapshot remains the cleanup value until another cleanup.',
        },
        'limitations': ['Native clock, heap, LVGL and transport APIs mocked; no hardware was contacted.',
                       'Reproduction does not weaken the frozen runtime tests or modify previous reports.'],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report[key] for key in ('passed', 'blob_sha256', 'source_drift', 'rows')}, indent=2))


if __name__ == '__main__':
    main()
