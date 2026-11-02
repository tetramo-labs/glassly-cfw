#!/usr/bin/env python3
"""Run original complete canary gate scenarios on the separate raster build."""
import argparse,json,sys
from pathlib import Path
import flash_canary_gate_emulator_test as gates
from raster_commands_runtime_emulator_test import BUILD,PINNED_SHA

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=BUILD);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    assert json.loads((a.build/'build.json').read_text())['raster_commands'] is True
    gates.PINNED_SHA=PINNED_SHA
    sys.argv=[sys.argv[0],'--build',str(a.build),'--report',str(a.report)];gates.main()
    report=json.loads(a.report.read_text());report['raster_commands']=True;report['format']='memomind-raster-command-gates-v1';a.report.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
