"""Synthetic, non-device validation of the trace verifier, including rejection paths."""
from pathlib import Path
import sys,json,struct,subprocess,shutil
if not __debug__:raise RuntimeError('Assertions required')
sys.path.insert(0,str(Path('scripts').resolve()))
from memomind_transport import gm_frames
root=Path('analysis/rect-copy-native-20261102');out=root/'verifier-selftest-v3';out.mkdir(exist_ok=False);capture=out/'synthetic-capture';capture.mkdir()
pixels=[0]*(600*350)
for g,rows in enumerate([(30,17,17,30,20,18,17),(16,16,16,16,16,16,31),(31,16,16,30,16,16,31)]):
 for row,bits in enumerate(rows):
  for col in range(5):
   if bits&(16>>col):
    for y in range(100+row*6,106+row*6):
     for x in range(100+g*42+col*6,106+g*42+col*6):pixels[y*600+x]=15

def packed(p):return bytes((p[i]<<4)|p[i+1] for i in range(0,len(p),2))
def rle(p):
 out=bytearray();i=0
 while i<len(p):
  count=1
  while i+count<len(p) and p[i+count]==p[i] and count<65535:count+=1
  if count<16:out.append((count<<4)|p[i])
  elif count<256:out.extend([p[i],count])
  else:out.extend([p[i],0]);out.extend(struct.pack('<H',count))
  i+=count
 return bytes(out)
def save(name,b): (capture/name).write_bytes(b)
key=bytes([6])+rle(pixels);save('keyframe-command.bin',key);save('expected-keyframe.gray4',packed(pixels))
box=[15 if (x//8+y//8)%2==0 else 0 for y in range(32) for x in range(64)]
delta=bytes([3,25,90,16,16,1,0])+rle(box);save('delta-command.bin',delta)
for y in range(32):pixels[(180+y)*600+100:(180+y)*600+164]=box[y*64:(y+1)*64]
save('expected-seed.gray4',packed(pixels));commands=[key,delta]
for name,expected,sx,sy,dx,dy,w,h in [('overlap','overlap',100,180,101,181,63,31),('copy','final',99,99,301,99,129,115)]:
 cmd=bytes([9])+struct.pack('<8H',sx,sy,w,h,dx,dy,w,h);commands.append(cmd);save(name+'-command.bin',cmd)
 before=pixels[:]
 for y in range(h):pixels[(dy+y)*600+dx:(dy+y)*600+dx+w]=before[(sy+y)*600+sx:(sy+y)*600+sx+w]
 save('expected-'+expected+'.gray4',packed(pixels))
for name,coords in [('invalid-bounds',(600,99,129,115,301,99,129,115)),('invalid-size',(99,99,129,115,301,99,128,115))]:
 cmd=bytes([9])+struct.pack('<8H',*coords);save(name+'-command.bin',cmd);commands.append(cmd)
commands.extend([bytes([9]),bytes([36,0]),bytes([11])]);rows=[]
for i,cmd in enumerate(commands):
 for packet in gm_frames(i+1,15,0x7d,bytes([1])+len(cmd).to_bytes(3,'big')+cmd,fragment_payload=642):
  rows.extend([{'event':'transmitSubmission','hex':packet.hex()},{'event':'transmitCompletion','hex':packet.hex(),'status':0}])
 result='invalid' if i in (4,5,6) else 'cleared' if i==8 else 'ok'
 reply={'glassly':'graphics','abi':1,'result':result}
 if result=='ok':reply['presentation']='scheduled'
 raw=json.dumps(reply,separators=(',',':')).encode()
 for packet in gm_frames(i+1,15,0x7d,bytes([5])+len(raw).to_bytes(3,'big')+raw):rows.append({'event':'receive','hex':packet.hex()})
# Synthetic monotonic times, including a90-second display window.
for i,row in enumerate(rows):row['uptime']=float(i)/100
clear_start=next(i for i,row in enumerate(rows) if row['event']=='transmitSubmission' and row['hex'].startswith('fa00000e090f7d'))
renew_start=next(i for i,row in enumerate(rows) if row['event']=='transmitSubmission' and row['hex'].startswith('fa00000f080f7d'))
rows.insert(renew_start,{'event':'pattern-visible','uptime':rows[renew_start]['uptime']-0.01})
for row in rows[clear_start+1:]:row['uptime']+=90
rows.append({'event':'smoke-complete','uptime':rows[-1]['uptime']+0.01})
def run(name,trace,ok):
 (capture/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in trace))
 r=subprocess.run([sys.executable,str(root/'verify-smoke.py'),str(capture),str(out/(name+'.json'))],capture_output=True)
 (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
 assert (r.returncode==0)==ok,(name,r.stderr)
run('valid',rows,True)
duplicated=rows[:-1]+[next(x for x in rows if x['event']=='receive'),rows[-1]];run('duplicate-reply',duplicated,False)
missing=rows[:];missing.pop(next(i for i,x in enumerate(missing) if x['event']=='transmitCompletion'));run('missing-completion',missing,False)
p=(capture/'expected-final.gray4');b=bytearray(p.read_bytes());b[0]^=1;p.write_bytes(b);run('wrong-pixels',rows,False);b[0]^=1;p.write_bytes(b)
(out/'report.json').write_text(json.dumps({'hardware_tested':False,'synthetic_cases':4,'passed':True,'checks':['valid fragmented request and correlated ACKs','duplicate reserved reply rejected','missing native completion rejected','incorrect expected pixels rejected']},indent=2)+'\n')
print('4 synthetic verifier checks passed; no hardware actions')
