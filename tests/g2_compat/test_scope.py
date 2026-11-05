"""Scope-only runner regressions; subprocesses are mocked, never device actions."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScopeTests(unittest.TestCase):
    def test_inventory_preserves_originals_and_mixed_suite(self):
        inventory = json.loads((ROOT / 'tests/g2_compat/inventory.json').read_text())
        pin = json.loads((ROOT / 'tests/g2_compat/UPSTREAM.json').read_text())
        for name, digest in pin['copied_files'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'tests/g2_compat/upstream' / name).read_bytes()).hexdigest(), digest)
        rows = {r['upstream_file']: r for r in inventory['rows']}
        excluded = {name for name, row in rows.items() if not row['parity_required']}
        self.assertEqual(excluded, {'patches/host/keyboard_host_test.c', 'patches/host/keyboard_emulator_test.py', 'demos/keyboard.test.ts', 'demos/keyboard.ts', 'demos/head-up-test.ts', 'demos/ring-touch-test.ts', 'demos/sound-test.ts', 'patches/host/volume_gate_host_test.c'})
        self.assertEqual(inventory['host_core_scenarios']['total'], 46)
        self.assertEqual(inventory['host_core_scenarios']['original_assertion_sites'], 769)
        self.assertEqual(inventory['required_host_core_scenarios']['total'], 38)
        self.assertEqual(inventory['required_host_core_scenarios']['original_assertion_sites'], 645)
        self.assertEqual(inventory['required_bun_test_cases'], 11)
        mixed = rows['patches/host/upstream_host_test.c']
        self.assertTrue(mixed['parity_required'])
        self.assertEqual(mixed['assertion_site_count'], 78)
        self.assertEqual(mixed['test_count'], 5)
        groups = {g['name']: g for g in mixed['test_groups']}
        self.assertFalse(groups['batteries']['parity_required'])
        self.assertTrue(groups['headings']['parity_required'])
        self.assertTrue(groups['routing']['parity_required'])
        self.assertTrue(groups['settings']['parity_required'])
        self.assertEqual(set(inventory['parity_scope']['required_hardware_features']), {
            'Single-button input', 'Compass data', 'Raw IMU data', 'Ambient-light sensing',
        })
        self.assertTrue(rows['demos/vector-protocol.test.ts']['parity_required'])
        self.assertFalse(inventory['full_memo_suite_port_complete'])

    def aggregate(self, optional=False, fail=None, require=False):
        module = load('scope_aggregate', 'tests/run_tests.py')
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            argv = ['run_tests.py', '--output', str(out)]
            if optional: argv.append('--include-keyboard-reference')
            if require: argv.append('--require-complete')
            def run(command, **kwargs):
                code = int(bool(fail and any(fail in str(p) for p in command)))
                return subprocess.CompletedProcess(command, code)
            with patch.object(sys, 'argv', argv), patch.object(module, 'source_snapshot', return_value={}), patch.object(module.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                result = module.main()
            return result, json.loads((out / 'report.json').read_text())

    def test_aggregate_default_excludes_keyboard(self):
        code, report = self.aggregate()
        self.assertEqual(code, 0)
        self.assertNotIn('keyboard', [r['name'] for r in report['results']])
        self.assertEqual(report['missing_upstream_mapped_stages'], [])
        self.assertNotIn('patches/host/keyboard_emulator_test.py', report['remaining_upstream_suite_files'])
        self.assertIn('patches/host/upstream_host_test.c', report['remaining_upstream_suite_files'])
        self.assertNotIn('demos/head-up-test.ts', report['remaining_upstream_suite_files'])
        self.assertNotIn('demos/ring-touch-test.ts', report['remaining_upstream_suite_files'])
        self.assertIn('demos/ble-mode.ts', report['remaining_upstream_suite_files'])

    def test_aggregate_optional_failure_is_reported_nonblocking(self):
        code, report = self.aggregate(optional=True, fail='run_keyboard_tests.py')
        self.assertEqual(code, 0)
        keyboard = next(r for r in report['results'] if r['name'] == 'keyboard')
        self.assertEqual(keyboard['result'], 'failed')
        self.assertFalse(keyboard['parity_required'])
        self.assertIn('--include-keyboard-reference', next(r for r in report['results'] if r['name'] == 'g2_compat')['command'])

    def test_mixed_settings_failure_blocks(self):
        self.assertEqual(self.aggregate(fail='run_upstream_tests.py')[0], 1)

    def test_native_sensor_failure_blocks(self):
        code, report = self.aggregate(fail='sensor_native_abi_test.py')
        self.assertEqual(code, 1)
        stage = next(r for r in report['results'] if r['name'] == 'sensor_native_abi')
        self.assertTrue(stage['parity_required'])
        self.assertEqual(stage['result'], 'failed')

    def test_required_parity_still_incomplete(self):
        self.assertEqual(self.aggregate(require=True)[0], 2)

    def compat(self, optional=False, fail=None, volume=False):
        module = load('scope_compat', 'tests/g2_compat/run_tests.py')
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'deps').mkdir()
            (base / 'media').mkdir()
            (base / 'media/bad_apple_quarter.gif').write_bytes(b'test fixture path only')
            out = base / 'out'
            argv = ['run_tests.py', '--output', str(out), '--demos-dependencies', str(base / 'deps'), '--g2-media', str(base / 'media')]
            if optional: argv.append('--include-keyboard-reference')
            if volume: argv.append('--include-volume-gate-reference')
            def run(command, **kwargs):
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'mocked compiler artifact')
                code = int(bool(fail and any(fail in str(p) for p in command)))
                return subprocess.CompletedProcess(command, code, stdout=b'' if not kwargs.get('text') else '', stderr=b'' if not kwargs.get('text') else '')
            def copytree(src, dst, **kwargs): Path(dst).mkdir(parents=True, exist_ok=True)
            with patch.object(sys, 'argv', argv), patch.object(module.subprocess, 'run', side_effect=run), patch.object(module.shutil, 'copytree', side_effect=copytree), patch.object(module.shutil, 'which', return_value='/mock/bun'), contextlib.redirect_stdout(io.StringIO()):
                result = module.main()
            return result, json.loads((out / 'report.json').read_text())

    def test_compat_default_preserves_settings_but_excludes_keyboard(self):
        code, report = self.compat()
        self.assertEqual(code, 0)
        names = [r['name'] for r in report['results']]
        self.assertIn('reference_upstream', names)
        self.assertNotIn('reference_keyboard', names)
        self.assertNotIn('ported_volume_gate', names)
        self.assertNotIn('typecheck_keyboard', names)
        self.assertNotIn('typescript_keyboard', names)

    def test_compat_each_optional_failure_is_nonblocking(self):
        for name in ('reference_keyboard', 'keyboard.test.ts', 'tsconfig.keyboard.json'):
            with self.subTest(name=name):
                code, report = self.compat(optional=True, fail=name)
                self.assertEqual(code, 0)
                self.assertTrue(any(r['result'] in ('failed', 'build-failed') and not r['parity_required'] for r in report['results']))

    def test_optional_volume_gate_failure_is_nonblocking(self):
        code, report = self.compat(volume=True, fail='ported_volume_gate')
        self.assertEqual(code, 0)
        row = next(r for r in report['results'] if r['name'] == 'ported_volume_gate')
        self.assertFalse(row['parity_required'])
        self.assertIn(row['result'], ('failed', 'build-failed'))

    def test_compat_mixed_settings_failure_blocks(self):
        self.assertEqual(self.compat(fail='reference_upstream')[0], 1)


if __name__ == '__main__': unittest.main()
