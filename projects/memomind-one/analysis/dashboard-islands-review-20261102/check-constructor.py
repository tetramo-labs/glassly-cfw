#!/usr/bin/env python3
"""Independent offline review; emits JSON only, never firmware/candidate files."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_memomind_dashboard_reclaim as c
from memomind_ota import unpack_ota
results=[]
def check(name,condition):
    assert condition,name
    results.append(name)
def reject(name,fn):
    try:fn()
    except ValueError:results.append(name);return
    raise AssertionError(name)
source=(ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
check('exact diagnostic source',c.sha(source)==c.SOURCE_SHA)
_,ss=unpack_ota(source);original=ss[3]['raw'][32:]
body,edits=c.apply_renderer_islands(original)
check('six fixed capacities', [e['rx_capacity'] for e in edits]==[486,430,332,450,518,530])
check('whole instruction prefixes',[len(bytes.fromhex(e['before'])) for e in edits]==[6,6,4,4,6,6])
for n,e in enumerate(edits):
    off=e['entry']-c.BODY_BASE;end=e['end']-c.BODY_BASE
    check(f'gate {n} returns minus one',body[off:off+4]==bytes.fromhex('7d558280'))
    check(f'tail {n} zero filled',not any(body[e['rx_start']-c.BODY_BASE:end]))
    bad=bytearray(original);bad[end-1]^=1
    reject(f'whole body witness {n}',lambda:c.apply_renderer_islands(bytes(bad)))
entry=edits[0]['entry'];cap=edits[0]['rx_capacity']
reject('unknown key',lambda:c.apply_renderer_islands(original,{entry+1:b''}))
reject('bool key',lambda:c.apply_renderer_islands(original,{True:b''}))
reject('odd size',lambda:c.apply_renderer_islands(original,{entry:b'1'}))
reject('oversize',lambda:c.apply_renderer_islands(original,{entry:b'1'*(cap+2)}))
reject('mutable payload',lambda:c.apply_renderer_islands(original,{entry:bytearray()}))
reject('short body',lambda:c.apply_renderer_islands(original[:100]))
payloads={e['entry']:bytes.fromhex('0100')*(e['rx_capacity']//2) for e in edits}
populated,pop_edits=c.apply_renderer_islands(original,payloads)
for e in edits:check(f'exact capacity retained {e["entry"]:x}',populated[e['rx_start']-c.BODY_BASE:e['rx_end']-c.BODY_BASE]==payloads[e['entry']])
output,manifest,proof=c.construct_dashboard_reclaim(source)
_,final=unpack_ota(output)
check('exact body reconstruction',final[3]['raw'][32:]==body)
check('unchanged body length',len(body)==len(original))
a,b=c.RENDERERS[0][0]-c.BODY_BASE,c.RENDERERS[-1][1]-c.BODY_BASE
check('all bytes outside fixed union unchanged',body[:a]==original[:a] and body[b:]==original[b:])
check('descriptor and table unchanged',all(body[x-c.BODY_BASE:y-c.BODY_BASE]==original[x-c.BODY_BASE:y-c.BODY_BASE] for x,y in [(0x0436312c,0x04363174),(0x0439a38c,0x0439a3c8)]))
check('six unrelated packed/raw streams unchanged',all(final[i]['raw']==ss[i]['raw'] and final[i]['packed']==ss[i]['packed'] for i in [0,1,2,4,5,6]))
check('explicit offline scope',manifest['live_flashing_enabled'] is False and manifest['hardware_validated'] is False and manifest['dashboard_fully_removed'] is False and proof['offline_only'] is True)
reject('source alteration',lambda:c.construct_dashboard_reclaim(source[:-1]+bytes([source[-1]^1])))
reconstructed,reproof=c.verify_dashboard_reclaim(source,manifest)
check('exact manifest reproducible',reconstructed==output)
invalid=dict(manifest,live_flashing_enabled=True)
reject('manifest cannot assert live authority',lambda:c.verify_dashboard_reclaim(source,invalid))
r={'passed':True,'checks':results,'check_count':len(results),'constructor_sha256':c.sha((ROOT/'scripts/build_memomind_dashboard_reclaim.py').read_bytes()),'source_sha256':c.sha(source),'in_memory_output_sha256':c.sha(output),'output_bytes':len(output),'output_body_sha256':c.sha(body),'emulation':False,'candidate_file_written':False,'device_actions':False,'command':'PYTHONDONTWRITEBYTECODE=1 python3 analysis/dashboard-islands-review-20261102/check-constructor.py'}
print(json.dumps(r,indent=2))
