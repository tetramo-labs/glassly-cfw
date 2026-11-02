#!/usr/bin/env python3
"""Run required offline firmware tests; missing-fixture skips are failures."""
import argparse
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'scripts'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped and result.testsRun > 0
    report = {'format': 'memomind-required-python-tests-v1', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
              'all_required_tests_passed': passed, 'hardware_tested': False}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
