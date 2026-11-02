if not __debug__:
    raise RuntimeError('Verification requires Python assertions; optimized execution is refused')
from pathlib import Path
from collections import deque
import sys,json,hashlib
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_transport import GmStream,parse_tlvs
from memomind_scene import decode_json,parse_reply
folder=Path(sys.argv[1]);out=Path(sys.argv[2])
class Ingress:
 # Native ingress fragments carry642 body bytes; replies carry503.
 def __init__(self):self.buffer=bytearray();self.body=bytearray();self.key=None;self.fragment=0
 def feed(self,data):
  self.buffer.extend(data);result=[]
  while len(self.buffer)>=7:
   head=self.buffer[0];logical=int.from_bytes(self.buffer[1:4],'big');key=(logical,*self.buffer[4:7])
   assert 9<=logical<=80*1024
   first=head==0xfa and self.key!=key
   if not first:assert self.key==key and head==self.fragment
   count=min(651,logical-(0 if first else len(self.body)))
   if len(self.buffer)<count:break
   packet=bytes(self.buffer[:count]);assert sum(packet[:-2])&65535==int.from_bytes(packet[-2:],'big');del self.buffer[:count]
   if first:self.key=key;self.body.clear();self.fragment=0
   self.body.extend(packet[7:-2]);self.fragment+=1
   if len(self.body)==logical-9:
    result.append({'event':key[1],'service':key[2],'command':key[3],'body':bytes(self.body),'tlvs':parse_tlvs(self.body)});self.body.clear();self.key=None;self.fragment=0
  return result
rows=list(map(json.loads,(folder/'trace.jsonl').read_text().splitlines()));tx=Ingress();rx=GmStream(legacy_repeat_fa=True,fragment_acks=True)
writes=deque();pending={};pairs=[];notifications=[];notification_sources=[];completed={};status_notices=[];startup_notices=[];custom_started=False
for r in rows:
 if r['event']=='transmitSubmission':
  assert not pending,'Transmission while prior business request outstanding'
  b=bytes.fromhex(r['hex']);writes.append(b)
  for m in tx.feed(b):
   if m['service']==15:custom_started=True
   k=(m['event'],m['service'],m['command']);assert k not in pending;m['_submitted_uptime']=r['uptime'];pending[k]=m
 elif r['event']=='transmitCompletion':assert r['status']==0 and writes.popleft()==bytes.fromhex(r['hex'])
 elif r['event']=='receive':
  for m in rx.feed(bytes.fromhex(r['hex'])):
   if not m['tlvs']:continue
   if (m['service'],m['command'])==(15,0x7d):
    assert len(m['tlvs'])==1 and m['tlvs'][0][0]==5 and len(m['tlvs'][0][1])<=1024
    value=decode_json(m)
    assert type(value.get('abi')) is int and value['abi']==1
    if value.get('result')=='settled':
     k=(m['event'],m['service'],m['command']);assert k in completed and k not in pending,'Settled before primary response'
     notification_sources.append(completed[k]['tlvs'][0][1])
     tag=value.get('tag');assert type(tag) is int and 0<=tag<=65535
     assert value=={'glassly':'scene','abi':1,'result':'settled','tag':tag}
     assert m['tlvs'][0][1].removesuffix(b'\0')==json.dumps(value,separators=(',',':')).encode()
     notifications.append((m['event'],tag));continue
   k=(m['event'],m['service'],m['command'])
   if not custom_started and m['service']!=15 and k not in pending:
    assert (m['service'],m['command']) not in ((1,1),(1,2)),'Unexpected probe reply'
    startup_notices.append({'event':m['event'],'service':m['service'],'command':m['command'],'bodyHex':bytes(m['body']).hex()});continue
   k=(m['event'],m['service'],m['command'])
   if custom_started and m['service']!=15 and k not in pending:
    status_notices.append((m['event'],m['service'],m['command'],bytes(m['body']).hex()));continue
   k=(m['event'],m['service'],m['command']);assert k in pending,'Unexpected or duplicate business reply'
   request=pending.pop(k);pairs.append((request,m));completed[k]=request
assert status_notices==[(r['eventID'],r['service'],r['command'],r['bodyHex']) for r in rows if r['event']=='native-service-notification']
assert not pending and not writes and not tx.buffer and not tx.body and not rx.buffer and not rx.body
# Independently verify probe/header/capabilities before accepting graphics replies.
assert len(pairs)>=4
assert [(a['service'],a['command']) for a,b in pairs[:4]]==[(1,1),(1,2),(15,0x7b),(15,0x7e)]
assert pairs[0][0]['tlvs']==pairs[1][0]['tlvs']==pairs[3][0]['tlvs']==[]
assert pairs[0][1]['tlvs']==[(6,b'\0')]
assert len(pairs[1][1]['tlvs'])==1 and pairs[1][1]['tlvs'][0][0]==2
identity=json.loads(pairs[1][1]['tlvs'][0][1]);assert identity['model']=='H001Y' and identity['mac']=='4C:3C:8F:90:CC:C3' and identity['hver']=='2.1.2'
assert pairs[2][0]['tlvs']==[(1,bytes([1,0,0,0xb0,0x1e,0,0,1]))]
def bounded_json(message):
 assert len(message['tlvs'])==1 and message['tlvs'][0][0]==5 and len(message['tlvs'][0][1])<=1024
 value=decode_json(message);assert type(value.get('abi')) is int and value['abi']==1
 return value
pins=json.loads(Path('analysis/text-native-20261102/candidate-pins.json').read_text())
header=Path('captures/firmware/text-commands-001/expected-app-header.bin').read_bytes()
assert len(header)==256 and hashlib.sha256(header).hexdigest()==pins['app_header_sha256']
assert bounded_json(pairs[2][1])=={'glassly':'flash-read','abi':1,'result':'ok','device':0,'offset':0x1eb000,'length':256,'hex':header.hex()}
caps=bounded_json(pairs[3][1])
expected_caps={'glassly':'graphics-runtime','profile':'H001Y-1.0.3.127','width':600,'height':350,'modes':[3,6,8,9,11,15,19,20,36,37,38,39,40,41],'rasterLens':'first-left','maxMessageBytes':8192,'bundleModes':[3,6,9,15,19,20,36,37,38,39,40,41],'bundleMaxSegments':255,'textMaxBytes':255,'textFont':'native-resource','missingGlyph':'reject'}
for key,value in expected_caps.items():assert type(caps[key]) is type(value) and caps[key]==value
graphics=[(a,b) for a,b in pairs if (a['service'],a['command'])==(15,0x7d)]
assert len(pairs)==len(graphics)+4
assert not notifications and not any(r['event']=='settled-notification' for r in rows)
commands=[]
for a,b in graphics:
 assert len(a['tlvs'])==1 and a['tlvs'][0][0]==1
 assert len(b['tlvs'])==1 and b['tlvs'][0][0]==5 and len(b['tlvs'][0][1])<=1024
 value=decode_json(b)
 assert type(value.get('abi')) is int and value['abi']==1
 assert b['tlvs'][0][1].removesuffix(b'\0')==json.dumps(value,separators=(',',':')).encode()
 commands.append((a['tlvs'][0][1],value))
assert len(commands)>=12
import struct
def text(payload,x,y,options=31,mode=15):return bytes([mode])+struct.pack('<hhBB',x,y,options,len(payload))+payload
def bundle(children):return bytes([8,len(children)])+b''.join(struct.pack('<H',len(c))+c for c in children)
maximum=text(bytes([11])*248+b'TEXT 15',70,100)
highbit=text(b'SWIFT',70,145,mode=143)
bundled=bundle([text(b'TEXT 15',320,100),text(b'SWIFT',320,145)])
empty=text(b'',-32768,32767,255)
invalid=[bytes([15,0,0,0,0,31,1,0]),bytes([15,0,0,0,0,31,2,0xc0,0xaf]),bytes([15,0,0,0,0,31,3,0xed,0xa0,0x80]),bytes([15,0,0,0,0,31,1]),bytes([15,0,0,0,0,31,0,65]),bytes([15,0,0,0,0,31])]
for i,(name,want) in enumerate([('maximum-text-command.bin',maximum),('highbit-text-command.bin',highbit),('text-bundle.bin',bundled),('empty-text-command.bin',empty)],1):
 assert commands[i][0]==want==(folder/name).read_bytes()
for i,want in enumerate(invalid):assert commands[5+i][0]==want==(folder/f'invalid-text-{i}.bin').read_bytes()
key=commands[0][0];assert key==(folder/'black-frame-command.bin').read_bytes() and key[0]==6
pos=1;pixels=0
while pos<len(key):
 op=key[pos];pos+=1;count=op>>4;assert op&15==0
 if not count:
  assert pos<len(key);count=key[pos];pos+=1
  if not count:
   assert pos+2<=len(key);count=int.from_bytes(key[pos:pos+2],'little');pos+=2
 assert count>0;pixels+=count;assert pixels<=210000
assert pixels==210000 and pos==len(key)
assert commands[-1][0]==bytes([11])
for i,(command,reply) in enumerate(commands):
 result='invalid' if 5<=i<=10 else 'cleared' if i==len(commands)-1 else 'ok'
 expected={'glassly':'graphics','abi':1,'result':result}
 if result=='ok':expected['presentation']='scheduled'
 assert reply==expected
 if 11<=i<len(commands)-1:assert command==bytes([36,0])
assert rows[-1]['event']=='smoke-complete'
assert rows[-1]['cleared'] and rows[-1]['invalidCommandsRejected']==6
visible=[r for r in rows if r['event']=='pattern-visible'];ends=[r for r in rows if r['event']=='hold-ended'];assert len(visible)==len(ends)==1
start=visible[0]['uptime'];clear=graphics[-1][0]['_submitted_uptime'];assert clear>=start
if ends[0]['finishRequested']:
 finish=json.loads((folder/'finish-requested.json').read_text());assert finish['reason']=='user confirmed visible pattern'
else:assert clear-start>=300
hold_times=[start]+[a['_submitted_uptime'] for a,b in graphics[11:]]
assert all(b>=a for a,b in zip(hold_times,hold_times[1:]))
report={'format':'memomind-native-text-smoke-verification-v1','capture':str(folder),'complete':True,'probe_header_capabilities_verified':True,'startup_notifications_captured':startup_notices,'native_service_notifications_logged':len(status_notices),'all_native_write_submissions_completed':True,'application_frames_independently_parsed_and_correlated':True,'maximum_255_byte_text_acknowledged':True,'highbit_text_acknowledged':True,'bundled_text_acknowledged':True,'empty_extreme_coordinates_acknowledged':True,'invalid_commands_rejected':6,'lease_renewals_acknowledged':len(commands)-12,'cleared':True,'black_frame_decoded_independently':True,'hardware_pixel_readback':False,'font_pixel_equivalence_to_g2':False,'hold_seconds_before_clear':clear-start,'finish_requested':ends[0]['finishRequested'],'maximum_hold_submission_gap_seconds':max(b-a for a,b in zip(hold_times,hold_times[1:])),'continuous_pixel_retention_proven':False,'visual_confirmation':'separate user observation required','trace_sha256':hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest()}
assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
