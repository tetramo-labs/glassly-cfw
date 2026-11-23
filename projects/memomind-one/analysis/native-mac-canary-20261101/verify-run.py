from pathlib import Path
from collections import deque
import json,sys,hashlib
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_transport import GmStream,gm_frames
from memomind_flash_canary import CanaryClient
from memomind_flash_read import decode_reply as decode_read
folder=Path('captures/swift-mac-canary-run-20261101-01')
rows=list(map(json.loads,(folder/'trace.jsonl').read_text().splitlines()))
tx=GmStream(legacy_repeat_fa=True,fragment_acks=True);rx=GmStream(legacy_repeat_fa=True,fragment_acks=True)
writes=deque();pending=None;pairs=[]
for r in rows:
 if r['event']=='transmitSubmission':
  data=bytes.fromhex(r['hex']);writes.append(data)
  for m in tx.feed(data):
   if m['service']==15 and m['command'] in (0x7a,0x7b):
    assert pending is None;pending=m
 elif r['event']=='transmitCompletion':assert r['status']==0 and writes.popleft()==bytes.fromhex(r['hex'])
 elif r['event']=='receive':
  for m in rx.feed(bytes.fromhex(r['hex'])):
   if m['service']==15 and m['command'] in (0x7a,0x7b) and m['tlvs']:
    assert pending and (pending['event'],pending['service'],pending['command'])==(m['event'],m['service'],m['command'])
    pairs.append((pending,m));pending=None
assert not pending and not writes and not tx.buffer and not rx.buffer and not rx.body
assert pairs[0][0]['command']==0x7b and pairs[0][0]['tlvs'][0][1]==bytes.fromhex('010000b01e000001')
header=decode_read(pairs[0][1])
assert header['device']==0 and header['offset']==0x1eb000 and header['length']==256
assert bytes.fromhex(header['hex'])==Path('captures/firmware/flash-canary-001/expected-app-header.bin').read_bytes()
# Header read precedes the independent canary client sequence.
pairs=pairs[1:]
class Replay:
 def __init__(self):self.pending=deque(pairs);self.reply=None;self.writes=0
 def write(self,data):
  assert self.reply is None
  req,res=self.pending.popleft()
  assert gm_frames(req['event'],req['service'],req['command'],req['body'],fragment_payload=642)==[data]
  self.reply=b''.join(gm_frames(res['event'],res['service'],res['command'],res['body'],fragment_payload=503));self.writes+=1
 def read(self,timeout=None):
  assert self.reply is not None;r=self.reply;self.reply=None;return r
transport=Replay();client=CanaryClient(transport);client.verify_profile();initial=client.status();assert initial['state']=='idle'
status=client.run_fixed_canary()
while transport.pending:status=client.status()
assert transport.reply is None and status['state']=='passed' and status['operation']==2 and status['restored'] and status['neighborVerified']
assert sum(req['command']==0x7a and req['tlvs'][0][1]==bytes.fromhex('02314e4143') for req,res in pairs)==1
assert not any(req['command']==0x7a and req['tlvs'][0][1][0]==1 for req,res in pairs)
assert status==json.loads((folder/'terminal-status.json').read_text())
report={'format':'memomind-native-mac-fixed-canary-verification-v1','capture':str(folder),'complete':True,'raw_application_frames_independently_parsed_and_correlated':True,'native_submissions_completed':True,'independent_python_client_replay_passed':True,'client_exchanges':transport.writes,'mutating_start_requests':1,'automatic_retries':0,'terminal_status':status,'trace_sha256':hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest(),'limitations':['Device status and application trace; not independent flash bus instrumentation.','Separate post-canary readback required to establish saved sector contents.']}
output=Path('analysis/native-mac-canary-20261101/run-verification.json');assert not output.exists();output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
