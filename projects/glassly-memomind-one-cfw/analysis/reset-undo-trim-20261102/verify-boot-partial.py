"""Offline independent GM trace cross-check; no Swift helper result trusted as wire proof."""
if not __debug__: raise RuntimeError('Refuse -O')
import hashlib,importlib.util,json,math,sys
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('diagnostic_wire',ROOT/'analysis/diagnostics-native-20261102/verify-smoke-v2.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
assert len(sys.argv)==4,'CAPTURE_DIRECTORY RELEASE NEW_REPORT_JSON required'
release=sys.argv[2];assert release in ('dashboard-ram-002','reset-undo-trim-001')
folder=Path(sys.argv[1]).resolve()
rows=[v.loads(line) for line in (folder/'trace.jsonl').read_text().splitlines()]
assert rows[-1]['event']=='failed' and rows[-1]['error']=='Failure(reason: \"Scene reply framing\")'
times=[r['uptime'] for r in rows];assert all(type(t) in (int,float) and math.isfinite(t) for t in times)
assert all(a<=b for a,b in zip(times,times[1:]))
tx=v.Ingress();rx=v.GmStream(legacy_repeat_fa=True,fragment_acks=True)
writes=deque();pending={};pairs=[];last=None;acks=set();notifications=[];started=False
for r in rows:
 if r['event']=='transmitSubmission':
  assert not pending
  b=bytes.fromhex(r['hex']);assert b;writes.append(b)
  for m in tx.feed(b):
   assert not pending;k=(m['event'],m['service'],m['command']);m['_time']=r['uptime'];pending[k]=m;acks.discard(k)
   if m['service']==15:started=True
 elif r['event']=='transmitCompletion':
  assert type(r['status']) is int and r['status']==0 and writes.popleft()==bytes.fromhex(r['hex'])
 elif r['event']=='receive':
  for m in rx.feed(bytes.fromhex(r['hex'])):
   k=(m['event'],m['service'],m['command'])
   if not m['tlvs']:
    assert m['head']==250
    if k in pending:assert k not in acks;acks.add(k)
    else:assert last and last[0]==k and not last[1];last=(k,True)
    continue
   if k not in pending and m['service']!=15:
    assert (m['service'],m['command']) not in ((1,1),(1,2))
    if started:notifications.append((m['event'],m['service'],m['command'],bytes(m['body']).hex()))
    continue
   assert k in pending,'Uncorrelated reserved or duplicate reply'
   m['_time']=r['uptime'];pairs.append((pending.pop(k),m));last=(k,k in acks)
assert not pending and not writes and not tx.buffer and not rx.buffer and not rx.body
v.same(notifications,[(r['eventID'],r['service'],r['command'],r['bodyHex']) for r in rows if r['event']=='native-service-notification'])
assert len(pairs)==6
assert [(a['event'],a['service'],a['command']) for a,b in pairs[:3]]==[(1,1,1),(2,1,2),(49,15,123)]
assert pairs[0][0]['body']==pairs[1][0]['body']==b''
assert pairs[0][1]['tlvs']==[(6,b'\0')]
assert len(pairs[1][1]['tlvs'])==1 and pairs[1][1]['tlvs'][0][0]==2
identity=v.loads(pairs[1][1]['tlvs'][0][1].removesuffix(b'\0'))
saved_identity=v.loads((folder/'device.json').read_bytes())
assert set(saved_identity)=={'model','mac','hver','fver','ver'}
v.same({k:identity[k] for k in saved_identity},saved_identity)
for k,val in dict(model='H001Y',mac='4C:3C:8F:90:CC:C3',hver='2.1.2',fver='1.3',ver='1.0.3.127').items():v.same(identity[k],val)
header=(ROOT/'captures/firmware'/release/'expected-app-header.bin').read_bytes()
pin={'dashboard-ram-002':'c7bd3f186f0d37277aa126c843a72a220886845e055013cfe547a1695601625a','reset-undo-trim-001':'76d7bfc287aad7294d4d855a86d4d2cfbe8043a3b555eca41a891e17b1f7a4e6'}[release]
assert len(header)==256 and hashlib.sha256(header).hexdigest()==pin
assert pairs[2][0]['tlvs']==[(1,bytes.fromhex('010000b01e000001'))]
wanted=dict(glassly='flash-read',abi=1,result='ok',device=0,offset=0x1eb000,length=256,hex=header.hex())
v.same(v.business(pairs[2][1]),wanted);v.same(v.loads((folder/'header-reply.json').read_bytes()),wanted)

assert [a['tlvs'] for a,b in pairs[3:]]==[[(1,b'\x0b')],[(1,bytes.fromhex('290000010000'))],[(1,b'\x0b')]]
assert [(a['event'],a['service'],a['command']) for a,b in pairs[3:]]==[(50,15,125),(51,15,125),(52,15,125)]
for index,state in [(3,'cleared'),(4,'stock-ui-active'),(5,'cleared')]:v.same(v.business(pairs[index][1]),dict(glassly='graphics',abi=1,result=state))
report=dict(passed=True,boot_verified=True,release=release,app_header_sha256=pin,capture=str(folder.relative_to(ROOT)),ram_measurement_completed=False,reason='Native display ownership gate returned stock-ui-active; failure cleanup verified',flash_mutations=0,ota_commands=0,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),capture_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()})
out=Path(sys.argv[3]);assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
