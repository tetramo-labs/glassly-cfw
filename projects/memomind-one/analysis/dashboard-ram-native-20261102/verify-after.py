"""Offline independent GM trace cross-check; no Swift helper result trusted as wire proof."""
if not __debug__: raise RuntimeError('Refuse -O')
import hashlib,importlib.util,json,math,sys
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('diagnostic_wire',ROOT/'analysis/diagnostics-native-20261102/verify-smoke-v2.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
assert len(sys.argv)==3,'CAPTURE_DIRECTORY NEW_REPORT_JSON required'
folder=Path(sys.argv[1]).resolve()
rows=[v.loads(line) for line in (folder/'trace.jsonl').read_text().splitlines()]
assert rows[-1]['event']=='measurement-complete' and not any(r['event']=='failed' for r in rows)
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
assert len(pairs)==13
assert [(a['service'],a['command']) for a,b in pairs]==[(1,1),(1,2),(15,123)]+[(15,126)]*10
assert [a['event'] for a,b in pairs]==[1,2,49]+list(range(50,60))
assert pairs[0][0]['body']==pairs[1][0]['body']==b''
assert pairs[0][1]['tlvs']==[(6,b'\0')]
assert len(pairs[1][1]['tlvs'])==1 and pairs[1][1]['tlvs'][0][0]==2
identity=v.loads(pairs[1][1]['tlvs'][0][1].removesuffix(b'\0'))
saved_identity=v.loads((folder/'device.json').read_bytes())
assert set(saved_identity)=={'model','mac','hver','fver','ver'}
v.same({k:identity[k] for k in saved_identity},saved_identity)
for k,val in dict(model='H001Y',mac='4C:3C:8F:90:CC:C3',hver='2.1.2',fver='1.3',ver='1.0.3.127').items():v.same(identity[k],val)
header=(ROOT/'captures/firmware/dashboard-ram-002/expected-app-header.bin').read_bytes()
assert len(header)==256 and hashlib.sha256(header).hexdigest()=='c7bd3f186f0d37277aa126c843a72a220886845e055013cfe547a1695601625a'
assert pairs[2][0]['tlvs']==[(1,bytes.fromhex('010000b01e000001'))]
wanted=dict(glassly='flash-read',abi=1,result='ok',device=0,offset=0x1eb000,length=256,hex=header.hex())
v.same(v.business(pairs[2][1]),wanted);v.same(v.loads((folder/'header-reply.json').read_bytes()),wanted)
logged=[r for r in rows if r['event']=='heap-sample'];assert len(logged)==10
result=v.loads((folder/'result.json').read_bytes());samples=[];gaps=[]
for i,(a,b) in enumerate(pairs[3:]):
 assert a['body']==b''
 caps=v.business(b)
 assert set(caps)==set(v.CAPS)|{'inputObserver','freeBytesHex','lowWaterBytesHex'}
 for k,val in v.CAPS.items():v.same(caps[k],val)
 v.same(caps['inputObserver'],dict(command=124,capacity=32,leaseTicks=30000))
 for key in ('freeBytesHex','lowWaterBytesHex'):
  h=caps[key];assert type(h) is str and len(h)==8 and all(c in '0123456789abcdef' for c in h)
 raw=b['tlvs'][0][1].removesuffix(b'\0')
 assert raw==(folder/f'capabilities-{i:02d}.json').read_bytes()
 item=dict(index=i,eventID=a['event'],freeBytes=int(caps['freeBytesHex'],16),lowWaterBytes=int(caps['lowWaterBytesHex'],16),freeBytesHex=caps['freeBytesHex'],lowWaterBytesHex=caps['lowWaterBytesHex'],uptime=result['samples'][i]['uptime'])
 v.same({k:logged[i][k] for k in item if k!='uptime'},{k:val for k,val in item.items() if k!='uptime'});v.same(result['samples'][i],item)
 assert item['uptime']<=logged[i]['uptime']
 assert b['_time']<=item['uptime']
 if i:gaps.append(a['_time']-logged[i-1]['uptime']);assert gaps[-1]>=0.49
 samples.append(item)
frees=[s['freeBytes'] for s in samples];lows=[s['lowWaterBytes'] for s in samples]
for k,val in dict(complete=True,sampleCount=10,minimumFreeBytes=min(frees),maximumFreeBytes=max(frees),minimumLowWaterBytes=min(lows),maximumLowWaterBytes=max(lows),flashMutations=0,displayCommands=0,otaCommands=0,automaticRetries=0,largestBlockSupported=False,telemetryIncludesTemporaryProbeAllocation=True,appHeaderSHA256=hashlib.sha256(header).hexdigest(),runtimeRelease='dashboard-ram-002').items():v.same(result[k],val)
report=dict(passed=True,device_actions=False,capture=str(folder.relative_to(ROOT)),wire_requests=13,wire_reply_pairs=13,heap_samples=10,wire_command_sequence=[[a['event'],a['service'],a['command'],a['body'].hex()] for a,b in pairs],no_display_or_ota_or_flash_mutation_commands=True,app_header_sha256=hashlib.sha256(header).hexdigest(),identity=identity,current_free_range=[min(frees),max(frees)],low_water_range=[min(lows),max(lows)],inter_request_pauses=gaps,saved_files_match_raw_replies=True,unsolicited_normal_messages=len(notifications),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'analysis/diagnostics-native-20261102/verify-smoke-v2.py',ROOT/'scripts/memomind_transport.py']},capture_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()},limitations=['Total pool accounting only; no largest block or owner attribution.','Telemetry includes temporary JSON allocation and connected transport activity.','Trace proves recorded transmitted commands and matching replies, not all autonomous device activity.'])
out=Path(sys.argv[2]);assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','wire_requests','heap_samples','current_free_range','low_water_range')}))
