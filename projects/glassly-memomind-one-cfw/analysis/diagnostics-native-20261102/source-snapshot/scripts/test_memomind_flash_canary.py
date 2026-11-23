import copy,json,struct,unittest
from collections import deque
from memomind_flash_canary import CanaryClient,CanaryError,CanaryNativeError,CanaryProtocolError,decode_reply,TOKEN
from memomind_flash_read import CANARY_PROFILE,PROFILES,FlashReadProtocolError
from memomind_transport import gm_frames,parse_tlvs

def idle():return dict(glassly='flash-canary',abi=1,result='ok',state='idle',operation=0,phase=0,error=0,nativeStatus=0,mapSource=0,mutationStarted=False,restored=False,neighborVerified=False,device=1,offset=0x7ff000,neighbor=0x7fe000,sectorBytes=4096)
def started(op=2):return {**idle(),'state':'starting','operation':op,'phase':1}
def passed(op=2):return {**started(op),'state':'passed','phase':8,'mapSource':1,'mutationStarted':op==2,'restored':op==2,'neighborVerified':True}
class Wire:
 timeout=10
 def __init__(self):self.messages=[];self.replies=deque();self.incoming=deque();self.edit=lambda r:r;self.drop=False;self.delta=0;self.duplicate=False
 def write(self,frame):
  if len(frame)==9:return
  event,service,cmd=frame[4:7];assert service==15
  tlvs=parse_tlvs(frame[7:-2]);assert len(tlvs)==1 and tlvs[0][0]==1;body=tlvs[0][1];self.messages.append((cmd,body))
  if cmd==0x7b:
   assert body==b'\0';r=dict(glassly='flash-read',abi=1,result='ok',profile=CANARY_PROFILE,maxRead=256,alignment=256,ranges=[dict(device=d,start=s,end=e) for d,s,e in PROFILES[CANARY_PROFILE].values()])
  else:assert cmd==0x7a;r=self.replies.popleft()
  r=self.edit(r)
  raw=json.dumps(r,separators=(',',':')).encode();payload=b'\6\0\0\1'+bytes([r['status']]) if set(r)=={'status'} else b'\5'+len(raw).to_bytes(3,'big')+raw
  wire=b''.join(gm_frames((event+self.delta)&255,15,cmd,payload))
  if not self.drop:
   if self.duplicate:wire+=wire
   self.incoming.extend([wire] if self.duplicate else (wire[i:i+13] for i in range(0,len(wire),13)))
 def read(self,timeout):
  if not self.incoming:raise TimeoutError('No reply')
  return self.incoming.popleft()
def decoded(r):return decode_reply({'tlvs':[(5,json.dumps(r).encode())]})
class CanaryClientTests(unittest.TestCase):
 def client(self):
  w=Wire();c=CanaryClient(w);c.verify_profile();w.replies.append(idle());c.status();return w,c
 def test_explicit_profile_idle_and_one_start(self):
  w=Wire();c=CanaryClient(w)
  with self.assertRaises(CanaryError):c.status()
  with self.assertRaises(CanaryError):c.run_fixed_canary()
  self.assertFalse(w.messages);c.verify_profile()
  with self.assertRaises(CanaryError):c.run_fixed_canary()
  w.replies.append(idle());c.status();w.replies.append(started());c.run_fixed_canary()
  self.assertEqual(w.messages[-1],(0x7a,struct.pack('<BI',2,TOKEN)))
  before=list(w.messages)
  with self.assertRaises(CanaryError):c.run_fixed_canary()
  self.assertEqual(w.messages,before)
  w.replies.append(passed());self.assertEqual(c.status(),passed())
 def test_validation_operation_and_immediate_completion(self):
  w,c=self.client();w.replies.append(passed(1));self.assertEqual(c.validate_worker(),passed(1));self.assertEqual(w.messages[-1],(0x7a,struct.pack('<BI',1,TOKEN)))
 def test_reboot_mismatch_regression_and_terminal_changes_stop(self):
  for changed in (idle(),started(1),{**started(),'phase':0}):
   w,c=self.client();w.replies.append(started());c.run_fixed_canary();w.replies.append(changed)
   with self.assertRaises(CanaryProtocolError):c.status()
   self.assertTrue(c.failed)
  w,c=self.client();w.replies.append(passed());c.run_fixed_canary();w.replies.append({**passed(),'mapSource':2})
  with self.assertRaises(CanaryProtocolError):c.status()
 def test_lost_or_duplicate_start_is_never_repeated(self):
  for mode,error in (('drop',TimeoutError),('duplicate',CanaryProtocolError),('delta',CanaryProtocolError)):
   w,c=self.client();w.replies.append(started());setattr(w,mode,True)
   with self.assertRaises(error):c.run_fixed_canary()
   n=len(w.messages)
   with self.assertRaises(CanaryError):c.run_fixed_canary()
   with self.assertRaises(CanaryError):c.status()
   self.assertEqual(len(w.messages),n);self.assertTrue(c.attempted and c.failed)
 def test_wrong_profile_never_sends_canary(self):
  w=Wire();w.edit=lambda r:{**r,'profile':'H001Y-1.0.3.127-full-store-read-v1'};c=CanaryClient(w)
  with self.assertRaises(FlashReadProtocolError):c.verify_profile()
  self.assertTrue(c.failed);self.assertEqual(w.messages,[(0x7b,b'\0')])
 def test_success_schema_and_semantic_rejection(self):
  for good in (idle(),started(),passed(),passed(1),{**started(),'state':'failed','error':-20001}):self.assertEqual(decoded(good),good)
  for patch in ({'operation':True},{'phase':9},{'offset':0x7fe000},{'device':True},{'error':-2**31-1},{'nativeStatus':2**31},{'restored':1},{'state':'other'},{'extra':0},{'mapSource':0},{'neighborVerified':False},{'mutationStarted':False}):
   with self.subTest(patch=patch),self.assertRaises(CanaryProtocolError):decoded({**passed(),**patch})
  for key in passed():
   bad=passed();del bad[key]
   with self.assertRaises(CanaryProtocolError):decoded(bad)
 def test_strict_json_tlv_and_native_errors(self):
  for result in ('invalid','wrong-image','registry-invalid','already-used','allocation-failed'):
   with self.assertRaises(CanaryNativeError):decoded(dict(glassly='flash-canary',abi=1,result=result))
  for raw in (b'[]',b'null',b'\xff',b'{"abi":1,"abi":1}',b'{"x":NaN}',b' '*769,json.dumps(idle()).encode()+b'\0\0'):
   with self.assertRaises(CanaryProtocolError):decode_reply({'tlvs':[(5,raw)]})
  for tlvs in ([],[(6,b'\4')],[(5,b'{}'),(5,b'{}')]):
   with self.assertRaises(CanaryProtocolError):decode_reply({'tlvs':tlvs})
 def test_terminal_failure_is_observable_not_success(self):
  w,c=self.client();failure={**started(),'state':'failed','phase':5,'error':-19718,'mapSource':2,'mutationStarted':True}
  w.replies.append(failure);self.assertEqual(c.run_fixed_canary(),failure);w.replies.append(failure);self.assertEqual(c.status(),failure)
  self.assertFalse(c.failed)
if __name__=='__main__':unittest.main()
