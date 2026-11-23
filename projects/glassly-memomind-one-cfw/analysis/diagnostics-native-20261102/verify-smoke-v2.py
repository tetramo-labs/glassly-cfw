"""Independent raw-wire diagnostics smoke proof; no hardware operations."""
if not __debug__: raise RuntimeError('Verification requires assertions; optimized execution is refused')
from pathlib import Path
from collections import deque
import hashlib,json,math,struct,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from memomind_transport import GmStream,parse_tlvs

def unique(pairs):
 d={}
 for k,v in pairs:
  assert k not in d,'Duplicate JSON key';d[k]=v
 return d

def loads(raw):
 return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(AssertionError('Nonfinite JSON')))

def same(value,wanted):
 assert type(value) is type(wanted),(value,wanted)
 if isinstance(wanted,dict):
  assert value.keys()==wanted.keys()
  for k in wanted:same(value[k],wanted[k])
 elif isinstance(wanted,list):
  assert len(value)==len(wanted)
  for a,b in zip(value,wanted):same(a,b)
 else:assert value==wanted,(value,wanted)

def business(m):
 assert len(m['tlvs'])==1 and m['tlvs'][0][0]==5 and len(m['tlvs'][0][1])<=1024
 value=loads(m['tlvs'][0][1].removesuffix(b'\0').decode('utf8'))
 assert isinstance(value,dict) and type(value.get('abi')) is int and value['abi']==1
 return value

def snapshot(m):
 value=business(m);assert len(m['tlvs'][0][1])<=256
 h=value.get('stateHex');assert type(h) is str and len(h)==40 and all(c in '0123456789abcdef' for c in h)
 same(value,dict(glassly='diagnostics',abi=1,result='ok',presentation='unchanged',stateHex=h))
 b=bytes.fromhex(h);flags,hidden,seen,resync,last,high,worker,allocation,failed,reserved,epoch=struct.unpack('<4BHHIIBBH',b)
 assert flags<=7 and max(hidden,seen,resync)<=1 and reserved==0
 return dict(flags=flags,hidden=bool(hidden),seen=bool(seen),resync=bool(resync),lastFrameID=last,highFrameID=high,displayWorkerFailures=worker,displayAllocationFailures=allocation,lastFailedMode=failed,savedSceneEpoch=epoch)

def next_epoch(e):return e+1 if e<65535 else 1

def black():return b'\x06'+bytes.fromhex('0000ffff')*3+bytes.fromhex('00005334')
def delta(fid):return bytes([3,0,0,1,1])+struct.pack('<H',fid)+b'\x80'
def title():return b'\x0f'+struct.pack('<hhBB',80,100,31,4)+b'DIAG'
def reset(request):return b'\x29'+struct.pack('<HHBB',0,request,0,250)
def input_reply(active):return dict(glassly='input',abi=1,result='ok',active=active,nonce=0x47414944 if active else 0,mask=1 if active else 0,capacity=32,leaseTicks=30000,sequence=0,ack=0,drops=0,exhausted=False,records=[])
def graphics(result='ok'):
 d=dict(glassly='graphics',abi=1,result=result)
 if result=='ok':d['presentation']='scheduled'
 return d
CAPS=dict(flashRead=123,rasterLens='first-left',bundleMaxSegments=255,builtinText=True,maxGeometryRecords=255,leaseTicks=1000,tickMs=1,flashCanary=122,registryBytes=256,writableStaticBytes=256,glassly='graphics-runtime',abi=1,profile='H001Y-1.0.3.127',width=600,height=350,modes=[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41],diagnostics='native-v1',snapshotBytes=20,cleanup='graphics-input-current-screen',maxMessageBytes=8192,storeKiB=64,textMaxBytes=255,textFont='native-resource',missingGlyph='reject',emptyGeometry='lease-only',bundleModes=[3,6,9,15,19,20,36,37,38,39,40,41])

class Ingress:
 # Every smoke command has one <=642-byte body; native MTU writes may split it.
 def __init__(self):self.buffer=bytearray()
 def feed(self,data):
  self.buffer.extend(data);out=[]
  while len(self.buffer)>=7:
   n=int.from_bytes(self.buffer[1:4],'big');assert self.buffer[0]==250 and 9<=n<=651
   if len(self.buffer)<n:break
   p=bytes(self.buffer[:n]);del self.buffer[:n]
   assert sum(p[:-2])&65535==int.from_bytes(p[-2:],'big')
   body=p[7:-2];out.append(dict(head=250,event=p[4],service=p[5],command=p[6],body=body,tlvs=parse_tlvs(body)))
  return out

def verify(folder,pins,header):
 folder=Path(folder);rows=[loads(r) for r in (folder/'trace.jsonl').read_text().splitlines()]
 assert rows and rows[-1]['event']=='smoke-complete'
 times=[r['uptime'] for r in rows];assert all(type(t) in (int,float) and math.isfinite(t) for t in times)
 assert all(a<=b for a,b in zip(times,times[1:])), 'Time reversal'
 assert not any(r['event']=='failed' for r in rows)
 tx=Ingress();rx=GmStream(legacy_repeat_fa=True,fragment_acks=True);writes=deque();pending={};pairs=[];status=[];started=False;acks=set();last_completed=None
 for row in rows:
  if row['event']=='transmitSubmission':
   assert not pending,'Overlapping business requests'
   data=bytes.fromhex(row['hex']);assert data;writes.append(data)
   for m in tx.feed(data):
    k=(m['event'],m['service'],m['command']);assert not pending
    m['_time']=row['uptime'];pending[k]=m;acks.discard(k)
    if m['service']==15:started=True
  elif row['event']=='transmitCompletion':
   assert type(row['status']) is int and row['status']==0 and writes
   assert writes.popleft()==bytes.fromhex(row['hex'])
  elif row['event']=='receive':
   for m in rx.feed(bytes.fromhex(row['hex'])):
    k=(m['event'],m['service'],m['command'])
    if not m['tlvs']:
     assert m['head']==250,'Unexpected ACK head'
     if k in pending:
      assert k not in acks,'Duplicate current ACK';acks.add(k)
     else:
      assert last_completed is not None and k==last_completed[0] and not last_completed[1],'Stale/duplicate completed ACK'
      last_completed=(k,True)
     continue
    if k not in pending and m['service']!=15:
     assert (m['service'],m['command']) not in ((1,1),(1,2))
     if started:status.append((m['event'],m['service'],m['command'],bytes(m['body']).hex()))
     continue
    assert k in pending,'Uncorrelated/duplicate reply'
    pairs.append((pending.pop(k),m));last_completed=(k,k in acks)
 assert not pending and not writes and not tx.buffer and not rx.buffer and not rx.body
 same(status,[(r['eventID'],r['service'],r['command'],r['bodyHex']) for r in rows if r['event']=='native-service-notification'])
 assert len(pairs)>=4 and [(a['service'],a['command']) for a,b in pairs[:4]]==[(1,1),(1,2),(15,123),(15,126)]
 assert pairs[0][0]['tlvs']==pairs[1][0]['tlvs']==pairs[3][0]['tlvs']==[]
 assert pairs[0][1]['tlvs']==[(6,b'\0')]
 assert len(pairs[1][1]['tlvs'])==1 and pairs[1][1]['tlvs'][0][0]==2
 identity=loads(pairs[1][1]['tlvs'][0][1].removesuffix(b'\0'))
 for k,v in dict(model='H001Y',mac='4C:3C:8F:90:CC:C3',hver='2.1.2',fver='1.3').items():same(identity[k],v)
 assert pairs[2][0]['tlvs']==[(1,bytes([1,0,0,0xb0,0x1e,0,0,1]))]
 assert len(header)==256 and hashlib.sha256(header).hexdigest()==pins['app_header_sha256']
 same(business(pairs[2][1]),dict(glassly='flash-read',abi=1,result='ok',device=0,offset=0x1eb000,length=256,hex=header.hex()))
 caps=business(pairs[3][1])
 for k,v in CAPS.items():same(caps[k],v)
 same(caps['inputObserver'],dict(command=124,capacity=32,leaseTicks=30000))
 assert set(caps)==set(CAPS)|{'inputObserver','freeBytesHex','lowWaterBytesHex'}
 for k in ['freeBytesHex','lowWaterBytesHex']:
  h=caps[k];assert type(h) is str and len(h)==8 and all(c in '0123456789abcdef' for c in h)
 assert (folder/'black-frame-command.bin').read_bytes()==black() and (folder/'title-command.bin').read_bytes()==title()
 # Decode all RLE runs independently, proving exact210000 black pixels.
 p=1;count=0;key=black()
 while p<len(key):
  op=key[p];p+=1;assert op&15==0;n=op>>4
  if not n:
   n=key[p];p+=1
   if not n:n=int.from_bytes(key[p:p+2],'little');p+=2
  assert n>0;count+=n
 assert count==210000 and p==len(key)
 at=4;snapshots=[];resets=[];input_logs=[]
 def take(cmd,body):
  nonlocal at
  assert at<len(pairs);a,b=pairs[at];at+=1
  assert (a['service'],a['command'])==(15,cmd) and a['tlvs']==[(1,body)]
  return a,b
 def draw(body,result='ok'):
  a,b=take(125,body);same(business(b),graphics(result));return a
 def inp(active=False):
  a,b=take(124,b'\x01\x01\x01DIAG' if active else b'\x01\0');same(business(b),input_reply(active));input_logs.append(dict(active=active,mask=1 if active else 0))
 def scene(req):
  a,b=take(125,reset(req));value=business(b);h=value.get('replyHex')
  assert type(h) is str and len(h)==26 and all(c in '0123456789abcdef' for c in h)
  same(value,dict(glassly='scene',abi=1,result='ok',replyHex=h));raw=bytes.fromhex(h)
  mode,r,status_,epoch,revision=struct.unpack('<BHBHI',raw[:10]);assert (mode,r,status_)==(41,req,0) and epoch and raw[10:]==b'\0\x40\0'
  resets.append(dict(request=req,epoch=epoch));return epoch
 def snap(label,flags,hidden,seen,resync,last,high,worker=0,failed=0,epoch=None,body=b'\x07\xff'):
  a,b=take(125,body);s=snapshot(b)
  wanted=dict(flags=flags,hidden=hidden,seen=seen,resync=resync,lastFrameID=last,highFrameID=high,displayWorkerFailures=worker,displayAllocationFailures=0,lastFailedMode=failed,savedSceneEpoch=s['savedSceneEpoch'] if epoch is None else epoch)
  same(s,wanted);snapshots.append(dict(label=label,eventID=a['event'],snapshot=s));return s
 draw(b'\x0b','cleared');inp();epoch=scene(1)
 base=snap('clear',0,True,False,False,0,0,body=b'\x07\0');saved=base['savedSceneEpoch']
 # Zero has no retained epoch: native cfw_cache_epoch seeds from clock before RESET.
 # scene() already requires nonzero epoch; only retained values imply next(saved).
 if saved:assert epoch==next_epoch(saved)
 snap('missing-sub',0,True,False,False,0,0,epoch=saved,body=b'\x07')
 snap('unknown-high-trailing',0,True,False,False,0,0,epoch=saved,body=b'\x87\xff\x01\x02')
 draw(black());snap('key-resync',0,True,True,True,0,0,epoch=saved)
 for fid,label,flags,last,high in [(10,'frame10',0,10,10),(12,'frame12',2,12,12),(12,'duplicate12',6,12,12),(11,'reorder11',7,11,12)]:
  draw(delta(fid));snap(label,flags,True,True,False,last,high,epoch=saved)
 draw(black());snap('key-preserves-ring',7,True,True,True,11,12,epoch=saved)
 draw(delta(12));snap('duplicate-after-key',7,True,True,True,11,12,epoch=saved)
 draw(delta(13));snap('resynced13',7,True,True,False,13,13,epoch=saved)
 snap('show-high-trailing',7,False,True,False,13,13,epoch=saved,body=b'\x87\x02\xff');draw(title())
 snap('hide-trailing',7,True,True,False,13,13,epoch=saved,body=b'\x07\x01\xff');draw(title())
 snap('show-before-failure',7,False,True,False,13,13,epoch=saved,body=b'\x07\x02')
 draw(b'\x09'+bytes(16),'invalid');snap('worker-failure',7,False,True,False,13,13,1,9,epoch=saved)
 inp(True);draw(b'\x8b\0\xff','cleared');snap('cleanup-saved-epoch',7,True,True,False,13,13,1,9,next_epoch(epoch));inp()
 draw(b'\x0b\xff','cleared');snap('cleanup-idempotent',7,True,True,False,13,13,1,9,next_epoch(epoch));inp()
 second=scene(2);assert second==next_epoch(next_epoch(epoch))
 draw(black());snap('show-before-present',7,False,True,True,13,13,1,9,next_epoch(epoch),body=b'\x07\x02');visual=draw(title())
 visible=[r for r in rows if r['event']=='pattern-visible'];ends=[r for r in rows if r['event']=='hold-ended'];assert len(visible)==len(ends)==1
 start=visible[0]['uptime'];assert start>=visual['_time']
 renewals=[]
 while at<len(pairs) and pairs[at][0]['tlvs']==[(1,b'\x24\0')]:renewals.append(draw(b'\x24\0')['_time'])
 clear=draw(b'\x0b','cleared');snap('final-cleanup',7,True,True,True,13,13,1,9,next_epoch(second));inp()
 assert at==len(pairs)
 same(snapshots,[{k:r[k] for k in ['label','eventID','snapshot']} for r in rows if r['event']=='diagnostic-snapshot'])
 same(resets,[{k:r[k] for k in ['request','epoch']} for r in rows if r['event']=='scene-reset'])
 same(input_logs,[{k:r[k] for k in ['active','mask']} for r in rows if r['event']=='input-observer'])
 end=ends[0];assert type(end['finishRequested']) is bool and start<=end['uptime']<=clear['_time']
 if end['finishRequested']:
  finish=loads((folder/'finish-requested.json').read_text());assert finish['reason']=='user confirmed visible pattern'
 else:assert clear['_time']-start>=300
 hold=[start]+renewals+[clear['_time']];assert all(a<=b for a,b in zip(hold,hold[1:]));assert renewals
 same({k:rows[-1][k] for k in ['cleared','observerInactive','hardwarePixelReadback','continuousPixelRetentionProven']},dict(cleared=True,observerInactive=True,hardwarePixelReadback=False,continuousPixelRetentionProven=False))
 return dict(format='memomind-native-diagnostics-smoke-verification-v2',complete=True,capture=str(folder),requests=len(pairs),snapshots=len(snapshots),all_native_writes_completed=True,probe_header_caps_verified=True,frame_ring_resync_verified=True,worker_dispatch_failure_counter_verified=True,allocation_failure_injection_performed=False,cleanup_observer_inactive=True,initial_saved_epoch=saved,initial_epoch_origin='retained-increment' if saved else 'fresh-clock-seed',epochs=[epoch,next_epoch(epoch),second,next_epoch(second)],lease_renewals=len(renewals),hold_seconds=clear['_time']-start,max_hold_submission_gap=max(b-a for a,b in zip(hold,hold[1:])),finish_requested=end['finishRequested'],hardware_pixel_readback=False,continuous_pixel_retention_proven=False,overlay_font_equivalent_to_g2=False,epoch_persistence_scope='successful allocation/current-screen only',visual_confirmation='separate user observation required',trace_sha256=hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest())

if __name__=='__main__':
 assert len(sys.argv)==3,'capture directory and NEW report path required'
 folder,out=map(Path,sys.argv[1:]);assert not out.exists()
 pins=loads((ROOT/'analysis/diagnostics-native-20261102/candidate-pins.json').read_text())
 header=(ROOT/'captures/firmware/diagnostic-commands-001/expected-app-header.bin').read_bytes()
 image=(ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
 runtime=(ROOT/'runtime/build/diagnostic-commands-001/graphics.bin').read_bytes()
 for data,prefix in [(image,'image'),(runtime,'runtime')]:
  assert type(pins[prefix+'_bytes']) is int and len(data)==pins[prefix+'_bytes']
  assert hashlib.sha256(data).hexdigest()==pins[prefix+'_sha256']
 report=verify(folder,pins,header)
 report['candidate_local_files_verified']={k:pins[k] for k in ['image_sha256','image_bytes','runtime_sha256','runtime_bytes','app_header_sha256']}
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
