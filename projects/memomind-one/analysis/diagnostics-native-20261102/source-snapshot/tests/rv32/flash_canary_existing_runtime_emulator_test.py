#!/usr/bin/env python3
"""Existing scene/input machine-code scenarios against the fixed canary build."""
import argparse
import sys
from pathlib import Path

p = argparse.ArgumentParser(add_help=False)
p.add_argument('--suite', choices=('scene', 'input'), required=True)
args, rest = p.parse_known_args()
sys.argv = [sys.argv[0], *rest]
SHA = 'c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992'
if args.suite == 'scene':
    import scene_runtime_emulator_test as suite
    suite.SCENE_SHA = SHA
else:
    import input_runtime_emulator_test as suite
    suite.PINNED_SHA = SHA
suite.BUILD = Path(__file__).resolve().parents[2] / 'runtime/build/flash-canary-004'
if __name__ == '__main__':
    suite.main()
