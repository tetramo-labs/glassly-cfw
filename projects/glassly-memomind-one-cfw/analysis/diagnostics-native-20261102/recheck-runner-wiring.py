"""Reuse unchanged successful stages; rerun the two argument-wiring failures.

The failed full run is preserved. Command capture validates the corrected
aggregate's complete command list but is not counted as test execution.
"""
if not __debug__:
    raise RuntimeError('Assertions required')
from pathlib import Path
import contextlib, copy, hashlib, importlib.util, io, json, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
base = ROOT / 'analysis/regression-20261102-04'
out = ROOT / 'analysis/regression-20261102-05'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())
def save(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')

old = read(base / 'report.json')
previous = read(base / 'source-sha256.json')
assert previous == read(base / 'source-sha256-final.json')
assert old['sources_changed_during_run'] == []
spec = importlib.util.spec_from_file_location('aggregate', ROOT / 'tests/run_tests.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
before = module.source_snapshot()
changed = [p for p in previous.keys() | before.keys() if previous.get(p) != before.get(p)]
assert changed == ['tests/run_tests.py'], changed
assert sha(out / 'aggregate-runner-before.py') == previous['tests/run_tests.py']
failed = {r['name'] for r in old['results'] if r['result'] != 'passed'}
assert failed == {'diagnostic_command_canary_contract', 'diagnostic_command_reader_contract'}
captured = []
with tempfile.TemporaryDirectory(prefix='memomind-command-capture-') as temp:
    scratch = Path(temp) / 'out'
    def capture(command, **kwargs):
        captured.append([str(value) for value in command])
        return subprocess.CompletedProcess(command, 0)
    with patch.object(sys, 'argv', ['run_tests.py', '--output', str(scratch)]), \
         patch.object(module.subprocess, 'run', side_effect=capture), \
         contextlib.redirect_stdout(io.StringIO()):
        assert module.main() == 0
    corrected = [[value.replace(str(scratch.resolve()), str(base)) for value in cmd] for cmd in captured]
assert len(corrected) == len(old['results']) == 117
for row, command in zip(old['results'], corrected):
    expected = list(row['command'])
    if row['name'] in failed:
        host = 'flash-canary-host' if row['name'].endswith('canary_contract') else 'full-store-host'
        expected[2:2] = ['--host-report', str(base / host / 'report.json')]
    assert command == expected, (row['name'], command, expected)
save(out / 'source-sha256.json', before)
results = copy.deepcopy(old['results'])
for row, command in zip(results, corrected):
    if row['name'] not in failed:
        row['evidence_origin'] = 'reused unchanged inputs and identical command from full run'
        row['original_logs'] = {ext: {'path': str((base / (row['name'] + '.' + ext)).relative_to(ROOT)),
                                    'sha256': sha(base / (row['name'] + '.' + ext))}
                                for ext in ['stdout', 'stderr']}
        continue
    command = list(command)
    index = command.index('--report') + 1
    command[index] = str(out / Path(command[index]).name)
    started = time.monotonic()
    with (out / (row['name'] + '.stdout')).open('xb') as stdout, \
         (out / (row['name'] + '.stderr')).open('xb') as stderr:
        process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=60)
    row.update(command=command, result='passed' if process.returncode == 0 else 'failed',
               returncode=process.returncode, seconds=round(time.monotonic() - started, 3),
               evidence_origin='executed after adding required host-report argument')
    process.check_returncode()
with (out / 'scope.stdout').open('xb') as stdout, (out / 'scope.stderr').open('xb') as stderr:
    subprocess.run([sys.executable, 'tests/g2_compat/test_scope.py'], cwd=ROOT,
                   stdout=stdout, stderr=stderr, check=True)
after = module.source_snapshot(); assert before == after
save(out / 'source-sha256-final.json', after)
report = copy.deepcopy(old)
report.update(format='memomind-offline-regression-composite-v1', results=results,
              base_report=str((base / 'report.json').relative_to(ROOT)),
              base_report_sha256=sha(base / 'report.json'),
              completed_utc=datetime.now(timezone.utc).isoformat(),
              all_required_offline_suites_passed=True, sources_changed_during_run=[],
              source_changes_since_base=changed, reused_successful_stages=115,
              rerun_stages=sorted(failed), scope_tests_rerun=8,
              aggregate_commands_verified=True, required_parity_gate_exit=2,
              execution_scope='115 unchanged full-run passes reused; two corrected contract invocations executed; not a second full run')
for name in ['firmware_transport.json', 'native_swift.stdout']:
    with (out / name).open('xb') as stream: stream.write((base / name).read_bytes())
save(out / 'report.json', report)
print(json.dumps({'passed': True, 'stages_covered': 117, 'reused': 115,
                  'rerun': sorted(failed), 'source_changes_since_base': changed,
                  'full_parity': False}))
