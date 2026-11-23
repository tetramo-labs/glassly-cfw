#!/usr/bin/env python3
"""Acquire fixed storage preflight evidence; never initialize, repair or write flash."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from capture_memomind_flash import private_file,sync
from memomind_transport import RfcommBridge
from memomind_storage_diag import StorageDiagnosticClient,tail_unavailable_map,DIAGNOSTIC_PROFILE,DIAGNOSTIC_PROFILES
from probe_memomind import probe

def acquire(client,expected_header):
    if not isinstance(expected_header,bytes) or len(expected_header) not in (32,256):
        raise ValueError('Expected candidate app header must be32 or256 bytes')
    query=client.query();header=client.read(0,0x1eb000,256)
    if not header.startswith(expected_header):raise ValueError('Installed app header differs from candidate')
    before=client.topology();badmap=client.badmap();after=client.topology()
    effective=tail_unavailable_map(badmap)
    return {'profile':query,'app_header_verified':True,'app_header_sha256':hashlib.sha256(header).hexdigest(),
            'topology_before':before,'badmap':badmap,'topology_after':after,
            'topology_unchanged':before==after,'both_samples_consistent':before['consistent']==after['consistent']==1,
            'effective_tail_map_hex':effective.hex(),'effective_tail_usable_sectors':256-sum(x.bit_count() for x in effective),
            'map_source':'persisted-record' if badmap['recordState']=='present' else 'native-defined-absent-default',
            'physical_badmap_record_acquired':badmap['recordState']=='present','flash_mutations':0,'automatic_retries':0,
            'reservation_established':False},header

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--address',required=True);p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=38741);p.add_argument('--timeout',type=float,default=20);p.add_argument('--expected-app-header',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument("--profile",choices=DIAGNOSTIC_PROFILES,default=DIAGNOSTIC_PROFILE);a=p.parse_args()
    expected=a.expected_app_header.read_bytes()
    if len(expected) not in (32,256):p.error('Expected app header must be32 or256 bytes')
    a.output.mkdir(mode=0o700,parents=False,exist_ok=False)
    with private_file(a.output/'journal.jsonl','w') as journal:
        def save(row):journal.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),**row})+'\n');sync(journal)
        try:
            with RfcommBridge(a.host,a.port,timeout=a.timeout,trace=lambda row:save({'kind':'wire','data':row})) as t:
                save({'kind':'baseline','reply':probe(t,a.address,legacy_repeat_fa=True)})
                result,header=acquire(StorageDiagnosticClient(t,timeout=a.timeout,profile=a.profile),expected)
            with private_file(a.output/'app-header.bin') as f:f.write(header);sync(f)
            result.update(format='memomind-storage-preflight-v1',complete=True)
            with private_file(a.output/'manifest.json','w') as f:f.write(json.dumps(result,indent=2)+'\n');sync(f)
            print(json.dumps(result,indent=2))
        except Exception as exc:
            save({'kind':'failed','complete':False,'error_type':type(exc).__name__,'error':str(exc),'automatic_retries':0});raise
if __name__=='__main__':main()
