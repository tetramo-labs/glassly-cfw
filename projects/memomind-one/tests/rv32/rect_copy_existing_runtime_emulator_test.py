#!/usr/bin/env python3
"""Retained native suites repinned to the separate mode9 runtime; no devices."""
import argparse,json,sys
from pathlib import Path
from rect_copy_runtime_emulator_test import BUILD,PINNED_SHA

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',choices=('gates','canary','reader','input'),required=True);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    assert json.loads((a.build/'build.json').read_text())['rect_copy'] is True
    if a.suite=='gates':import flash_canary_gate_emulator_test as suite
    elif a.suite=='canary':import flash_canary_runtime_emulator_test as suite
    elif a.suite=='reader':
        import flash_canary_reader_emulator_test as reader
        suite=reader.suite
    else:import input_runtime_emulator_test as suite
    suite.BUILD=a.build.resolve();suite.PINNED_SHA=PINNED_SHA
    sys.argv=[sys.argv[0],'--build',str(a.build),'--report',str(a.report)];suite.main()
if __name__=='__main__':main()
