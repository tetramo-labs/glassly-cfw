#!/usr/bin/env python3
"""Actual host/RV32 emitted canary JSON validated through strict Python and GM."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from memomind_flash_canary import CanaryClient,CanaryNativeError,CanaryProtocolError
from test_memomind_flash_canary import Wire

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host-report',type=Path,required=True);p.add_argument('--rv32-report',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();sources=[]
 for path in (a.host_report,a.rv32_report):
  counts={'success':0,'native_error':0,'status_error':0}
  for row in json.loads(path.read_text())['replies']:
   wire=Wire();client=CanaryClient(wire);client.verify_profile();wire.replies.append(row)
   try:received=client.status()
   except CanaryNativeError:assert row['result']!='ok';counts['native_error']+=1
   except CanaryProtocolError:assert set(row)=={'status'};counts['status_error']+=1
   else:assert received==row;counts['success']+=1
   assert not wire.incoming and not wire.replies
  assert counts['success'];sources.append({'source':str(path),'counts':counts})
 report={'passed':True,'sources':sources,'hardware_tested':False,'scope':'Production C/RV32 replies via actual GM framing and strict canary client; native APIs mocked'}
 a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
