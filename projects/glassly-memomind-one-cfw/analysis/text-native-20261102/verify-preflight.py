if not __debug__:
    raise RuntimeError('Verification requires Python assertions; optimized execution is refused')
from pathlib import Path
import hashlib,json,sys,struct
from collections import deque
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_flash_read import FlashReadClient,CANARY_PROFILE,decode_reply
from memomind_storage_diag import validate_topology,validate_badmap,tail_unavailable_map
from memomind_transport import GmStream
folder=Path(sys.argv[1]);output=Path(sys.argv[2])
responses=[];pending=None;writes=deque();tx=GmStream(legacy_repeat_fa=True,fragment_acks=True);rx=GmStream(legacy_repeat_fa=True,fragment_acks=True)
for r in map(json.loads,(folder/'trace.jsonl').read_text().splitlines()):
 kind=r['event']
 if kind=='transmitSubmission':
  data=bytes.fromhex(r['hex']);writes.append(data)
  for m in tx.feed(data):
   if (m['service'],m['command'])==(15,0x7b):
    assert pending is None and len(m['tlvs'])==1 and m['tlvs'][0][0]==1
    pending=(m['event'],m['tlvs'][0][1])
 elif kind=='transmitCompletion':assert r['status']==0 and writes.popleft()==bytes.fromhex(r['hex'])
 elif kind=='receive':
  for m in rx.feed(bytes.fromhex(r['hex'])):
   if (m['service'],m['command'])==(15,0x7b) and m['tlvs']:
    assert pending and pending[0]==m['event'];responses.append((pending[1],decode_reply(m)));pending=None
assert pending is None and not writes and not rx.buffer and not rx.body and len(responses)==37
class CapturedClient(FlashReadClient):
 def __init__(self):super().__init__(None,profile=CANARY_PROFILE);self.queue=deque(responses)
 def _request(self,body,check):
  request,r=self.queue.popleft();assert request==body;check(r);return r
c=CapturedClient();c.query();header=c.read(0,0x1eb000)
assert hashlib.sha256(header).hexdigest()=='b7e85bb1ca5658d743190e4589da2d7454d41ecad0ca459695a43b36264e6fc0'
assert header==(folder/'app-header.bin').read_bytes()
before=c._request(b'\x02',validate_topology);bad=c._request(b'\x03',validate_badmap)
sectors=b''.join(c.read(1,0x7fe000+i*256) for i in range(32))
after=c._request(b'\x02',validate_topology);assert not c.queue
assert sectors==(folder/'target-and-neighbor.bin').read_bytes()==b'\xff'*8192
backup=Path('captures/swift-mac-full-backup-20261101-01')
assert before==after==json.loads((backup/'topology-before.json').read_text())
assert bad==json.loads((backup/'badmap.json').read_text())
assert before['consistent']==1 and before['cus8ContextPresent']==0 and tail_unavailable_map(bad)[-1]&0xc0==0
report={'format':'memomind-native-mac-raster-preflight-v1','capture':str(folder),'complete':True,'app_header_full256_matches':True,'target_and_neighbor_all_ff':True,'topology_and_badmap_match_backup':True,'raw_application_frames_independently_parsed_and_correlated':True,'native_submissions_completed':True,'current_full_backup_verification':'analysis/native-mac-backup-20261101/verification.json','flash_mutations':0,'automatic_retries':0,'trace_sha256':hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest()}
assert not output.exists();output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
