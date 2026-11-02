#!/usr/bin/env python3
"""Entirely synthetic trace verification. No device/user confirmation evidence."""
from pathlib import Path
import sys, json, struct, subprocess, copy, hashlib
if not __debug__: raise RuntimeError('Assertions required')
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from memomind_transport import gm_frames
HERE=Path(__file__).resolve().parent
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);capture=OUT/'synthetic-capture';capture.mkdir()
VERIFIER=ROOT/'analysis/bundle-native-20261102/verify-smoke-v3.py'
def save(name,data):(capture/name).write_bytes(data)
def packed(p):return bytes((p[i]<<4)|p[i+1] for i in range(0,len(p),2))
def rle(p):
 out=bytearray();i=0
 while i<len(p):
  n=1
  while i+n<len(p) and p[i+n]==p[i] and n<65535:n+=1
  if n<=15:out.append(n<<4|p[i])
  elif n<=255:out.extend([p[i],n])
  else:out.extend([p[i],0]);out.extend(struct.pack('<H',n))
  i+=n
 return bytes(out)
def bundle(children):return bytes([8,len(children)])+b''.join(struct.pack('<H',len(c))+c for c in children)
epoch=0x12ab
reset=bytes([41,0,0,1,0,0,250]);save('reset-command.bin',reset)
def hide(tag):return bytes([39])+struct.pack('<HHBB',epoch,tag,4,0)
tags=[11,12,11,12,13,14,15,16];tag_bundle=bundle([hide(tag) for tag in tags]);save('tags-bundle.bin',tag_bundle)
invalid_copy=b'\x09'+struct.pack('<8H',0,0,0,1,0,0,1,1)
late=bundle([hide(17),invalid_copy]);save('late-failure-bundle.bin',late)
pixels=[0]*210000
for g,rows in enumerate([(30,17,17,30,17,17,30),(14,17,17,14,17,17,14)]):
 for row,bits in enumerate(rows):
  for col in range(5):
   if bits&(16>>col):
    for y in range(100+row*6,106+row*6):
     for x in range(100+g*42+col*6,106+g*42+col*6):pixels[y*600+x]=15
key=b'\x06'+rle(pixels);save('keyframe-command.bin',key);save('expected-keyframe.gray4',packed(pixels))
box=[15 if (x//8+y//8)%2==0 else 0 for y in range(32) for x in range(64)]
delta=bytes([3,25,90,16,16,1,0])+rle(box);save('delta-command.bin',delta)
for y in range(32):pixels[(180+y)*600+100:(180+y)*600+164]=box[y*64:(y+1)*64]
save('expected-seed.gray4',packed(pixels));copies=[]
for name,expected,sx,sy,dx,dy,w,h in [('overlap','overlap',100,180,101,181,63,31),('copy','final',99,99,301,99,129,115)]:
 cmd=b'\x09'+struct.pack('<8H',sx,sy,w,h,dx,dy,w,h);copies.append(cmd);save(name+'-command.bin',cmd)
 before=pixels[:]
 for y in range(h):pixels[(dy+y)*600+dx:(dy+y)*600+dx+w]=before[(sy+y)*600+sx:(sy+y)*600+sx+w]
 save('expected-'+expected+'.gray4',packed(pixels))
visual=bundle([key,delta,*copies]);save('visual-bundle.bin',visual)
empty=bytes([0x88,0,0xab,0xcd]);save('empty-bundle.bin',empty)
invalid=[bytes([8,1,2,0,8,0]),bytes([8,1,1,0,11]),bytes([8,1,1,0,15]),bytes([8,1,17,0,9])]
for i,bad in enumerate(invalid):save(f'invalid-bundle-{i}.bin',bad)
commands=[reset,tag_bundle,b'\x24\0',late,b'\x24\0',visual,empty,*invalid,b'\x24\0',b'\x0b']
rows=[]
def rx(event,obj,label):
 raw=json.dumps(obj,separators=(',',':')).encode()
 # Native503reply physical fragments; coalesce into one callback where possible.
 wire=b''.join(gm_frames(event,15,0x7d,b'\x05'+len(raw).to_bytes(3,'big')+raw))
 return dict(event='receive',hex=wire.hex(),label=label)
def main_reply(i):
 if i in (0,1):
  data=struct.pack('<BHBHI',41 if i==0 else 39,1 if i==0 else 16,0,epoch,1)+(bytes([0,64,0]) if i==0 else b'\0')
  return dict(glassly='scene',abi=1,result='ok',replyHex=data.hex())
 result='invalid' if i in (3,7,8,9,10) else 'cleared' if i==len(commands)-1 else 'ok'
 obj=dict(glassly='graphics',abi=1,result=result)
 if result=='ok':obj['presentation']='scheduled'
 return obj
for i,command in enumerate(commands):
 event=64+i
 if i==11:rows.append(dict(event='pattern-visible'))
 if i==12:rows.append(dict(event='hold-ended',finishRequested=False))
 frames=gm_frames(event,15,0x7d,b'\x01'+len(command).to_bytes(3,'big')+command,fragment_payload=642)
 for fragment,packet in enumerate(frames):
  # Independent nativeMTU-style splitting across application-frame boundaries.
  for offset in range(0,len(packet),183):
   chunk=packet[offset:offset+183]
   rows.extend([dict(event='transmitSubmission',hex=chunk.hex(),label=f'tx-{i}'),dict(event='transmitCompletion',hex=chunk.hex(),status=0,label=f'complete-{i}')])
  if fragment+1<len(frames):
   ack=bytes([packet[0],0,0,9,event,15,0x7d]);ack+=(sum(ack)&65535).to_bytes(2,'big')
   rows.append(dict(event='receive',hex=ack.hex(),label=f'ack-{i}-{fragment}'))
 rows.append(rx(event,main_reply(i),f'main-{i}'))
 for j,tag in enumerate(tags if i==1 else [17] if i==3 else []):
  rows.append(rx(event,dict(glassly='scene',abi=1,result='settled',tag=tag),f'tag-{i}-{j}'))
  rows.append(dict(event='settled-notification',eventID=event,tag=tag,label=f'taglog-{i}-{j}'))
for i,row in enumerate(rows):row['uptime']=i/100
start=next(r['uptime'] for r in rows if r['event']=='pattern-visible')
shift=False
for row in rows:
 if row['event']=='hold-ended':shift=True
 if shift:row['uptime']+=301
rows.append(dict(event='smoke-complete',uptime=rows[-1]['uptime']+.01))
(capture/'README.txt').write_text('Entirely synthetic. No hardware, visibility, or user-confirmation claims.\n')
results=[]
def run(name,trace,success,optimized=False):
 (capture/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in trace))
 args=[sys.executable]+(['-O'] if optimized else [])+[str(VERIFIER),str(capture),str(OUT/(name+'.json'))]
 p=subprocess.run(args,cwd=ROOT,capture_output=True)
 (OUT/(name+'.stdout')).write_bytes(p.stdout);(OUT/(name+'.stderr')).write_bytes(p.stderr)
 passed=(p.returncode==0)==success
 results.append(dict(name=name,expected_success=success,exit_code=p.returncode,passed=passed))
 return passed
def altered_reply(label,obj):
 trace=copy.deepcopy(rows);index=next(i for i,r in enumerate(trace) if r.get('label')==label)
 original=trace[index];event=bytes.fromhex(original['hex'])[4]
 trace[index]={**rx(event,obj,label),'uptime':original['uptime']};return trace
run('valid-fragmented',rows,True)
run('optimized-refused',rows,False,True)
for label in ['main-0','main-1','main-5']:
 i=int(label.split('-')[1]);bad=main_reply(i);bad['abi']=True
 run('boolean-abi-'+str(i),altered_reply(label,bad),False)
bad=dict(glassly='scene',abi=1,result='settled',tag=True)
run('boolean-tag',altered_reply('tag-1-0',bad),False)
for label,target in [('tag-before-primary','main-1'),('tag-before-request','tx-1')]:
 trace=copy.deepcopy(rows);i=next(i for i,r in enumerate(trace) if r.get('label')=='tag-1-0');m=trace.pop(i)
 at=next(i for i,r in enumerate(trace) if r.get('label')==target);m['uptime']=trace[at]['uptime']-.001;trace.insert(at,m)
 run(label,trace,False)
trace=copy.deepcopy(rows);i=next(i for i,r in enumerate(trace) if r.get('label')=='tag-1-0')
raw=bytes.fromhex(trace[i]['hex']);body=raw[7:-2];trace[i]['hex']=b''.join(gm_frames(99,15,0x7d,body)).hex()
run('wrong-tag-event',trace,False)
trace=copy.deepcopy(rows);i=next(i for i,r in enumerate(trace) if r.get('label')=='main-1');trace.insert(i+1,copy.deepcopy(trace[i]));run('duplicate-main',trace,False)
trace=copy.deepcopy(rows)
moved=[r for r in trace if r.get('label') in ('tx-1','complete-1') or str(r.get('label','')).startswith('ack-1-')]
trace=[r for r in trace if r not in moved]
at=next(i for i,r in enumerate(trace) if r.get('label')=='main-0')
for i,r in enumerate(moved):r['uptime']=trace[at]['uptime']-0.001+(i/100000)
trace[at:at]=moved
run('overlapping-business-requests',trace,False)
trace=copy.deepcopy(rows);trace.pop(next(i for i,r in enumerate(trace) if r['event']=='transmitCompletion'));run('missing-completion',trace,False)
trace=[r for r in copy.deepcopy(rows) if r.get('label')!='tag-1-0'];run('missing-tag',trace,False)
trace=copy.deepcopy(rows);i=next(i for i,r in enumerate(trace) if r.get('label')=='tag-1-0');trace.insert(i+1,copy.deepcopy(trace[i]));run('duplicate-tag',trace,False)
for name,change in [('uppercase-hex',lambda h:h.upper()),('whitespace-hex',lambda h:' '.join(h[i:i+2] for i in range(0,len(h),2))),('truncated-scene',lambda h:h[:20])]:
 bad=main_reply(0);bad['replyHex']=change(bad['replyHex']);run(name,altered_reply('main-0',bad),False)
bad=main_reply(1);wire=bytearray.fromhex(bad['replyHex']);wire[1]=15;bad['replyHex']=wire.hex();run('wrong-final-scratch-request',altered_reply('main-1',bad),False)
bad=main_reply(1);wire=bytearray.fromhex(bad['replyHex']);wire[4]^=1;bad['replyHex']=wire.hex();run('wrong-scene-epoch',altered_reply('main-1',bad),False)
bad=dict(glassly='graphics',abi=1,result='ok',presentation='scheduled');run('late-failure-misreported-ok',altered_reply('main-3',bad),False)
trace=copy.deepcopy(rows)
for row in trace:
 if row['event']=='hold-ended' or row.get('label') in ('tx-12','complete-12','main-12') or row['event']=='smoke-complete':row['uptime']-=301
run('timeout-hold-too-short',trace,False)
p=capture/'expected-final.gray4';original=p.read_bytes();corrupt=bytearray(original);corrupt[0]^=1;p.write_bytes(corrupt);run('wrong-final-pixels',rows,False);p.write_bytes(original)
# Unrelated native service messages are preserved with exact bodies, not interpreted.
def native_trace(service=1,command=45,body=bytes.fromhex('080000010001000010690af5ff50005e0a00000000b0ff0000'),logged=True):
 trace=copy.deepcopy(rows);at=next(i for i,r in enumerate(trace) if r.get('label')=='main-5')+1
 notice=dict(event='receive',hex=b''.join(gm_frames(11,service,command,body)).hex(),uptime=trace[at-1]['uptime']+.0001)
 add=[notice]
 if logged:add.append(dict(event='native-service-notification',eventID=11,service=service,command=command,bodyHex=body.hex(),uptime=notice['uptime']))
 trace[at:at]=add;return trace
run('captured-native-telemetry',native_trace(),True)
run('captured-native-status',native_trace(command=58,body=bytes.fromhex('0800000100')),True)
run('unlogged-native-rejected',native_trace(logged=False),False)
run('private-service-still-rejected',native_trace(service=15),False)
trace=native_trace();next(r for r in trace if r['event']=='native-service-notification')['bodyHex']='00'
run('wrong-native-log-body',trace,False)
trace=native_trace();next(r for r in trace if r['event']=='native-service-notification')['eventID']=12
run('wrong-native-log-event',trace,False)
# Restore the valid synthetic trace as the representative fixture.
(capture/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
report={'hardware_tested':False,'fixture_origin':'Fully synthetic Python wire/pixel model; original firmware routines are not executed.','verifier_sha256':hashlib.sha256(VERIFIER.read_bytes()).hexdigest(),'cases':results,'count':len(results),'passed':all(r['passed'] for r in results)}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not report['passed']:sys.exit(1)
