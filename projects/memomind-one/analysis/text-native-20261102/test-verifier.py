"""Synthetic wire evidence only; does not exercise hardware or prove visibility."""
from pathlib import Path
import copy, hashlib, json, struct, subprocess, sys
if not __debug__: raise RuntimeError('Assertions required')
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from memomind_transport import gm_frames
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False)
C=OUT/'synthetic-capture';C.mkdir()
VERIFIER=ROOT/'analysis/text-native-20261102/verify-smoke.py'
def save(name,data):(C/name).write_bytes(data)
def text(payload,x,y,options=31,mode=15):return bytes([mode])+struct.pack('<hhBB',x,y,options,len(payload))+payload
def bundle(children):return bytes([8,len(children)])+b''.join(struct.pack('<H',len(c))+c for c in children)
black=b'\x06'+b'\x00\x00\xff\xff'*3+b'\x00\x00'+struct.pack('<H',210000-65535*3)
commands=[black,text(bytes([11])*248+b'TEXT 15',70,100),text(b'SWIFT',70,145,mode=143),bundle([text(b'TEXT 15',320,100),text(b'SWIFT',320,145)]),text(b'',-32768,32767,255)]
for name,data in zip(['black-frame-command.bin','maximum-text-command.bin','highbit-text-command.bin','text-bundle.bin','empty-text-command.bin'],commands):save(name,data)
invalid=[bytes.fromhex(h) for h in ['0f000000001f0100','0f000000001f02c0af','0f000000001f03eda080','0f000000001f01','0f000000001f0041','0f000000001f']]
for i,data in enumerate(invalid):save(f'invalid-text-{i}.bin',data)
commands+=invalid+[bytes([36,0]),bytes([11])]
rows=[];clock=0
def append(row):
 global clock
 row['uptime']=clock;clock+=.01;rows.append(row)
def wire(event,service,command,body):return b''.join(gm_frames(event,service,command,body))
def reply(i):
 result='invalid' if 5<=i<=10 else 'cleared' if i==len(commands)-1 else 'ok'
 obj=dict(glassly='graphics',abi=1,result=result)
 if result=='ok':obj['presentation']='scheduled'
 return obj
def response(i,obj):
 raw=json.dumps(obj,separators=(',',':')).encode()
 return dict(event='receive',hex=wire(49+i,15,125,b'\x05'+len(raw).to_bytes(3,'big')+raw).hex(),label=f'rx-{i}')
append(dict(event='receive',hex=wire(34,1,33,bytes.fromhex('08000001010400000400004eb6')).hex()))
header=(ROOT/'captures/firmware/text-commands-001/expected-app-header.bin').read_bytes()
probe_header={'glassly':'flash-read','abi':1,'result':'ok','device':0,'offset':0x1eb000,'length':256,'hex':header.hex()}
probe_caps={'glassly':'graphics-runtime','abi':1,'profile':'H001Y-1.0.3.127','width':600,'height':350,'modes':[3,6,8,9,11,15,19,20,36,37,38,39,40,41],'rasterLens':'first-left','maxMessageBytes':8192,'bundleModes':[3,6,9,15,19,20,36,37,38,39,40,41],'bundleMaxSegments':255,'textMaxBytes':255,'textFont':'native-resource','missingGlyph':'reject'}
probe_identity={'model':'H001Y','mac':'4C:3C:8F:90:CC:C3','hver':'2.1.2'}
def json_tlv(kind,value):
 raw=json.dumps(value,separators=(',',':')).encode();return bytes([kind])+len(raw).to_bytes(3,'big')+raw
probes=[(1,1,1,b'',bytes.fromhex('0600000100')),(2,1,2,b'',json_tlv(2,probe_identity)),(47,15,123,bytes.fromhex('01000008010000b01e000001'),json_tlv(5,probe_header)),(48,15,126,b'',json_tlv(5,probe_caps))]
for i,(event,service,command,body,response_body) in enumerate(probes):
 raw=wire(event,service,command,body).hex()
 append(dict(event='transmitSubmission',hex=raw,label=f'probe-tx-{i}'));append(dict(event='transmitCompletion',hex=raw,status=0))
 append(dict(event='receive',hex=wire(event,service,command,response_body).hex(),label=f'probe-rx-{i}'))
for i,data in enumerate(commands):
 if i==11:append(dict(event='pattern-visible'))
 if i==12:
  clock+=301;append(dict(event='hold-ended',finishRequested=False))
 raw=wire(49+i,15,125,b'\x01'+len(data).to_bytes(3,'big')+data)
 for n in range(0,len(raw),73):
  piece=raw[n:n+73].hex()
  append(dict(event='transmitSubmission',hex=piece,label=f'tx-{i}'))
  append(dict(event='transmitCompletion',hex=piece,status=0))
 append(response(i,reply(i)))
 if i==11:
  body=bytes.fromhex('0800000100')
  append(dict(event='receive',hex=wire(91,1,58,body).hex(),label='native-rx'))
  append(dict(event='native-service-notification',eventID=91,service=1,command=58,bodyHex=body.hex(),label='native-log'))
append(dict(event='smoke-complete',cleared=True,invalidCommandsRejected=6))
results=[]
def run(name,trace,success,optimized=False):
 (C/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in trace))
 process=subprocess.run([sys.executable]+(['-O'] if optimized else [])+[str(VERIFIER),str(C),str(OUT/(name+'.json'))],cwd=ROOT,capture_output=True)
 (OUT/(name+'.stdout')).write_bytes(process.stdout);(OUT/(name+'.stderr')).write_bytes(process.stderr)
 results.append(dict(name=name,expected_success=success,exit_code=process.returncode,passed=(process.returncode==0)==success))
def change_reply(i,obj):
 trace=copy.deepcopy(rows);at=next(n for n,r in enumerate(trace) if r.get('label')==f'rx-{i}')
 trace[at]={**response(i,obj),'uptime':trace[at]['uptime']};return trace
run('valid-native-capture',rows,True)
def probe_change(i,value):
 trace=copy.deepcopy(rows);row=next(r for r in trace if r.get('label')==f'probe-rx-{i}')
 event,service,command,_,_=probes[i];row['hex']=wire(event,service,command,json_tlv(2 if i==1 else 5,value)).hex();return trace
bad=dict(probe_header);bad['hex']='00'*256;run('wrong-header',probe_change(2,bad),False)
bad=dict(probe_caps);bad['missingGlyph']='fallback';run('wrong-font-policy',probe_change(3,bad),False)
bad=dict(probe_caps);bad['textMaxBytes']=True;run('boolean-capacity',probe_change(3,bad),False)
bad=dict(probe_identity);bad['mac']='00:00:00:00:00:00';run('wrong-device',probe_change(1,bad),False)

run('optimized-refused',rows,False,True)
bad=reply(1);bad['abi']=True;run('boolean-abi-rejected',change_reply(1,bad),False)
run('malformed-accepted-rejected',change_reply(5,reply(1)),False)
run('missing-native-log',[r for r in rows if r.get('label')!='native-log'],False)
trace=copy.deepcopy(rows);next(r for r in trace if r.get('label')=='native-log')['bodyHex']='00';run('wrong-native-body',trace,False)
trace=copy.deepcopy(rows);at=next(i for i,r in enumerate(trace) if r.get('label')=='rx-1');trace.insert(at+1,copy.deepcopy(trace[at]));run('duplicate-main',trace,False)
trace=copy.deepcopy(rows);trace.pop(next(i for i,r in enumerate(trace) if r['event']=='transmitCompletion'));run('missing-completion',trace,False)
trace=copy.deepcopy(rows);item=next(r for r in trace if r.get('label')=='rx-1');raw=bytearray.fromhex(item['hex']);raw[-1]^=1;item['hex']=raw.hex();run('checksum-rejected',trace,False)
run('missing-clear-reply',[r for r in rows if r.get('label')!='rx-12'],False)
for name,file in [('wrong-maximum','maximum-text-command.bin'),('wrong-bundle','text-bundle.bin'),('wrong-black','black-frame-command.bin')]:
 original=(C/file).read_bytes();modified=bytearray(original);modified[-1]^=1;save(file,modified);run(name,rows,False);save(file,original)
trace=copy.deepcopy(rows)
for row in trace:
 if row['event']=='hold-ended' or row.get('label') in ('tx-12','rx-12') or row['event']=='smoke-complete':row['uptime']-=301
run('short-timeout-hold',trace,False)
next(r for r in trace if r['event']=='hold-ended')['finishRequested']=True
(C/'finish-requested.json').write_text(json.dumps({'reason':'user confirmed visible pattern'}));run('confirmed-early-finish',trace,True)
(C/'finish-requested.json').write_text(json.dumps({'reason':'unknown'}));run('unconfirmed-early-finish',trace,False)
(C/'finish-requested.json').unlink()
(C/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
report={'hardware_tested':False,'fixture_origin':'Synthetic independent text bytes and wire events; no renderer or device execution','verifier_sha256':hashlib.sha256(VERIFIER.read_bytes()).hexdigest(),'cases':results,'count':len(results),'passed':all(r['passed'] for r in results)}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if not report['passed']:sys.exit(1)
