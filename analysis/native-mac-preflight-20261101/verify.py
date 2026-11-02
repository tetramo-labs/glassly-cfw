from pathlib import Path
import hashlib,json,sys,struct
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_flash_read import FlashReadClient, FULL_STORE_PROFILE, decode_reply
from memomind_storage_diag import validate_topology,validate_badmap,tail_unavailable_map

def sha(b):return hashlib.sha256(b).hexdigest()
class CapturedClient(FlashReadClient):
 def __init__(self,folder):
  super().__init__(None,profile=FULL_STORE_PROFILE);self.folder=folder;self.pending=[]
 def next(self,name,request):self.pending.append((name,request))
 def _request(self,body,check):
  name,expected=self.pending.pop(0);assert body==expected
  r=decode_reply({'tlvs':[(5,(self.folder/name).read_bytes())]});check(r);return r

def witness(folder):
 c=CapturedClient(folder);c.next('profile.json',b'\0');c.query()
 c.next('header-reply.json',struct.pack('<BBIH',1,0,0x1eb000,256));header=c.read(0,0x1eb000)
 assert sha(header)=='117219ae77258054a768244fac70014ad96c77f88ed3ee116dce45ec32aa6167'
 assert header==(folder/'app-header.bin').read_bytes()
 return c
boot=Path('captures/swift-mac-boot-20261101-02');witness(boot)
pre=Path('captures/swift-mac-storage-preflight-20261101-01');c=witness(pre)
def diagnostic(name,validator):
 r=decode_reply({'tlvs':[(5,(pre/name).read_bytes())]});validator(r);return r
before=diagnostic('topology-before.json',validate_topology)
bad=diagnostic('badmap.json',validate_badmap)
after=diagnostic('topology-after.json',validate_topology)
assert before==after and before['consistent']==1 and before['cus8ContextPresent']==0
prior=json.loads(Path('captures/exclusive-store-runtime-20261101/preflight-after-02/manifest.json').read_text())
assert before==prior['topology_before'] and bad==prior['badmap']
bitmap=tail_unavailable_map(bad);assert bitmap[-1]&0xc0==0
parts=[]
for i in range(32):
 offset=0x7fe000+i*256;c.next(f'sector-page-{i:02d}.json',struct.pack('<BBIH',1,1,offset,256));parts.append(c.read(1,offset))
sectors=b''.join(parts);assert sectors==(pre/'target-and-neighbor.bin').read_bytes()==b'\xff'*8192
r={'format':'memomind-native-mac-post-reset-verification-v1','complete':True,'boot_capture':str(boot),'preflight_capture':str(pre),'strict_python_profile_and_read_validation':True,'app_header_full256_matches':True,'app_header_sha256':sha((boot/'app-header.bin').read_bytes()),'topology_before_after_equal':True,'topology_matches_before_reset':True,'effective_badmap_matches_before_reset':True,'map_source':'native-defined-absent-default','target_and_neighbor_all_ff':True,'target_and_neighbor_bytes':len(sectors),'target_and_neighbor_sha256':sha(sectors),'flash_mutations':0,'current_full_3MiB_backup':False,'historical_full_backup':'analysis/exclusive-store-backup-verification.json','canary_executed':False}
Path('analysis/native-mac-preflight-20261101/verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
