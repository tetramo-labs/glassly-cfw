#!/usr/bin/env python3
"""Explicit one-shot canary client. No transport/device opening, retry or reset.

The token prevents accidental opcode use; it is not authentication. A timeout
may leave the native worker running. A new read-only status client can inspect
it; never repeat an ambiguous start. Full backup/owner validation are external
preconditions and cannot be inferred from the query profile alone.
"""
import json,struct
from memomind_scene import _DeadlineIO,tlv_bytes
from memomind_transport import GmStream,request_gm
from memomind_flash_read import FlashReadClient,CANARY_PROFILE
SERVICE,COMMAND,TOKEN=15,0x7a,0x43414e31
class CanaryError(RuntimeError):pass
class CanaryProtocolError(CanaryError):pass
class CanaryNativeError(CanaryError):
 def __init__(self,reply):self.reply=reply;super().__init__('Canary rejected: '+repr(reply))
def _object(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('Duplicate key')
  d[k]=v
 return d
def decode_reply(message):
 tlvs=message['tlvs']
 if len(tlvs)!=1 or tlvs[0][0]!=5 or len(tlvs[0][1])>768:raise CanaryProtocolError('Expected one bounded JSON TLV')
 raw=tlvs[0][1]
 if raw.endswith(b'\0'):raw=raw[:-1]
 try:r=json.loads(raw.decode('utf-8'),object_pairs_hook=_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite')))
 except (ValueError,UnicodeError) as e:raise CanaryProtocolError('Malformed JSON') from e
 if not isinstance(r,dict) or r.get('glassly')!='flash-canary' or type(r.get('abi')) is not int or r['abi']!=1:raise CanaryProtocolError('Wrong identity')
 if r.get('result')!='ok':
  if set(r)=={'glassly','abi','result'} and r.get('result') in ('invalid','wrong-image','registry-invalid','already-used','allocation-failed'):raise CanaryNativeError(r)
  raise CanaryProtocolError('Unknown error')
 expected={'glassly','abi','result','state','operation','phase','error','nativeStatus','mapSource','mutationStarted','restored','neighborVerified','device','offset','neighbor','sectorBytes'}
 if set(r)!=expected:raise CanaryProtocolError('Unexpected fields')
 for key,low,high in (('operation',0,2),('phase',0,8),('mapSource',0,2),('error',-2**31,2**31-1),('nativeStatus',-2**31,2**31-1)):
  if type(r[key]) is not int or not low<=r[key]<=high:raise CanaryProtocolError('Invalid '+key)
 for key,value in (('device',1),('offset',0x7ff000),('neighbor',0x7fe000),('sectorBytes',4096)):
  if type(r[key]) is not int or r[key]!=value:raise CanaryProtocolError('Wrong fixed target')
 for key in ('mutationStarted','restored','neighborVerified'):
  if type(r[key]) is not bool:raise CanaryProtocolError('Invalid boolean')
 state=r['state']
 if state not in ('idle','starting','running','passed','failed'):raise CanaryProtocolError('Unknown state')
 if state=='idle':
  if any(r[k] for k in ('operation','phase','error','nativeStatus','mapSource','mutationStarted','restored','neighborVerified')):raise CanaryProtocolError('Dirty idle registry')
 else:
  if not r['operation'] or not r['phase']:raise CanaryProtocolError('Missing operation')
  if state=='failed' and not r['error']:raise CanaryProtocolError('Failed without error')
  if state!='failed' and r['error']:raise CanaryProtocolError('Unexpected error')
  if state=='starting' and (r['phase']!=1 or r['mapSource'] or r['mutationStarted'] or r['restored'] or r['neighborVerified']):raise CanaryProtocolError('Dirty admission')
  if r['operation']==1 and (r['mutationStarted'] or r['restored']):raise CanaryProtocolError('Readonly operation mutated')
  if r['restored'] and not r['mutationStarted']:raise CanaryProtocolError('Restore without mutation')
  if state=='passed' and (r['phase']!=8 or not r['mapSource'] or not r['neighborVerified'] or r['nativeStatus'] or (r['operation']==2 and not(r['mutationStarted'] and r['restored']))):raise CanaryProtocolError('Incomplete success')
 return r
class _Parser:
 fragment_acks=True
 def __init__(self):self.stream=GmStream(legacy_repeat_fa=True,fragment_acks=True);self.pending=None;self.seen=False
 def begin(self,key):self.pending=key;self.seen=False
 def feed(self,data):
  messages=self.stream.feed(data)
  for m in messages:
   key=m['event'],m['service'],m['command']
   if key[1:]==(SERVICE,COMMAND) and m['tlvs']:
    if key!=self.pending or self.seen:raise CanaryProtocolError('Uncorrelated or duplicate reply')
    self.seen=True
  return messages
class CanaryClient:
 def __init__(self,transport,*,timeout=10):
  if type(timeout) not in (int,float) or not 0<timeout<=60:raise ValueError('timeout must be0..60')
  self.transport,self.timeout=transport,timeout;self.parser=_Parser();self.event=0x60;self.failed=False;self.verified=False;self.attempted=False;self.previous=None
 def verify_profile(self):
  if self.failed:raise CanaryError('Stopped after error')
  try:r=FlashReadClient(self.transport,timeout=self.timeout,profile=CANARY_PROFILE).query()
  except Exception:self.failed=True;raise
  self.verified=True;return r
 def _request(self,body,operation=None):
  if self.failed or not self.verified:raise CanaryError('Verify profile first; no recovery after an error')
  self.event=self.event%255+1;key=self.event,SERVICE,COMMAND;self.parser.begin(key)
  try:
   r=decode_reply(request_gm(_DeadlineIO(self.transport,self.timeout),self.parser,*key,tlv_bytes(body),timeout=self.timeout))
   if operation is not None and r['operation']!=operation:raise CanaryProtocolError('Start operation mismatch')
   if self.previous and self.previous['state']!='idle':
    old=self.previous
    if r['operation']!=old['operation'] or r['phase']<old['phase']:raise CanaryProtocolError('Registry regressed or rebooted')
    if old['state'] in ('passed','failed') and r!=old:raise CanaryProtocolError('Terminal registry changed')
    for k in ('mutationStarted','restored','neighborVerified'):
     if old[k] and not r[k]:raise CanaryProtocolError('Registry flag regressed')
   self.previous=r;return r
  except Exception:self.failed=True;raise
 def status(self):return self._request(b'\0')
 def _start(self,operation):
  if self.attempted or not self.previous or self.previous['state']!='idle':raise CanaryError('An observed idle registry and one explicit attempt are required')
  self.attempted=True;return self._request(struct.pack('<BI',operation,TOKEN),operation)
 def validate_worker(self):return self._start(1)
 def run_fixed_canary(self):return self._start(2)
