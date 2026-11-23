#!/usr/bin/env python3
"""Native microphone ownership with injected APIs and sanitizer checking."""
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=['runtime/graphics/tests/test_microphone.c','runtime/graphics/microphone_native.c','runtime/graphics/microphone_native.h']
    command=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Iruntime/graphics','-Iruntime/portable',sources[0],'-o',str(out/'microphone')]
    subprocess.run(command,cwd=ROOT,check=True);subprocess.run([str(out/'microphone')],cwd=ROOT,check=True)
    (out/'report.json').write_text(json.dumps(dict(passed=True,command=command,sourceSHA256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},sanitizers=['address','undefined'],nativeAPIsMocked=True,hardwareTested=False),indent=2)+'\n')
if __name__=='__main__':main()
