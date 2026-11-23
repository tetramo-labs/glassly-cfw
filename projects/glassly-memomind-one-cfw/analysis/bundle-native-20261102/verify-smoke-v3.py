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
   if not custom_started and (m['service'],m['command']) in ((1,0x30),(14,12)):
    expected=b'\x02' if m['service']==1 else b'\0'
    assert m['tlvs']==[(8,expected)],'Unexpected startup payload'
    startup_notices.append((m['event'],m['service'],m['command']));continue
   k=(m['event'],m['service'],m['command'])
   if custom_started and m['service']!=15 and k not in pending:
    status_notices.append((m['event'],m['service'],m['command'],bytes(m['body']).hex()));continue
   k=(m['event'],m['service'],m['command']);assert k in pending,'Unexpected or duplicate business reply'
   request=pending.pop(k);pairs.append((request,m));completed[k]=request
assert status_notices==[(r['eventID'],r['service'],r['command'],r['bodyHex']) for r in rows if r['event']=='native-service-notification']
assert not pending and not writes and not tx.buffer and not tx.body and not rx.buffer and not rx.body
graphics=[(a,b) for a,b in pairs if (a['service'],a['command'])==(15,0x7d)]
commands=[]
for a,b in graphics:
 assert len(a['tlvs'])==1 and a['tlvs'][0][0]==1
 assert len(b['tlvs'])==1 and b['tlvs'][0][0]==5 and len(b['tlvs'][0][1])<=1024
 value=decode_json(b)
 assert type(value.get('abi')) is int and value['abi']==1
 assert b['tlvs'][0][1].removesuffix(b'\0')==json.dumps(value,separators=(',',':')).encode()
 commands.append((a['tlvs'][0][1],value))
assert len(commands)>=12
reset,reply=commands[0];assert reset==bytes([41,0,0,1,0,0,250])==(folder/'reset-command.bin').read_bytes()
def scene(reply,mode,request,epoch=None):
 assert set(reply)=={'glassly','abi','result','replyHex'} and reply['glassly']=='scene' and reply['abi']==1 and reply['result']=='ok'
 h=reply['replyHex'];assert isinstance(h,str) and 20<=len(h)<=500 and len(h)%2==0 and all(c in '0123456789abcdef' for c in h)
 decoded=parse_reply(bytes.fromhex(h))
 assert decoded.mode==mode and decoded.request==request and decoded.status==0 and decoded.epoch>0
 if epoch is not None:assert decoded.epoch==epoch
 assert decoded.extra==(bytes([0,64,0]) if mode==41 else bytes([0]))
 return decoded.epoch
epoch=scene(reply,41,1)
import struct
def hide(request):return bytes([39])+struct.pack('<HHBB',epoch,request,4,0)
def bundle(messages):return bytes([8,len(messages)])+b''.join(struct.pack('<H',len(m))+m for m in messages)
tags=[11,12,11,12,13,14,15,16]
tag_bundle=bundle([hide(n) for n in tags]);assert commands[1][0]==tag_bundle==(folder/'tags-bundle.bin').read_bytes()
scene(commands[1][1],39,16,epoch)
invalid_copy=bytes([9])+struct.pack('<8H',0,0,0,1,0,0,1,1)
late=bundle([hide(17),invalid_copy]);assert commands[3][0]==late==(folder/'late-failure-bundle.bin').read_bytes()
expected_notifications=[(graphics[1][0]['event'],tag) for tag in tags]+[(graphics[3][0]['event'],17)]
assert notifications==expected_notifications
assert notification_sources==[tag_bundle]*8+[late]
assert [(r['eventID'],r['tag']) for r in rows if r['event']=='settled-notification']==expected_notifications
key=(folder/'keyframe-command.bin').read_bytes();delta=(folder/'delta-command.bin').read_bytes()
overlap=bytes([9])+struct.pack('<8H',100,180,63,31,101,181,63,31)
copy=bytes([9])+struct.pack('<8H',99,99,129,115,301,99,129,115)
assert (folder/'overlap-command.bin').read_bytes()==overlap and (folder/'copy-command.bin').read_bytes()==copy
visual=bundle([key,delta,overlap,copy]);assert commands[5][0]==visual==(folder/'visual-bundle.bin').read_bytes()
assert commands[6][0]==bytes([0x88,0,0xab,0xcd])==(folder/'empty-bundle.bin').read_bytes()
invalid=[bytes([8,1,2,0,8,0]),bytes([8,1,1,0,11]),bytes([8,1,1,0,15]),bytes([8,1,17,0,9])]
for i,bad in enumerate(invalid):assert commands[7+i][0]==bad==(folder/f'invalid-bundle-{i}.bin').read_bytes()
assert commands[-1][0]==bytes([11])
for i,(command,reply) in enumerate(commands):
 if i in (0,1):continue
 result='invalid' if i in (3,7,8,9,10) else 'cleared' if i==len(commands)-1 else 'ok'
 expected={'glassly':'graphics','abi':1,'result':result}
 if result=='ok':expected['presentation']='scheduled'
 assert reply==expected
 if i in (2,4) or 11<=i<len(commands)-1:assert command==bytes([36,0])
def decode(data,pixels):
 output=[];p=0
 while p<len(data):
  op=data[p];p+=1;count=op>>4;color=op&15
  if not count:
   count=data[p];p+=1
   if not count:count=int.from_bytes(data[p:p+2],'little');p+=2
  assert count and len(output)+count<=pixels;output.extend([color]*count)
 assert len(output)==pixels
 return bytes((output[i]<<4)|output[i+1] for i in range(0,pixels,2))
assert key[0]==6;frame=bytearray(decode(key[1:],600*350));assert frame==(folder/'expected-keyframe.gray4').read_bytes()
# Verify the intended black background and glyph geometry independently of the
# Swift helper's saved expected frame, then verify checkerboard pixels.
intended=bytearray(105000)
glyphs=[(30,17,17,30,17,17,30),(14,17,17,14,17,17,14)]
for g,rows_ in enumerate(glyphs):
 for row,bits in enumerate(rows_):
  for col in range(5):
   if bits & (16>>col):
    for y in range(100+row*6,106+row*6):
     for x in range(100+g*42+col*6,106+g*42+col*6):
      index=y*300+x//2;intended[index]|=15 if x&1 else 240
assert frame==intended
assert delta[:7]==bytes([3,25,90,16,16,1,0]);box=decode(delta[7:],64*32)
assert box==bytes(255 if (x//8+y//8)%2==0 else 0 for y in range(32) for x in range(0,64,2))
for y in range(32):frame[(180+y)*300+50:(180+y)*300+82]=box[y*32:(y+1)*32]
assert frame==(folder/'expected-seed.gray4').read_bytes()
def copy_snapshot(frame,command):
 assert command[0]==9 and len(command)==17
 sx,sy,w,h,dx,dy,dw,dh=struct.unpack('<8H',command[1:]);assert w==dw and h==dh and w and h
 assert sx+w<=600 and sy+h<=350 and dx+w<=600 and dy+h<=350
 # Independent full unpack/snapshot/repack, without reproducing native traversal.
 pixels=[n for byte in frame for n in (byte>>4,byte&15)];before=pixels[:]
 for y in range(h):pixels[(dy+y)*600+dx:(dy+y)*600+dx+w]=before[(sy+y)*600+sx:(sy+y)*600+sx+w]
 return bytearray((pixels[i]<<4)|pixels[i+1] for i in range(0,len(pixels),2))
frame=copy_snapshot(frame,overlap);assert frame==(folder/'expected-overlap.gray4').read_bytes()
frame=copy_snapshot(frame,copy);assert frame==(folder/'expected-final.gray4').read_bytes()
assert rows[-1]['event']=='smoke-complete'
visible=[r for r in rows if r['event']=='pattern-visible'];ends=[r for r in rows if r['event']=='hold-ended']
assert len(visible)==len(ends)==1
start=visible[0]['uptime'];clear=graphics[-1][0]['_submitted_uptime'];assert clear>=start
if ends[0]['finishRequested']:
 finish=json.loads((folder/'finish-requested.json').read_text());assert finish['reason']=='user confirmed visible pattern'
else:assert clear-start>=300
hold_times=[start]+[a['_submitted_uptime'] for a,b in graphics[11:]]
assert all(b>=a for a,b in zip(hold_times,hold_times[1:]))
report={'format':'memomind-native-bundle-smoke-verification-v1','capture':str(folder),'complete':True,'startup_notifications_captured':startup_notices,'native_service_notifications_logged':len(status_notices),'all_native_write_submissions_completed':True,'application_frames_independently_parsed_and_correlated':True,'bundle_acknowledged':True,'final_cache_reply_verified':True,'ordered_settled_notifications':notifications,'invalid_commands_rejected':5,'late_failure_settled_verified':True,'lease_renewals_acknowledged':len(commands)-10,'cleared':True,'encoded_and_expected_pixels_independently_verified':True,'hardware_pixel_readback':False,'physical_single_presentation_proven':False,'background_gray4':0,'hold_seconds_before_clear':clear-start,'finish_requested':ends[0]['finishRequested'],'maximum_hold_submission_gap_seconds':max(b-a for a,b in zip(hold_times,hold_times[1:])),'continuous_pixel_retention_proven':False,'visual_confirmation':'separate user observation required','trace_sha256':hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest()}
assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
