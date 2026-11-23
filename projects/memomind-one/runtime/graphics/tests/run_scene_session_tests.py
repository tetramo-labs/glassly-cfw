#!/usr/bin/env python3
"""Test the real display session and native queue adapter with explicit mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-from', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'runtime'
    flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-function', '-fsanitize=address,undefined',
             '-fno-sanitize-recover=all', '-I'+str(source/'graphics'),
             '-I'+str(source/'portable')]
    common = [source/'graphics/scene_session.c', source/'portable/scene.c',
              source/'portable/geometry.c', source/'portable/vector.c']
    inputs = sorted(p for base in ('graphics', 'portable')
                    for p in (source/base).rglob('*')
                    if p.is_file() and p.suffix in ('.c', '.h', '.inc', '.py'))
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in inputs}
    report = {'format': 'memomind-scene-session-tests-v1', 'passed': False,
              'source_hashes': hashes, 'commands': [], 'fixtures': [],
              'hardware_tested': False,
              'scope': ['Actual production scene session, native queue adapter and scene/vector core',
                        '600x350 native-policy lifecycle/heap tests use a 170KiB scene budget and 48KiB reserved headroom',
                        'Original 640x480 replay corpus uses a larger synthetic heap/store for exact upstream pixel expectations',
                        'Each corpus also runs at600x350/64KiB store with modeled request/job/queue memory; out-of-panel probes are explicitly omitted',
                        'Allocator, native LVGL and external firmware APIs are mocked; no native OOM guarantee']}

    def run(name, command):
        command = [str(x) for x in command]
        result = subprocess.run(command, capture_output=True)
        (out/(name+'.stdout')).write_bytes(result.stdout)
        (out/(name+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'name': name, 'command': command,
                                   'returncode': result.returncode})
        result.check_returncode()

    try:
        fixtures = []
        for name in ('vector-fixture.bin', 'gif-300.bin', 'svg-300.bin'):
            data = (args.fixtures_from/name).read_bytes()
            dest = out/name
            dest.write_bytes(data)
            fixtures.append(dest)
            report['fixtures'].append({'name': name, 'bytes': len(data),
                                       'sha256': hashlib.sha256(data).hexdigest()})
        run('build-session', ['clang', *flags, source/'graphics/tests/test_scene_session.c',
                              *common, '-o', out/'test_scene_session'])
        run('session', [out/'test_scene_session', *fixtures])
        run('build-native-adapter', ['clang', *flags, '-DMM_GRAPHICS_SCENE=1',
                                     source/'graphics/tests/test_scene_graphics.c',
                                     source/'graphics/graphics.c', source/'graphics/native_text.c', *common,
                                     '-o', out/'test_scene_graphics'])
        run('native-adapter', [out/'test_scene_graphics'])
        report['source_drift'] = [name for name, digest in hashes.items()
                                  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
        if report['source_drift']:
            raise RuntimeError('Source changed during execution')
        report['passed'] = True
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        report['error'] = str(exc)
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('commands', 'source_hashes')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
