"""Synthetic positive and fault captures for independent scratch wire proof."""
import copy,hashlib,json,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from memomind_transport import gm_frames
BASE=json.loads((ROOT/'captures/swift-mac-ram-after-cleanup-20261102-01/capabilities-09.json').read_text())
def tlv(kind,value):return bytes([kind])+len(value).to_bytes(3,'big')+value
def packed(d):return json.dumps(d,separators=(',',':')).encode()
def fixture(release):
 rows=[];files={};now=1.;event=0x30;samples=[]
 def log(ev,**fields):rows.append(dict(event=ev,uptime=now,**fields))
 def query(service,cmd,body,response,kind=5,eid=None):
  nonlocal now,event
  if eid is None:event+=1;eid=event
  for raw in gm_frames(eid,service,cmd,body,fragment_payload=642):log('transmitSubmission',hex=raw.hex());log('transmitCompletion',hex=raw.hex(),status=0)
  now+=.001
  value=packed(response)+b'\0' if isinstance(response,dict) else response
  for raw in gm_frames(eid,service,cmd,tlv(kind,value)):log('receive',hex=raw.hex())
  now+=.001
  return eid
 identity=dict(model='H001Y',mac='4C:3C:8F:90:CC:C3',hver='2.1.2',fver='1.3',ver='1.0.3.127')
 query(1,1,b'',b'\0',6,eid=1);query(1,2,b'',identity,2,eid=2);files['device.json']=identity
 header=(ROOT/'captures/firmware'/release/'expected-app-header.bin').read_bytes();pin=hashlib.sha256(header).hexdigest()
 d=dict(glassly='flash-read',abi=1,result='ok',device=0,offset=0x1eb000,length=256,hex=header.hex());query(15,123,tlv(1,bytes.fromhex('010000b01e000001')),d);files['header-reply.json']=d
 def graphics(payload,result='ok'):
  d=dict(glassly='graphics',abi=1,result=result)
  if result=='ok':d['presentation']='scheduled'
  query(15,125,tlv(1,payload),d)
 epoch=0
 def scene(mode,number):
  nonlocal epoch
  payload=struct.pack('<BHH',mode,epoch,number)
  if mode==41:payload+=b'\0'
  else:payload+=struct.pack('<BIIBBBB8h',1,1,1,3,1,7,0,5,5,10,5,0,0,0,0)
  epoch=epoch or 32
  reply=struct.pack('<BHBHI',mode,number,0,epoch,0 if mode==41 else 1)+b'\0'
  if mode==41:reply+=struct.pack('<H',64)
  d=dict(glassly='scene',abi=1,result='ok',replyHex=reply.hex());query(15,125,tlv(1,payload),d);files[f'scene-{number}.json']=d
 graphics(b'\x0b','cleared');scene(41,1);scene(37,2)
 for phase in ('put','reset','reacquired'):
  if phase=='reset':scene(41,3)
  if phase=='reacquired':scene(37,4)
  for index in range(10):
   graphics(b'\x24\0');d=copy.deepcopy(BASE);free=150000+(46756 if release=='reset-undo-trim-001' and phase=='reset' else 0)+index
   d['freeBytesHex']=f'{free:08x}';d['lowWaterBytesHex']='00010000';eid=query(15,126,b'',d);files[f'{phase}-{index}.json']=d
   item=dict(phase=phase,index=index,eventID=eid,freeBytes=free,lowWaterBytes=65536);samples.append(item);log('heap-sample',**item);now+=.1
 graphics(b'\x0b','cleared');query(15,126,b'',BASE);files['capabilities-after-cleanup.json']=BASE
 files['result.json']=dict(complete=True,release=release,appHeaderSHA256=pin,samples=samples,cleanupVerified=True,physicalOutputConfirmed=False,flashMutations=0,otaCommands=0)
 log('scratch-probe-complete');return rows,files
cases=[]
def run(name,release,change=None,success=True):
 rows,files=fixture(release)
 if change:change(rows,files)
 out=HERE/'synthetic'/name;out.mkdir(parents=True,exist_ok=False)
 (out/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
 for key,value in files.items():(out/key).write_text(json.dumps(value))
 r=subprocess.run([sys.executable,str(HERE/'verify-scratch.py'),str(out),release,str(out/'verification.json')],capture_output=True)
 (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
 assert (r.returncode==0)==success,(name,r.stderr.decode())
 cases.append(dict(name=name,expected_pass=success,returncode=r.returncode))
for release in ('dashboard-ram-002','reset-undo-trim-001'):run(release,release)
release='reset-undo-trim-001'
run('summary-lie',release,lambda rows,f:f['result.json']['samples'][0].update(freeBytes=1),False)
run('saved-capability-lie',release,lambda rows,f:f['put-0.json'].update(freeBytesHex='00000000'),False)
run('completion-failure',release,lambda rows,f:next(r for r in rows if r['event']=='transmitCompletion').update(status=-1),False)
run('missing-completion',release,lambda rows,f:rows.pop(next(i for i,r in enumerate(rows) if r['event']=='transmitCompletion')),False)
run('missing-final-event',release,lambda rows,f:rows.pop(),False)
def long_gap(rows,files):
 at=next(i for i,r in enumerate(rows) if r['event']=='heap-sample')
 for r in rows[at+1:]:r['uptime']+=2
run('expired-lease',release,long_gap,False)
run('duplicate-reply',release,lambda rows,f:rows.insert(3,copy.deepcopy(rows[2])),False)
run('wrong-header-file',release,lambda rows,f:f['header-reply.json'].update(hex='00'*256),False)
p=HERE/'scratch-verifier-selftest.json';assert not p.exists();p.write_text(json.dumps(dict(passed=True,cases=cases,verifier_sha256=hashlib.sha256((HERE/'verify-scratch.py').read_bytes()).hexdigest(),device_actions=False),indent=2)+'\n')
print(json.dumps(dict(passed=True,cases=len(cases))))
