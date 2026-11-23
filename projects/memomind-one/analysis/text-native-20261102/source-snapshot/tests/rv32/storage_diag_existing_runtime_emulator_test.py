#!/usr/bin/env python3
"""Run existing scene/input actual-code scenarios against the diagnostic image."""
import argparse,sys
from pathlib import Path
p=argparse.ArgumentParser(add_help=False);p.add_argument('--suite',choices=('scene','input'),required=True)
args,rest=p.parse_known_args();sys.argv=[sys.argv[0],*rest]
if args.suite=='scene':
    import scene_runtime_emulator_test as suite
    suite.SCENE_SHA='265f8837b2b939930434253f7be63a1155190fef701c57d8c123d482a66725eb'
else:
    import input_runtime_emulator_test as suite
    suite.PINNED_SHA='265f8837b2b939930434253f7be63a1155190fef701c57d8c123d482a66725eb'
suite.BUILD=Path(__file__).resolve().parents[2]/'runtime/build/storage-diag-001'
if __name__=='__main__':suite.main()
