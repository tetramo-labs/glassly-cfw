#!/usr/bin/env python3
"""Run existing scene/input actual-code cases against the full-store reader."""
import argparse
import sys
from pathlib import Path

p = argparse.ArgumentParser(add_help=False)
p.add_argument('--suite', choices=('scene', 'input'), required=True)
args, rest = p.parse_known_args()
sys.argv = [sys.argv[0], *rest]
SHA = '83290f4c3d300b3f479bcd60865ffb5cc29b55e5887e635fac6f0d0d208d352b'
if args.suite == 'scene':
    import scene_runtime_emulator_test as suite
    suite.SCENE_SHA = SHA
else:
    import input_runtime_emulator_test as suite
    suite.PINNED_SHA = SHA
suite.BUILD = Path(__file__).resolve().parents[2] / 'runtime/build/full-store-read-001'
if __name__ == '__main__':
    suite.main()
