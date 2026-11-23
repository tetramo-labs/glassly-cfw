#!/usr/bin/env python3
"""ASan/UBSan actual canary core+native adapter; native task/flash mocked."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 sources=[ROOT/'runtime/graphics/flash_canary.c',ROOT/'runtime/graphics/flash_store_native.c',ROOT/'runtime/graphics/tests/flash_canary/test_flash_canary.c']
 inputs=[*sources,ROOT/'runtime/graphics/flash_canary.h',ROOT/'runtime/graphics/flash_store_native.h',ROOT/'runtime/graphics/graphics.h',ROOT/'runtime/graphics/storage_diag.h',Path(__file__).resolve()]
 hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
 cmd=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-DMM_FLASH_NATIVE_HOST_TEST=1','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'runtime/graphics'),'-I'+str(ROOT/'runtime/portable'),*map(str,sources),'-o',str(out/'test_canary')]
 b=subprocess.run(cmd,text=True,capture_output=True);(out/'build.stdout').write_text(b.stdout);(out/'build.stderr').write_text(b.stderr);b.check_returncode()
 r=subprocess.run([str(out/'test_canary')],text=True,capture_output=True);(out/'test.stdout').write_text(r.stdout);(out/'test.stderr').write_text(r.stderr);r.check_returncode()
 assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
 report={'passed':True,'source_sha256':hashes,'replies':[json.loads(x) for x in r.stdout.splitlines() if x.startswith('{')],'summary':r.stdout.splitlines()[-1],'native_mocked':True,'device_actions':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report['summary'])
if __name__=='__main__':main()
