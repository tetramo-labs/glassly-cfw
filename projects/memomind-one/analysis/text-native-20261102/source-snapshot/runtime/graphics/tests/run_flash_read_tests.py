#!/usr/bin/env python3
"""Sanitizer tests of production bounded flash-read C with read-only native mocks."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--external-tail',action='store_true');p.add_argument('--full-store',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 sources=[ROOT/'runtime/graphics/flash_read.c',ROOT/'runtime/graphics/tests/test_flash_read.c']
 inputs=[*sources,ROOT/'runtime/graphics/flash_read.h',ROOT/'runtime/graphics/graphics.h',Path(__file__).resolve()]
 hashes={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}
 command=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'runtime/graphics'),'-I'+str(ROOT/'runtime/portable'),*map(str,sources),'-o',str(out/'test_flash_read')]
 if a.full_store:command[1:1]=['-DMM_FULL_STORE_READ=1','-DMM_STORAGE_DIAGNOSTICS=1','-DMM_EXTERNAL_TAIL_READ=1']
 if a.external_tail:command.insert(1,'-DMM_EXTERNAL_TAIL_READ=1')
 build=subprocess.run(command,text=True,capture_output=True);(out/'build.stdout').write_text(build.stdout);(out/'build.stderr').write_text(build.stderr);build.check_returncode()
 result=subprocess.run([str(out/'test_flash_read')],text=True,capture_output=True);(out/'test.stdout').write_text(result.stdout);(out/'test.stderr').write_text(result.stderr);result.check_returncode()
 replies=[json.loads(x) for x in result.stdout.splitlines() if x.startswith('{')]
 ranges=[(0,0,0x10000),(0,0x1eb000,0x1eb100),(0,0x7fc000,0x7fe000),(1,0x500000,0x510000)]
 if a.full_store:ranges[-1]=(1,0x500000,0x800000)
 elif a.external_tail:ranges.append((1,0x700000,0x800000))
 assert replies[0]['ranges']==[{'device':d,'start':b,'end':e} for d,b,e in ranges]
 for r in replies:
  assert r['glassly']=='flash-read' and r['abi']==1
  if 'hex' in r:assert len(bytes.fromhex(r['hex']))==r['length']<=256
  elif r['result']!='ok':assert set(r)=={'glassly','abi','result'}
 assert all(hashlib.sha256((ROOT/x).read_bytes()).hexdigest()==v for x,v in hashes.items())
 report={'passed':True,'external_tail_reader':a.external_tail,'full_store_reader':a.full_store,'source_sha256':hashes,'replies':replies,'summary':result.stdout.splitlines()[-1],'native_flash_mocked':True,'device_actions':False,'source_drift':[]}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256','replies')},indent=2))
if __name__=='__main__':main()
