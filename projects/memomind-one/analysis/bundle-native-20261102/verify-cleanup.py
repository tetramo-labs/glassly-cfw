if not __debug__:
    raise RuntimeError('Verification requires Python assertions; optimized execution is refused')
from pathlib import Path
from collections import deque
import sys,json,hashlib
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_transport import GmStream,parse_tlvs
from memomind_scene import decode_json
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
writes=deque();pending={};pairs=[]
for r in rows:
 if r['event']=='transmitSubmission':
  b=bytes.fromhex(r['hex']);writes.append(b)
  for m in tx.feed(b):
   k=(m['event'],m['service'],m['command']);assert k not in pending;m['_submitted_uptime']=r.get('uptime');pending[k]=m
 elif r['event']=='transmitCompletion':assert r['status']==0 and writes.popleft()==bytes.fromhex(r['hex'])
 elif r['event']=='receive':
  for m in rx.feed(bytes.fromhex(r['hex'])):
   if not m['tlvs']:continue
   k=(m['event'],m['service'],m['command'])
   if k in pending:pairs.append((pending.pop(k),m))
   elif m['service']==15 and m['command'] in (0x7b,0x7e,0x7d):raise AssertionError('Unexpected or duplicated reserved-service reply')
assert not pending and not writes and not tx.buffer and not tx.body and not rx.buffer and not rx.body
graphics=[(a,b) for a,b in pairs if (a['service'],a['command'])==(15,0x7d)]
assert len(graphics)==1 and graphics[0][0]['tlvs']==[(1,bytes([11]))]
raw=graphics[0][1]['tlvs'][0][1].removesuffix(b'\0')
assert raw==b'{"glassly":"graphics","abi":1,"result":"cleared"}'
header=[(a,b) for a,b in pairs if (a['service'],a['command'])==(15,0x7b)];assert len(header)==1
assert header[0][0]['tlvs']==[(1,bytes([1,0,0,0xb0,0x1e,0,0,1]))]
expected=(Path('captures/firmware/bundle-commands-001')/'expected-app-header.bin').read_bytes()
assert hashlib.sha256(expected).hexdigest()=='5a930be718c3937d6c2221fd8953a53edd7bf916a1a0dd588258fcf4161a1d3f'
assert decode_json(header[0][1])=={'glassly':'flash-read','abi':1,'result':'ok','device':0,'offset':0x1eb000,'length':256,'hex':expected.hex()}
assert rows[-1]['event']=='cleanup-complete'
report={'format':'memomind-native-bundle-cleanup-verification-v1','capture':str(folder),'complete':True,'exact_header_verified':True,'clear_acknowledged':True,'raw_application_frames_independently_parsed_and_correlated':True,'native_submissions_completed':True,'hardware_pixel_readback':False,'trace_sha256':hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest()}
assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
