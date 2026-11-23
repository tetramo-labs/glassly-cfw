#!/usr/bin/env python3
"""Replay actual C/RV32 diagnostics through Python checks and fragmented GM."""
import argparse,json,sys
from pathlib import Path
from check_flash_contract import Replay
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from memomind_storage_diag import StorageDiagnosticClient,tail_unavailable_map
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host-report',type=Path,required=True);p.add_argument('--rv32-report',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 rv=json.loads(a.rv32_report.read_text())['replies'];query=next(x for x in rv if 'ranges' in x);counts={}
 for path in (a.host_report,a.rv32_report):
  replies=json.loads(path.read_text())['replies'];n=0
  for r in replies:
   kind=r.get('diagnostic')
   if kind not in ('topology','badmap'):continue
   io=Replay([(b'\0',query),(b'\2' if kind=='topology' else b'\3',r)]);client=StorageDiagnosticClient(io);client.query()
   received=client.topology() if kind=='topology' else client.badmap();assert received==r
   if kind=='badmap' and r['recordState'] in ('present','absent'):assert len(tail_unavailable_map(r))==32
   assert not io.exchanges and not io.incoming;n+=1
  assert n;counts[str(path)]=n
 report={'passed':True,'reply_counts':counts,'hardware_tested':False,'scope':'Production C/RV32 emitted diagnostics independently validated through GM/Python; native RAM/KV synthetic'}
 a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
