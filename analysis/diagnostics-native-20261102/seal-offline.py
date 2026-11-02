"""Seal the completed offline checkpoint; no radio operations or installation claims."""
if not __debug__:
    raise RuntimeError('Verification requires assertions')
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, re

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/diagnostics-native-20261102'
REG = ROOT / 'analysis/regression-20261102-05'

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pin(path):
    return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def save(path, value):
    with path.open('x') as output:
        output.write(json.dumps(value, indent=2) + '\n')

reg = read(REG / 'report.json')
assert reg['all_required_offline_suites_passed'] is True
assert reg['format'] == 'memomind-offline-regression-composite-v1'
assert sha(ROOT / reg['base_report']) == reg['base_report_sha256']
assert reg['reused_successful_stages'] == 115 and len(reg['rerun_stages']) == 2
assert reg['source_changes_since_base'] == ['tests/run_tests.py']
for row in reg['results']:
    for value in row.get('original_logs', {}).values():
        assert sha(ROOT / value['path']) == value['sha256']
assert reg['sources_changed_during_run'] == reg['missing_upstream_mapped_stages'] == []
sources = read(REG / 'source-sha256.json')
assert sources == read(REG / 'source-sha256-final.json')
assert all(sha(ROOT / name) == digest for name, digest in sources.items())
native = read(ROOT / 'analysis/diagnostic-commands-001/report.json')
assert native['passed'] is True and native['frozen'] is True and native['source_drift'] == []
pins = read(BASE / 'candidate-pins.json')
assert sha(ROOT / native['runtime']) == native['blob_sha256'] == pins['runtime_sha256']
assert sha(ROOT / 'captures/firmware/diagnostic-commands-001/firmware.bin') == pins['image_sha256']
assert read(BASE / 'candidate-reconstruction.json')['complete_reconstruction_matches'] is True
review = read(ROOT / 'analysis/diagnostics-cleanup-review-20261102/final-review.json')
assert review['source_drift'] == [] and review['runtime_sha256'] == pins['runtime_sha256']
assert read(BASE / 'ios-core.json')['passed'] is True
assert read(BASE / 'helper-builds.json')['passed'] is True
helper = read(BASE / 'template-compile-003/report.json')
assert helper['compile_passed'] is True and helper['pins'] == pins
verifier = read(ROOT / helper['verifier_evidence'])
assert verifier['passed'] is True and verifier['cases'] == 37
assert all(row['accepted'] == row['expected_acceptance'] for row in verifier['results'])
inspection = read(BASE / 'swift-inspect.json')
assert inspection['eligible'] is True and inspection['bluetoothAccessed'] is False
assert inspection['sha256'] == pins['image_sha256'] and inspection['releaseName'] == 'diagnostic-commands-001'
for name, digest in helper['files_sha256'].items():
    assert sha(ROOT / name) == digest, name
python = read(REG / 'firmware_transport.json')
assert python['all_required_tests_passed'] is True and python['skipped'] == []
matches = re.findall(r'Executed (\d+) tests?, with 0 failures', (REG / 'native_swift.stdout').read_text())
assert matches
swift = max(map(int, matches))
now = datetime.now(timezone.utc).isoformat()
snapshot = BASE / 'source-snapshot'
snapshot.mkdir(exist_ok=False)
for name, digest in sources.items():
    target = snapshot / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT / name).read_bytes())
    assert sha(target) == digest
report = {
    'format': 'memomind-diagnostics-offline-checkpoint-v1', 'utc': now,
    'release': 'diagnostic-commands-001', 'candidate': pins,
    'aggregate': str(REG.relative_to(ROOT) / 'report.json'),
    'regression_execution_scope': reg['execution_scope'],
    'all_required_offline_suites_passed': True,
    'required_stages': sum(row['parity_required'] for row in reg['results']),
    'python_tests': python['tests_run'], 'swift_tests': swift,
    'source_files_rechecked': len(sources), 'source_drift': False,
    'ios15_core_typecheck': True, 'swift_catalog_admitted': True,
    'trace_verifier_synthetic_cases': verifier['cases'],
    'current_installed_release_at_checkpoint': 'text-commands-001',
    'diagnostics_candidate_installed': False, 'hardware_tested': False,
    'parity_scope': reg['parity_scope'],
    'required_original_inventory': reg['required_host_core_scenario_inventory'],
    'remaining_required_suite_entries': reg['remaining_upstream_suite_files'],
    'full_cfw_parity': False,
    'limitations': native['limitations'] + [
        'Offline original G2 references and native mocks do not prove hardware acceptance.',
        'Mac transport traces are application logs, not independent HCI/radio captures.',
        'Compass/raw IMU, single-button ownership and other required native adapters remain unfinished.',
        'Swift iOS type checking does not establish an iOS Bluetooth or Glassly integration.',
    ],
}
save(BASE / 'offline-checkpoint.json', report)
files = {ROOT / name for name in sources}
files.update(path for path in snapshot.rglob('*') if path.is_file())
for directory in (BASE, ROOT / 'analysis/diagnostic-commands-001',
                  ROOT / 'analysis/diagnostics-cleanup-review-20261102',
                  ROOT / 'analysis/diagnostics-swift-20261102',
                  ROOT / 'captures/firmware/diagnostic-commands-001',
                  ROOT / 'runtime/build/diagnostic-commands-001'):
    files.update(path for path in directory.rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts)
files.update({REG / 'report.json', REG / 'source-sha256.json', REG / 'source-sha256-final.json',
              ROOT / 'README.md', ROOT / 'tests/g2_compat/COMMAND_PARITY.md',
              ROOT / 'analysis/parity-status.json', ROOT / 'analysis/storage-integration-plan.json'})
files.add(ROOT / reg['base_report'])
files.update(path for path in REG.rglob('*') if path.is_file())
files.add(ROOT / 'swift/MemoMindKit/.build/out/Products/Debug/memomind')
manifest = ROOT / 'analysis/evidence/diagnostics-offline-20261102.json'
assert manifest not in files
save(manifest, {'format': 'memomind-evidence-supplement-v1', 'utc': now,
                'scope': 'Offline diagnostics/cleanup candidate, G2 comparisons, native RV32, Swift and exact OTA admission',
                'previous_hardware_evidence': pin(ROOT / 'analysis/evidence/text-hardware-20261102.json'),
                'device_actions': False, 'files': [pin(path) for path in sorted(files)]})
print(json.dumps({'report': str(BASE / 'offline-checkpoint.json'),
                  'evidence': str(manifest), 'files': len(files),
                  'required_stages': report['required_stages']}))
