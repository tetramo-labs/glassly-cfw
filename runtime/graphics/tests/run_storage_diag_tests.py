#!/usr/bin/env python3
"""Production passive topology serializer with mocked fixed RAM snapshots."""
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 sources=[ROOT/'runtime/graphics/storage_diag.c',ROOT/'runtime/graphics/tests/test_storage_diag.c']
 inputs=[*sources,ROOT/'runtime/graphics/storage_diag.h',Path(__file__).resolve()]
 hashes={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}
 command=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'runtime/graphics'),*map(str,sources),'-o',str(out/'test_storage_diag')]
 build=subprocess.run(command,text=True,capture_output=True);(out/'build.stdout').write_text(build.stdout);(out/'build.stderr').write_text(build.stderr);build.check_returncode()
 result=subprocess.run([str(out/'test_storage_diag')],text=True,capture_output=True);(out/'test.stdout').write_text(result.stdout);(out/'test.stderr').write_text(result.stderr);result.check_returncode()
 replies=[json.loads(x) for x in result.stdout.splitlines() if x.startswith('{')]
 assert len(replies)==6 and replies[1]['xip1LegacyId']==0x8517 and replies[1]['generalSpiPinsMatch']==1
 assert [r['recordState'] for r in replies[2:]]==['present','absent','unavailable','invalid']
 assert all(hashlib.sha256((ROOT/x).read_bytes()).hexdigest()==v for x,v in hashes.items())
 report={'passed':True,'source_sha256':hashes,'replies':replies,'summary':[x for x in result.stdout.splitlines() if x.startswith('PASS')],'native_RAM_and_KV_mocked':True,'device_actions':False,'source_drift':[]}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report['summary'])
if __name__=='__main__':main()
