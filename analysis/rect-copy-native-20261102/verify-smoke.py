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
for a,b in graphics:
 assert len(a['tlvs'])==1 and a['tlvs'][0][0]==1
 assert len(b['tlvs'])==1 and b['tlvs'][0][0]==5
 raw=b['tlvs'][0][1];raw=raw[:-1] if raw.endswith(b'\0') else raw
 assert raw in [b'{"glassly":"graphics","abi":1,"result":"'+v+b'"'+(b',"presentation":"scheduled"' if v==b'ok' else b'')+b'}' for v in (b'ok',b'invalid',b'cleared')]
commands=[(a['tlvs'][0][1],decode_json(b)) for a,b in graphics]
key=(folder/'keyframe-command.bin').read_bytes();delta=(folder/'delta-command.bin').read_bytes()
import struct
expected_commands=[key,delta,bytes([9])+struct.pack('<8H',100,180,63,31,101,181,63,31),bytes([9])+struct.pack('<8H',99,99,129,115,301,99,129,115),bytes([9])+struct.pack('<8H',600,99,129,115,301,99,129,115),bytes([9])+struct.pack('<8H',99,99,129,115,301,99,128,115),bytes([9])]
assert [a for a,b in commands[:7]]==expected_commands
for filename,index in [('overlap-command.bin',2),('copy-command.bin',3),('invalid-bounds-command.bin',4),('invalid-size-command.bin',5)]:assert (folder/filename).read_bytes()==expected_commands[index]
assert commands[-1][0]==bytes([11])
for i,(command,reply) in enumerate(commands):
 expected='invalid' if i in (4,5,6) else 'cleared' if i==len(commands)-1 else 'ok'
 wanted={'glassly':'graphics','abi':1,'result':expected}
 if expected=='ok':wanted['presentation']='scheduled'
 assert reply==wanted
 if 7<=i<len(commands)-1:assert command==bytes([36,0])
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
glyphs=[(30,17,17,30,20,18,17),(16,16,16,16,16,16,31),(31,16,16,30,16,16,31)]
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
frame=copy_snapshot(frame,expected_commands[2]);assert frame==(folder/'expected-overlap.gray4').read_bytes()
frame=copy_snapshot(frame,expected_commands[3]);assert frame==(folder/'expected-final.gray4').read_bytes()
assert rows[-1]['event']=='smoke-complete'
visible=[r for r in rows if r['event']=='pattern-visible'];assert len(visible)==1
start=visible[0]['uptime'];clear=graphics[-1][0]['_submitted_uptime']
assert clear-start>=90 and len(commands)>8
hold_times=[start]+[a['_submitted_uptime'] for a,b in graphics[7:]]
assert all(b>=a for a,b in zip(hold_times,hold_times[1:]))
max_gap=max(b-a for a,b in zip(hold_times,hold_times[1:]))

report={'format':'memomind-native-rect-copy-smoke-verification-v1','capture':str(folder),'complete':True,'all_native_write_submissions_completed':True,'application_frames_independently_parsed_and_correlated':True,'keyframe_acknowledged':True,'delta_acknowledged':True,'overlap_copy_acknowledged':True,'rectangle_copy_acknowledged':True,'invalid_commands_rejected':3,'lease_renewals_acknowledged':len(commands)-8,'cleared':True,'encoded_and_expected_pixels_independently_verified':True,'hardware_pixel_readback':False,'background_gray4':0,'hold_seconds_before_clear':clear-start,'maximum_renewal_or_clear_submission_gap_seconds':max_gap,'continuous_pixel_retention_proven':False,'visual_confirmation':'separate user observation required','trace_sha256':hashlib.sha256((folder/'trace.jsonl').read_bytes()).hexdigest()}
assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
