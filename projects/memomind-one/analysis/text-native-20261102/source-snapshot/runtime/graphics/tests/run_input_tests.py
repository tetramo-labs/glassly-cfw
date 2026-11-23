#!/usr/bin/env python3
"""ASan/UBSan tests of actual input C and version2 display integration."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    sources = [ROOT/'runtime/graphics/tests/test_input.c', ROOT/'runtime/graphics/graphics.c',
               ROOT/'runtime/graphics/scene_session.c', ROOT/'runtime/graphics/native_text.c',
               *(ROOT/'runtime/portable'/name for name in ('geometry.c', 'scene.c', 'vector.c'))]
    # test_input.c includes production input.c so exhaustion state can be set
    # explicitly without exposing a production mutation API.
    inputs = [Path(__file__).resolve(), *sources, ROOT/'runtime/graphics/input.c', ROOT/'scripts/memomind_input.py',
              *sorted((ROOT/'runtime/graphics').glob('*.h')),
              *sorted((ROOT/'runtime/portable').glob('*.h')), *sorted((ROOT/'runtime/portable').glob('*.inc'))]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
             '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-DMM_GRAPHICS_INPUT=1',
             '-DMM_GRAPHICS_SCENE=1', '-I'+str(ROOT/'runtime/graphics'), '-I'+str(ROOT/'runtime/portable')]
    command = ['clang', *flags, *map(str, sources), '-o', str(out/'test_input')]
    report = {'format': 'memomind-input-host-tests-v1', 'passed': False, 'source_sha256': hashes,
              'build_command': command, 'hardware_tested': False,
              'scope': 'Production input C, scene-enabled version2 display dispatch; native allocator/LVGL/transport mocked'}
    try:
        built = subprocess.run(command, capture_output=True, text=True)
        (out/'build.stdout').write_text(built.stdout); (out/'build.stderr').write_text(built.stderr)
        built.check_returncode()
        tested = subprocess.run([str(out/'test_input')], capture_output=True, text=True)
        (out/'test.stdout').write_text(tested.stdout); (out/'test.stderr').write_text(tested.stderr)
        tested.check_returncode()
        replies = [json.loads(line) for line in tested.stdout.splitlines() if line.startswith('{')]
        sys.path.insert(0, str(ROOT/'scripts'))
        from memomind_input import decode_reply, InputNativeError
        schema_success = schema_errors = 0
        for reply in replies:
            try:
                decoded = decode_reply({'tlvs': [(5, json.dumps(reply).encode())]})
                assert decoded == reply
                schema_success += 1
            except InputNativeError as exc:
                assert exc.reply == reply
                schema_errors += 1
        report['client_schema'] = {'success': schema_success, 'native_errors': schema_errors,
                                   'client_sha256': hashlib.sha256((ROOT/'scripts/memomind_input.py').read_bytes()).hexdigest()}
        required = {'glassly', 'abi', 'result', 'active', 'nonce', 'mask', 'capacity', 'leaseTicks',
                    'sequence', 'ack', 'drops', 'exhausted', 'records'}
        for reply in replies:
            assert reply['glassly'] == 'input' and reply['abi'] == 1
            if reply['result'] == 'ok': assert set(reply) == required
            if 'records' in reply:
                assert len(reply['records']) <= 8 and reply['capacity'] == 32 and reply['leaseTicks'] == 30000
                for record in reply['records']:
                    assert set(record) == {'tick', 'sequence', 'id', 'class'}
                    assert 0 <= record['tick'] <= 0xffffffff and 1 <= record['sequence'] <= 0xffffffff
                    assert record['class'] in (2, 3)
        report['validated_json_replies'] = len(replies)
        report['source_drift'] = [p for p, digest in hashes.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != digest]
        assert not report['source_drift']
        report['passed'] = True
        report['summary'] = tested.stdout.splitlines()[-1]
    except (OSError, subprocess.CalledProcessError, AssertionError, ValueError) as exc:
        report['error'] = str(exc)
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256', 'build_command')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
