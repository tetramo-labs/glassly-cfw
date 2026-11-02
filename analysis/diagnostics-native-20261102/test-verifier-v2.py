"""Synthetic positive/fault traces; never connects to hardware or admits images."""
if not __debug__: raise RuntimeError('Assertions required; optimized execution refused')
from pathlib import Path
import copy,hashlib,importlib.util,json,struct,subprocess,sys
HERE=Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('diagnostic_verifier',HERE/'verify-smoke-v2.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);FOLDER=OUT/'synthetic-capture';FOLDER.mkdir()
header=bytes(range(256));pins={'app_header_sha256':hashlib.sha256(header).hexdigest()}
rows=[];now=0.;event=0x30;snap_indices=[];response_indices=[]
def add(kind,**values):
 global now
 now+=.001;rows.append(dict(event=kind,uptime=now,utc='SYNTHETIC',**values));return len(rows)-1

def tlv(kind,data):return bytes([kind])+len(data).to_bytes(3,'big')+data

def frames(ev,svc,cmd,body,limit=503):
 # Independent packet framing/checksum, no imported encoder.
 result=[]
 for i,at in enumerate(range(0,max(1,len(body)),limit)):
  p=bytes([250 if not i else i])+(len(body)+9).to_bytes(3,'big')+bytes([ev,svc,cmd])+body[at:at+limit]
  result.append(p+(sum(p)&65535).to_bytes(2,'big'))
 return b''.join(result)

def pair(svc,cmd,body,response,ev=None,kind=5):
 global event
 if ev is None:event=event%255+1;ev=event
 req=frames(ev,svc,cmd,body,642)
 # Real RFCOMM MTU can split a GM frame; each submitted segment completes.
 for at in range(0,len(req),31):
  part=req[at:at+31];add('transmitSubmission',hex=part.hex(),status=None);add('transmitCompletion',hex=part.hex(),status=0)
 raw=json.dumps(response,separators=(',',':')).encode() if isinstance(response,dict) else response
 reply=frames(ev,svc,cmd,tlv(kind,raw))
 idx=add('receive',hex=reply.hex(),status=None);response_indices.append(idx);return ev,idx

def custom(cmd,body,response):return pair(15,cmd,tlv(1,body),response)
def draw(body,result='ok'):
 response={'glassly':'graphics','abi':1,'result':result}
 if result=='ok':response['presentation']='scheduled'
 return custom(125,body,response)
def state(flags,hidden,seen,resync,last,high,worker=0,failed=0,epoch=65534):
 return dict(flags=flags,hidden=hidden,seen=seen,resync=resync,lastFrameID=last,highFrameID=high,displayWorkerFailures=worker,displayAllocationFailures=0,lastFailedMode=failed,savedSceneEpoch=epoch)
def snap(label,s,body=b'\x07\xff'):
 raw=struct.pack('<4BHHIIBBH',s['flags'],s['hidden'],s['seen'],s['resync'],s['lastFrameID'],s['highFrameID'],s['displayWorkerFailures'],s['displayAllocationFailures'],s['lastFailedMode'],0,s['savedSceneEpoch'])
 ev,i=custom(125,body,dict(glassly='diagnostics',abi=1,result='ok',presentation='unchanged',stateHex=raw.hex()));snap_indices.append(i)
 add('diagnostic-snapshot',label=label,eventID=ev,snapshot=s)
def reset(req,epoch):
 raw=struct.pack('<BHBHI',41,req,0,epoch,1)+b'\0\x40\0'
 custom(125,b'\x29'+struct.pack('<HHBB',0,req,0,250),dict(glassly='scene',abi=1,result='ok',replyHex=raw.hex()));add('scene-reset',request=req,epoch=epoch)
def inp(active=False):
 reply=dict(glassly='input',abi=1,result='ok',active=active,nonce=0x47414944 if active else 0,mask=1 if active else 0,capacity=32,leaseTicks=30000,sequence=0,ack=0,drops=0,exhausted=False,records=[])
 custom(124,b'\x01\x01\x01DIAG' if active else b'\x01\0',reply);add('input-observer',active=active,mask=1 if active else 0)
black=b'\x06'+b'\0\0\xff\xff'*3+b'\0\0\x53\x34';title=b'\x0f\x50\0\x64\0\x1f\x04DIAG'
def delta(fid):return b'\x03\0\0\x01\x01'+struct.pack('<H',fid)+b'\x80'
(FOLDER/'black-frame-command.bin').write_bytes(black);(FOLDER/'title-command.bin').write_bytes(title)
pair(1,1,b'',b'\0',ev=1,kind=6)
pair(1,2,b'',dict(model='H001Y',mac='4C:3C:8F:90:CC:C3',hver='2.1.2',fver='1.3'),ev=2,kind=2)
custom(123,bytes([1,0,0,0xb0,0x1e,0,0,1]),dict(glassly='flash-read',abi=1,result='ok',device=0,offset=0x1eb000,length=256,hex=header.hex()))
caps=dict(v.CAPS,freeBytesHex='00050000',lowWaterBytesHex='00040000',inputObserver=dict(command=124,capacity=32,leaseTicks=30000))
pair(15,126,b'',caps)
draw(b'\x0b','cleared');inp();reset(1,65535)
s=state(0,True,False,False,0,0)
snap('clear',s,b'\x07\0');snap('missing-sub',s,b'\x07');snap('unknown-high-trailing',s,b'\x87\xff\x01\x02')
draw(black);snap('key-resync',state(0,True,True,True,0,0))
for fid,label,flags,last,high in [(10,'frame10',0,10,10),(12,'frame12',2,12,12),(12,'duplicate12',6,12,12),(11,'reorder11',7,11,12)]:
 draw(delta(fid));snap(label,state(flags,True,True,False,last,high))
draw(black);snap('key-preserves-ring',state(7,True,True,True,11,12))
draw(delta(12));snap('duplicate-after-key',state(7,True,True,True,11,12))
draw(delta(13));snap('resynced13',state(7,True,True,False,13,13))
snap('show-high-trailing',state(7,False,True,False,13,13),b'\x87\x02\xff');draw(title)
snap('hide-trailing',state(7,True,True,False,13,13),b'\x07\x01\xff');draw(title)
snap('show-before-failure',state(7,False,True,False,13,13),b'\x07\x02')
draw(b'\x09'+bytes(16),'invalid');snap('worker-failure',state(7,False,True,False,13,13,1,9))
inp(True);draw(b'\x8b\0\xff','cleared');snap('cleanup-saved-epoch',state(7,True,True,False,13,13,1,9,1));inp()
draw(b'\x0b\xff','cleared');snap('cleanup-idempotent',state(7,True,True,False,13,13,1,9,1));inp()
reset(2,2);draw(black);snap('show-before-present',state(7,False,True,True,13,13,1,9,1),b'\x07\x02');draw(title)
add('pattern-visible',hardwarePixelReadback=False)
for _ in range(1200):now+=.25;draw(b'\x24\0')
add('hold-ended',finishRequested=False)
draw(b'\x0b','cleared');snap('final-cleanup',state(7,True,True,True,13,13,1,9,3));inp()
add('smoke-complete',cleared=True,observerInactive=True,hardwarePixelReadback=False,continuousPixelRetentionProven=False)
original=copy.deepcopy(rows)

def change_json(case,index,transform):
 row=case[index];wire=bytes.fromhex(row['hex']);assert len(wire)==int.from_bytes(wire[1:4],'big')
 data=wire[11:-2];value=json.loads(data);new=transform(value)
 raw=new if isinstance(new,bytes) else json.dumps(new,separators=(',',':')).encode()
 row['hex']=frames(wire[4],wire[5],wire[6],tlv(5,raw)).hex()
def set_field(field,value):return lambda d:{**d,field:value}
def mutate_state(index,value):
 def f(d):
  b=bytearray.fromhex(d['stateHex']);b[index]=value;d['stateHex']=b.hex();return d
 return f
results=[]
def run(name,mutation=None,valid=False):
 case=copy.deepcopy(original)
 if mutation:mutation(case)
 (FOLDER/'trace.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in case))
 try:report=v.verify(FOLDER,pins,header);accepted=True;error=None
 except Exception as e:accepted=False;error=repr(e)
 assert accepted==valid,(name,accepted,error)
 results.append(dict(name=name,expected_acceptance=valid,accepted=accepted,error=error))
 if valid:(OUT/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
run('valid-timeout-wraparound',valid=True)
# Rebase the complete valid trace independently to a fresh native clock seed.
def fresh_seed(case,first=33149):
 next1=first+1 if first<65535 else 1
 next2=next1+1 if next1<65535 else 1
 next3=next2+1 if next2<65535 else 1
 mapping={65534:0,1:next1,3:next3}
 for i,row in enumerate(case):
  if row['event']=='diagnostic-snapshot':row['snapshot']={**row['snapshot'],'savedSceneEpoch':mapping[row['snapshot']['savedSceneEpoch']]}
  elif row['event']=='scene-reset':row['epoch']=first if row['request']==1 else next2
  elif row['event']=='receive':
   w=bytes.fromhex(row['hex'])
   if len(w)!=int.from_bytes(w[1:4],'big') or w[7]!=5:continue
   d=json.loads(w[11:-2])
   if d.get('glassly')=='diagnostics':
    b=bytearray.fromhex(d['stateHex']);old=int.from_bytes(b[18:20],'little');b[18:20]=mapping[old].to_bytes(2,'little');d['stateHex']=b.hex()
   elif d.get('glassly')=='scene':
    b=bytearray.fromhex(d['replyHex']);request=int.from_bytes(b[1:3],'little');b[4:6]=(first if request==1 else next2).to_bytes(2,'little');d['replyHex']=b.hex()
   else:continue
   row['hex']=frames(w[4],w[5],w[6],tlv(5,json.dumps(d,separators=(',',':')).encode())).hex()
run('valid-fresh-seed33149',fresh_seed,True)
run('valid-fresh-seed-wrap65535',lambda c:fresh_seed(c,65535),True)

snap0=snap_indices[0]
run('fresh-zero-epoch-rejected',lambda c:fresh_seed(c,0))
run('retained-increment-still-required',lambda c:change_json(c,snap0,mutate_state(18,253)))
for name,transform in [('boolean-abi',set_field('abi',True)),('wrong-presentation',set_field('presentation','scheduled')),('extra-key',set_field('extra',0)),('short-hex',lambda d:{**d,'stateHex':d['stateHex'][:-2]}),('uppercase-hex',lambda d:{**d,'stateHex':d['stateHex'].upper()}),('bad-flag',mutate_state(0,128)),('bad-bool',mutate_state(1,2)),('bad-reserved',mutate_state(17,1)),('duplicate-key',lambda d:json.dumps(d,separators=(',',':')).replace('"abi":1','"abi":1,"abi":1').encode())]:
 run(name,lambda c,f=transform:change_json(c,snap0,f))
run('counter-producer-wrong',lambda c:change_json(c,snap_indices[14],mutate_state(8,2)))
run('ring-cleared-by-key',lambda c:change_json(c,snap_indices[9],mutate_state(0,0)))
run('cleanup-wrong-epoch',lambda c:change_json(c,snap_indices[15],mutate_state(18,2)))
run('logged-snapshot-false',lambda c:next(r for r in c if r['event']=='diagnostic-snapshot')['snapshot'].update(flags=1))
run('missing-completion',lambda c:c.pop(next(i for i,r in enumerate(c) if r['event']=='transmitCompletion')))
run('completion-bool',lambda c:next(r for r in c if r['event']=='transmitCompletion').update(status=False))
run('duplicate-reply',lambda c:c.insert(snap0+1,copy.deepcopy(c[snap0])))
# Corrupt event while repairing checksum, so correlation (not checksum) rejects.
def bad_event(c):
 wire=bytearray.fromhex(c[snap0]['hex']);wire[4]^=64;wire[-2:]=(sum(wire[:-2])&65535).to_bytes(2,'big');c[snap0]['hex']=wire.hex()
run('wrong-response-event',bad_event)
def overlap(c):
 i=next(i for i in range(snap0+1,len(c)) if c[i]['event']=='transmitSubmission');item=c.pop(i);item['uptime']=c[snap0]['uptime'];c.insert(snap0,item)
run('overlapping-request',overlap)
def shortened(c):
 start=next(r['uptime'] for r in c if r['event']=='pattern-visible')
 for r in c:
  if r['uptime']>start:r['uptime']=start+(r['uptime']-start)/10
run('short-hold',shortened)
run('finish-without-sentinel',lambda c:next(r for r in c if r['event']=='hold-ended').update(finishRequested=True))
(FOLDER/'finish-requested.json').write_text(json.dumps(dict(reason='user confirmed visible pattern')))
run('valid-finish-sentinel',lambda c:next(r for r in c if r['event']=='hold-ended').update(finishRequested=True),True)
(FOLDER/'finish-requested.json').unlink()
# Additional actual wire/schema and cleanup invariants, not just log mutations.
def find_response(predicate):
 for i in response_indices:
  w=bytes.fromhex(original[i]['hex'])
  if len(w)!=int.from_bytes(w[1:4],'big') or w[7]!=5:continue
  d=json.loads(w[11:-2])
  if predicate(d):return i
 raise AssertionError('Missing synthetic response')
input_active=find_response(lambda d:d.get('glassly')=='input' and d.get('active') is True)
input_inactive=find_response(lambda d:d.get('glassly')=='input' and d.get('active') is False)
run('input-mask3',lambda c:change_json(c,input_active,set_field('mask',3)))
run('cleanup-observer-active',lambda c:change_json(c,input_inactive,set_field('active',True)))
run('input-bool-capacity',lambda c:change_json(c,input_active,set_field('capacity',True)))
run('snapshot-bool-hex',lambda c:change_json(c,snap0,set_field('stateHex',True)))
run('unexpected-settled',lambda c:change_json(c,snap0,lambda d:dict(glassly='scene',abi=1,result='settled',tag=1)))
# ACKs are optional for these one-frame commands, but head/correlation/count are checked.
def add_ack(c,head=250,duplicate=False):
 w=bytes.fromhex(c[snap0]['hex']);p=bytes([head,0,0,9])+w[4:7];ack=p+(sum(p)&65535).to_bytes(2,'big')
 row=dict(event='receive',uptime=c[snap0]['uptime'],utc='SYNTHETIC',hex=ack.hex(),status=None)
 c.insert(snap0,row)
 if duplicate:c.insert(snap0,copy.deepcopy(row))
run('valid-optional-final-ack',lambda c:add_ack(c),True)
run('wrong-ack-head',lambda c:add_ack(c,1))
run('duplicate-ack',lambda c:add_ack(c,250,True))
def late_ack(c,when='after',duplicate=False):
 w=bytes.fromhex(c[snap0]['hex']);p=b'\xfa\0\0\x09'+w[4:7];ack=p+(sum(p)&65535).to_bytes(2,'big')
 at=snap0+1
 if when in ('next-pending','stale'):
  at=next(i for i in range(snap0+1,len(c)) if c[i]['event']=='receive')
  if when=='stale':at+=1
 row=dict(event='receive',uptime=c[at-1]['uptime'],utc='SYNTHETIC',hex=ack.hex(),status=None)
 c.insert(at,row)
 if duplicate:c.insert(at,copy.deepcopy(row))
run('valid-ack-after-business',lambda c:late_ack(c),True)
run('valid-previous-ack-next-request-pending',lambda c:late_ack(c,'next-pending'),True)
run('stale-ack-after-next-business',lambda c:late_ack(c,'stale'))
run('duplicate-completed-ack',lambda c:late_ack(c,duplicate=True))
def early_and_late(c):
 late_ack(c);add_ack(c)
run('duplicate-before-and-after-business',early_and_late)

# Non-ASCII invalid byte, incomplete packet, all are rejected before completion.
run('truncated-final-rx',lambda c:c.__setitem__(response_indices[-1],{**c[response_indices[-1]],'hex':c[response_indices[-1]]['hex'][:-2]}))
proc=subprocess.run([sys.executable,'-O',str(HERE/'verify-smoke-v2.py')],capture_output=True,text=True)
assert proc.returncode and 'optimized execution is refused' in proc.stderr
results.append(dict(name='optimized-refused',expected_acceptance=False,accepted=False,error=proc.stderr.strip()))
# The preserved real stopped attempt is evidence for the fresh epoch, never a pass.
real=HERE.parents[1]/'captures/swift-mac-diagnostics-smoke-20261102-01'
realrows=[json.loads(line) for line in (real/'trace.jsonl').read_text().splitlines()]
assert realrows[-1]['event']=='failed' and 'Initial RESET epoch chain' in realrows[-1]['error']
assert [r['epoch'] for r in realrows if r['event']=='scene-reset']==[33149]
assert [r['snapshot']['savedSceneEpoch'] for r in realrows if r['event']=='diagnostic-snapshot']==[0]
wire=v.GmStream(legacy_repeat_fa=True,fragment_acks=True);native=[]
for row in realrows:
 if row['event']=='receive':native.extend(wire.feed(bytes.fromhex(row['hex'])))
actualscene=[v.business(m) for m in native if (m['service'],m['command'])==(15,125) and m['tlvs'] and v.business(m).get('glassly')=='scene']
actualdiag=[v.snapshot(m) for m in native if (m['service'],m['command'])==(15,125) and m['tlvs'] and v.business(m).get('glassly')=='diagnostics']
assert len(actualscene)==len(actualdiag)==1
assert int.from_bytes(bytes.fromhex(actualscene[0]['replyHex'])[4:6],'little')==33149
assert actualdiag[0]['savedSceneEpoch']==0

try:v.verify(real,pins,header)
except AssertionError:pass
else:raise AssertionError('Stopped hardware attempt incorrectly admitted as complete')
results.append(dict(name='real-stopped-attempt-still-incomplete',expected_acceptance=False,accepted=False,trace_sha256=hashlib.sha256((real/'trace.jsonl').read_bytes()).hexdigest()))

(FOLDER/'trace.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in original))
(FOLDER/'README.txt').write_text('Entirely synthetic protocol fixture. No hardware operations, wait, user confirmation or firmware admission took place.\n')
report=dict(passed=True,cases=len(results),results=results,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'verify-smoke-v2.py',Path(__file__)]})
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(len(results),'verifier cases passed')
