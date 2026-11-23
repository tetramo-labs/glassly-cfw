#!/usr/bin/env python3
"""Compile/run display-adapter ownership tests with explicit native mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/'runtime/graphics/graphics.c',ROOT/'runtime/portable/geometry.c',
             ROOT/'runtime/graphics/tests/test_graphics.c']
    flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
           '-fno-sanitize-recover=all','-I'+str(ROOT/'runtime/graphics'),'-I'+str(ROOT/'runtime/portable')]
    command=['clang',*flags,*map(str,sources),'-o',str(out/'test_graphics')]
    build=subprocess.run(command,capture_output=True,text=True)
    (out/'build.stdout').write_text(build.stdout);(out/'build.stderr').write_text(build.stderr)
    build.check_returncode()
    result=subprocess.run([str(out/'test_graphics')],capture_output=True,text=True)
    (out/'test.stdout').write_text(result.stdout);(out/'test.stderr').write_text(result.stderr)
    report={'build_command':command,'passed':result.returncode==0,'result':result.stdout.strip(),
            'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'hardware_tested':False,'native_oom_behavior':'mocked failure returns; actual LVGL may assert',
            'ownership_model':'display task serializes object and timer operations'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
