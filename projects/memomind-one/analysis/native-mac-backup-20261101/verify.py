from pathlib import Path
from collections import deque
import hashlib,json,sys,struct
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_transport import GmStream
from memomind_flash_read import FlashReadClient,FULL_STORE_PROFILE,decode_reply
from memomind_storage_diag import validate_topology,validate_badmap,tail_unavailable_map
folder=Path(sys.argv[1]);out=Path(sys.argv[2])
def sha(b):return hashlib.sha256(b).hexdigest()
rows=[json.loads(l) for l in (folder/'trace.jsonl').read_text().splitlines()]
tx=GmStream(legacy_repeat_fa=True,fragment_acks=True);rx=GmStream(legacy_repeat_fa=True,fragment_acks=True)
pending=None;responses=[];submitted=deque();seen_pages=[];saved_pages=[]
for r in rows:
 kind=r['event']
 if kind=='transmitSubmission':
  raw=bytes.fromhex(r['hex']);submitted.append(raw)
  for m in tx.feed(raw):
   if (m['service'],m['command'])==(15,0x7b):
    assert pending is None,'Overlapping requests'
    assert len(m['tlvs'])==1 and m['tlvs'][0][0]==1
    pending=(m['event'],m['tlvs'][0][1])
 elif kind=='transmitCompletion':assert r['status']==0 and submitted.popleft()==bytes.fromhex(r['hex'])
 elif kind=='receive':
  for m in rx.feed(bytes.fromhex(r['hex'])):
   if (m['service'],m['command'])==(15,0x7b) and m['tlvs']:
    assert pending and m['event']==pending[0],'Uncorrelated/duplicate reply'
    result=decode_reply(m);responses.append((pending[1],result));pending=None
 elif kind=='page-reply':seen_pages.append((r['page'],decode_reply({'tlvs':[(5,r['json'].encode())]})))
 elif kind=='page-saved':saved_pages.append(r)
assert not pending and not submitted and not tx.buffer and not rx.buffer and not rx.body
assert len(responses)==12293,(len(responses),'Expected profile/header/topology/badmap/12288 pages/topology')
class Client(FlashReadClient):
 def __init__(self):super().__init__(None,profile=FULL_STORE_PROFILE);self.queue=deque(responses)
 def _request(self,body,check):
  request,r=self.queue.popleft();assert request==body;check(r);return r
c=Client();c.query();header=c.read(0,0x1eb000)
assert sha(header)=='117219ae77258054a768244fac70014ad96c77f88ed3ee116dce45ec32aa6167'
assert header==(folder/'app-header.bin').read_bytes()
before=c._request(b'\x02',validate_topology);bad=c._request(b'\x03',validate_badmap)
backup=(folder/'managed-store.bin').read_bytes();assert len(backup)==3145728
assert len(seen_pages)==len(saved_pages)==12288
for i in range(12288):
 offset=0x500000+i*256
 raw=c.read(1,offset)
 assert backup[i*256:(i+1)*256]==raw
 page,result=seen_pages[i];assert page==i and bytes.fromhex(result['hex'])==raw
 assert (result['device'],result['offset'],result['length'])==(1,offset,256)
 saved=saved_pages[i];assert (saved['page'],saved['offset'],saved['bytes'],saved['sha256'])==(i,offset,256,sha(raw))
after=c._request(b'\x02',validate_topology);assert not c.queue
assert before==after and before['consistent']==1 and before['cus8ContextPresent']==0
old=json.loads(Path('captures/exclusive-store-runtime-20261101/preflight-after-02/manifest.json').read_text())
assert before==old['topology_before'] and bad==old['badmap']
assert tail_unavailable_map(bad)[-1]&0xc0==0
result=json.loads((folder/'result.json').read_text());assert result['complete'] and result['backupSHA256']==sha(backup)
report={'format':'memomind-native-mac-full-backup-verification-v1','complete':True,'capture':str(folder),'bytes':len(backup),'chunks':12288,'sha256':sha(backup),'all_ff':backup==b'\xff'*len(backup),'matches_pre_reset_backup':sha(backup)=='908b6cfc9aef496dd5ab5c5540d80c6383ed6e92f86044574c996315381bc064','raw_application_frames_independently_parsed_and_correlated':True,'native_submissions_completed':True,'profile_and_read_replies_strictly_validated':True,'app_header_full256_matches':True,'topology_before_after_equal':True,'topology_and_badmap_match_pre_reset':True,'badmap_source':'native-defined-absent-default','flash_mutations':0,'automatic_retries':0,'trace_sha256':sha((folder/'trace.jsonl').read_bytes())}
assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
