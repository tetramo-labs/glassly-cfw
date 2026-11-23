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
assert rows[-1]['event']=='scratch-probe-complete' and not any(r['event']=='failed' for r in rows)
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
assert len(pairs)==70
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
position=3;epoch=0;lease_times=[]
def get(command,payload=None):
 global position
 a,b=pairs[position];position+=1
 assert (a['service'],a['command'])==(15,command)
 assert a['event']==49+position-3
 if payload is None:assert a['body']==b''
 else:assert a['tlvs']==[(1,payload)]
 return a,b
def graphics(payload,result='ok'):
 a,b=get(125,payload);wanted=dict(glassly='graphics',abi=1,result=result)
 if result=='ok':wanted['presentation']='scheduled'
 v.same(v.business(b),wanted);lease_times.append(a['_time'])
def scene(mode,number):
 global epoch
 body=bytes([mode])+epoch.to_bytes(2,'little')+number.to_bytes(2,'little')
 body+=b'\0' if mode==41 else bytes.fromhex('01010000000100000003010700050005000a0005000000000000000000')
 a,b=get(125,body);r=v.business(b)
 assert set(r)=={'glassly','abi','result','replyHex'}
 v.same({k:r[k] for k in ('glassly','abi','result')},dict(glassly='scene',abi=1,result='ok'))
 h=r['replyHex'];assert all(c in '0123456789abcdef' for c in h)
 raw=bytes.fromhex(h);new=int.from_bytes(raw[4:6],'little')
 assert len(raw)==(13 if mode==41 else 11) and raw[0]==mode and int.from_bytes(raw[1:3],'little')==number and raw[3]==0 and new and raw[10]==0
 assert int.from_bytes(raw[6:10],'little')==(0 if mode==41 else 1)
 if mode==41:assert raw[11:]==b'\x40\0';assert not epoch or new==epoch
 else:assert new==epoch
 epoch=new;v.same(v.loads((folder/f'scene-{number}.json').read_bytes()),r);lease_times.append(a['_time'])
def caps(command_pair):
 a,b=command_pair;d=v.business(b)
 assert set(d)==set(v.CAPS)|{'inputObserver','freeBytesHex','lowWaterBytesHex'}
 for k,val in v.CAPS.items():v.same(d[k],val)
 v.same(d['inputObserver'],dict(command=124,capacity=32,leaseTicks=30000))
 for k in ('freeBytesHex','lowWaterBytesHex'):
  assert type(d[k]) is str and len(d[k])==8 and all(c in '0123456789abcdef' for c in d[k])
 return d
samples=[];graphics(b'\x0b','cleared');scene(41,1);scene(37,2)
for phase in ('put','reset','reacquired'):
 if phase=='reset':scene(41,3)
 if phase=='reacquired':scene(37,4)
 for index in range(10):
  graphics(b'\x24\0');a,b=get(126);d=caps((a,b))
  v.same(v.loads((folder/f'{phase}-{index}.json').read_bytes()),d)
  samples.append(dict(phase=phase,index=index,eventID=a['event'],freeBytes=int(d['freeBytesHex'],16),lowWaterBytes=int(d['lowWaterBytesHex'],16)))
graphics(b'\x0b','cleared');d=caps(get(126));v.same(v.loads((folder/'capabilities-after-cleanup.json').read_bytes()),d)
assert position==len(pairs)
assert max(y-x for x,y in zip(lease_times,lease_times[1:]))<1.0,'Lease gap can invalidate allocation history'
result=v.loads((folder/'result.json').read_bytes())
v.same(result,dict(complete=True,release=release,appHeaderSHA256=pin,samples=samples,cleanupVerified=True,physicalOutputConfirmed=False,flashMutations=0,otaCommands=0))
logged=[{k:r[k] for k in samples[0]} for r in rows if r['event']=='heap-sample'];v.same(logged,samples)
import statistics
phases={phase:[s['freeBytes'] for s in samples if s['phase']==phase] for phase in ('put','reset','reacquired')}
stats={phase:dict(samples=x,minimum=min(x),maximum=max(x),median=statistics.median(x)) for phase,x in phases.items()}
report=dict(passed=True,capture=str(folder.relative_to(ROOT)),release=release,wire_requests=len(pairs),boot_header_verified=True,app_header_sha256=pin,phases=stats,reset_minus_put_median_bytes=stats['reset']['median']-stats['put']['median'],reset_minus_reacquired_median_bytes=stats['reset']['median']-stats['reacquired']['median'],cleanup_verified=True,after_cleanup_free_bytes=int(d['freeBytesHex'],16),maximum_lease_gap=max(y-x for x,y in zip(lease_times,lease_times[1:])),no_ota_or_flash_mutation_commands=True,hardware_visual_confirmed=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'analysis/diagnostics-native-20261102/verify-smoke-v2.py',ROOT/'scripts/memomind_transport.py']},capture_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()},limitations=['Native free-byte accounting includes query allocation and asynchronous activity; no largest-block or allocator-owner telemetry.','Raw application TX/RX, not independent HCI capture.'])
out=Path(sys.argv[3]);assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','release','reset_minus_put_median_bytes','reset_minus_reacquired_median_bytes')}))
