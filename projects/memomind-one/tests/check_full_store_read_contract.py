#!/usr/bin/env python3
"""Full-store C/RV32 JSON through production Python/GM, including diagnostics."""
import argparse,json
from pathlib import Path
from check_flash_contract import check,Replay
from memomind_flash_read import FULL_STORE_PROFILE
from memomind_storage_diag import StorageDiagnosticClient,tail_unavailable_map

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host-report',type=Path,required=True);p.add_argument('--rv32-report',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 sources=[check(a.host_report),check(a.rv32_report)]
 runtime=json.loads(a.rv32_report.read_text());query=next(r for r in runtime['replies'] if 'ranges' in r);assert query['profile']==FULL_STORE_PROFILE
 counts={'topology':0,'badmap':0}
 for r in runtime['diagnostic_replies']:
  kind=r['diagnostic'];assert kind in counts
  io=Replay([(b'\0',query),(b'\2' if kind=='topology' else b'\3',r)])
  client=StorageDiagnosticClient(io,profile=FULL_STORE_PROFILE);client.query()
  assert (client.topology() if kind=='topology' else client.badmap())==r
  if kind=='badmap' and r['recordState'] in ('present','absent'):assert len(tail_unavailable_map(r))==32
  assert not io.exchanges and not io.incoming;counts[kind]+=1
 assert all(counts.values())
 report={'passed':True,'sources':sources,'diagnostic_counts':counts,'hardware_tested':False,'profile':FULL_STORE_PROFILE}
 a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
