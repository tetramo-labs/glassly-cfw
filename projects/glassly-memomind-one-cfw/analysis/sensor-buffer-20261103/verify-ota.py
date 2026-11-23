"""Offline raw application trace validation, not live admission/transaction replay.

Revision 9 buffered sensor candidate; no StockTransaction/eligibility bypass, no device access.
"""
if not __debug__: raise RuntimeError('Refuse optimized verification')
import argparse,hashlib,json,math,sys,zlib
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts'))
from decode_memomind import OtaStream,encode_ota,encode_chunk
from memomind_transport import GmStream
PIN='fa230c0c893d9b810d0901dcfec2798dc4a78f043069aef865a07c94b883eb86'

def unique(pairs):
 d={}
 for k,v in pairs:
  assert k not in d,'Duplicate JSON key';d[k]=v
 return d

def loads(data):return json.loads(data,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(AssertionError('Nonfinite JSON')))
def sha(data):return hashlib.sha256(data).hexdigest()
def same(a,b):assert type(a) is type(b) and a==b,(a,b)

def verify(rows,image,result):
 assert rows and rows[-1]['event']=='operation-complete'
 assert not any(r['event'] in ('failed','operation-failed') for r in rows)
 times=[r['uptimeSeconds'] for r in rows]
 assert all(type(t) in (int,float) and math.isfinite(t) for t in times)
 assert all(a<=b for a,b in zip(times,times[1:]))
 assert rows[-1]['result']==result
 attempts=[r for r in rows if r['event']=='attempt'];assert len(attempts)==1
 for k,val in dict(address='4C:3C:8F:90:CC:C3',command='flash',confirmWrite=True,imageSHA256=sha(image)).items():same(attempts[0][k],val)
 writes={s:deque() for s in ('control','ota')};counts={s:0 for s in writes}
 op={d:OtaStream() for d in (0,1)};cp={d:GmStream(legacy_repeat_fa=True,fragment_acks=True) for d in (0,1)}
 control_pending={};control=[];ota=[];last_control=None;control_acks=set();notify_accepted=False;unsolicited=0
 requests=[(1,1,1,b''),(2,1,2,b''),(0x15,1,0x1c,bytes.fromhex('0800000101'))]
 for index,row in enumerate(rows):
  ev=row['event']
  if ev not in ('transmitSubmission','transmitCompletion','receive'):continue
  session=row.get('session');assert session in writes
  raw=bytes.fromhex(row['hex']);assert raw and type(row['bytes']) is int and row['bytes']==len(raw)
  if ev=='transmitCompletion':
   assert type(row['status']) is int and row['status']==0 and writes[session]
   assert writes[session].popleft()==raw,'Write completion differs';continue
  direction=int(ev=='receive')
  if not direction:writes[session].append(raw);counts[session]+=1
  if session=='ota':
   assert notify_accepted,'OTA before accepted control notification'
   for frame in op[direction].feed(raw):ota.append((direction,frame,index))
  else:
   for m in cp[direction].feed(raw):
    key=(m['event'],m['service'],m['command'])
    if not direction:
     assert not control_pending and len(control)<3
     wanted=requests[len(control)];assert (*key,bytes(m['body']))==wanted
     control_pending[key]=m;control_acks.discard(key)
    elif not m['tlvs']:
     assert m['head']==250
     if key in control_pending:assert key not in control_acks;control_acks.add(key)
     else:assert last_control and key==last_control[0] and not last_control[1];last_control=(key,True)
    elif key in control_pending:
     control.append((control_pending.pop(key),m));last_control=(key,key in control_acks)
     if key==(0x15,1,0x1c):assert m['tlvs']==[(6,b'\x01')];notify_accepted=True
    else:
     assert m['service']!=15 and key not in [x[:3] for x in requests],'Uncorrelated reserved/duplicate control reply'
     unsolicited+=1
 assert all(not q for q in writes.values()) and not control_pending and len(control)==3
 assert all(not p.buffer for p in op.values()) and all(not p.buffer and not p.body for p in cp.values())
 assert control[0][1]['tlvs']==[(6,b'\0')]
 info=control[1][1]['tlvs'];assert len(info)==1 and info[0][0]==2
 identity=loads(info[0][1].rstrip(b'\0'))
 for k,v in dict(model='H001Y',hver='2.1.2',fver='1.3',ver='1.0.3.127',mac='4C:3C:8F:90:CC:C3').items():same(identity[k],v);same(result['device'][k],v)
 pos=0;sequence=0;wire=hashlib.sha256();headers=[];pacing_waits=[]
 def take(direction):
  nonlocal pos
  assert pos<len(ota),'Incomplete OTA';d,frame,index=ota[pos];pos+=1
  assert d==direction,'OTA send/reply ordering mismatch'
  assert frame[3]==(0 if direction else 0xc0),'Unsupported OTA flags'
  if not direction:wire.update(frame)
  return frame
 def response(cmd,seq):
  f=take(1);assert f[4]==cmd and len(f[7:-1])>=2
  assert f[7]==0 and f[8]==seq,'OTA transport status/ACK sequence'
  return f[9:-1]
 def command(cmd,params=b''):
  nonlocal sequence
  sequence=(sequence+1)&255
  outgoing=take(0);assert outgoing==encode_ota(cmd,sequence,params),'Unexpected outgoing command bytes'
  if cmd==0xe2:headers.append(outgoing[8:-1])
  return response(cmd,sequence)
 attached=command(2,b'\xff'*5);fields={}
 while attached:
  n=attached[0];assert n>=1 and len(attached)>=n+1
  k=attached[1];assert k not in fields;fields[k]=attached[2:n+1];attached=attached[n+1:]
 assert fields.get(1)==image[:4]
 assert command(0xe1)==bytes.fromhex('000000000012')
 assert command(0xe2,image[:18])==b'\x03'
 entry=command(0xe3);assert len(entry)==8 and entry[0]==0 and entry[-1]==1
 offset=int.from_bytes(entry[1:5],'big');size=int.from_bytes(entry[5:7],'big');assert offset==18
 assert headers==[image[:18]]
 recovered=bytearray(headers[0]);blocks=[];chunks=0
 while True:
  assert 0<size<=4096 and offset==len(recovered) and offset+size<=len(image),'Invalid requested range'
  sequence=(sequence+1)&255;base=sequence
  for i,rel in enumerate(range(0,size,630)):
   f=take(0);assert f[4]==0xe5 and len(f[7:-1])>=10
   seq=(base+i)&255;off=int.from_bytes(f[8:12],'big');data=f[12:-5]
   expected=image[offset+rel:offset+min(rel+630,size)]
   assert off==len(recovered)==offset+rel and data==expected
   assert f[7]==seq and int.from_bytes(f[-5:-1],'big')==zlib.crc32(data),'Chunk CRC or sequence'
   assert f==encode_chunk(seq,off,data),'Noncanonical chunk envelope'
   recovered.extend(data);chunks+=1
  ack=response(0xe5,seq);assert len(ack)==9 and ack[0]==0,'Unsupported block status'
  pacing=int.from_bytes(ack[7:9],'big');assert pacing in (0,2000),'Unsupported pacing field'
  if pacing:
   assert pos<len(ota) and ota[pos][0]==0,'Missing paced continuation'
   waited=rows[ota[pos][2]]['uptimeSeconds']-rows[ota[pos-1][2]]['uptimeSeconds']
   assert waited>=2,'Pacing wait shorter than two seconds'
   pacing_waits.append(waited)
  blocks.append(dict(offset=offset,length=size,base_sequence=base,ack_sequence=seq))
  offset=int.from_bytes(ack[1:5],'big');size=int.from_bytes(ack[5:7],'big')
  if offset==size==0:assert len(recovered)==len(image),'Premature completion';break
 assert command(0xe6)==b'\0' and command(3,b'\0')==b'\0'
 assert pos==len(ota),'Extra OTA frames after reboot ACK'
 assert bytes(recovered)==image
 for k,v in dict(state='reboot acknowledged',transferredRange=[18,len(image)],blocks=len(blocks),chunks=chunks,imageSHA256=sha(image),automaticRetries=0,modifiedImage=True,checkOnly=False,controlLinkPreserved=True,postRebootVersionVerified=False,command='flash').items():same(result[k],v)
 same(result['attachFields'],{str(k):v.hex() for k,v in fields.items()})
 return dict(passed=True,pacing_waits_seconds=pacing_waits,format='memomind-offline-application-ota-proof-v1',image_sha256=sha(image),reconstructed_sha256=sha(recovered),reconstructed_bytes=len(recovered),entire_ota_reconstructed=True,blocks=len(blocks),chunks=chunks,transferred_range=[18,len(image)],outgoing_ota_wire_sha256=wire.hexdigest(),ota_frames_consumed=pos,all_tx_submissions_completed=True,write_submissions=counts,control_requests=3,unsolicited_control_messages=unsolicited,pre_ota_acceptance_before_ota=True,block_crc_and_sequence_verified=True,block_requests=blocks,device_actions=False,limitations=['Application callback TX/RX evidence, not an independent HCI/radio capture.','Independent strict frame/range reconstruction; not execution of Python StockTransaction or a live-admission bypass.','Reboot acknowledgment is not proof of post-reboot boot, UI safety or RAM savings.','Control health after last recorded traffic is not proven solely by a preserved-link result flag.'])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 assert not a.output.exists(),'Refuse overwrite'
 image=(ROOT/'captures/firmware/sensor-buffer-001/firmware.bin').read_bytes();assert sha(image)==PIN
 trace=(a.capture/'trace.jsonl').read_bytes();rows=[loads(r) for r in trace.splitlines()];result=loads((a.capture/'result.json').read_bytes())
 report=verify(rows,image,result);same(result['releaseName'],'sensor-buffer-001')
 report.update(trace_sha256=sha(trace),capture=str(a.capture),verifier_sha256=sha(Path(__file__).read_bytes()),parser_sha256={name:sha((ROOT/'scripts'/name).read_bytes()) for name in ('decode_memomind.py','memomind_transport.py')})
 a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','image_sha256','reconstructed_bytes','blocks','chunks')}))
if __name__=='__main__':main()
