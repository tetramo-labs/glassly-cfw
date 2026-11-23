#!/usr/bin/env python3
"""Bounded MemoMind carrier for unchanged G2 modes37..41; no implicit retry.

Scene packets are one BYTES TLV on service15/command0x7d. Replies retain the
original cache bytes inside correlated JSON. This module never opens a device
itself; the caller supplies an already connected RFCOMM transport.
"""
from collections import deque
from dataclasses import dataclass, asdict
import json
import re
import struct
import time

from memomind_transport import GmStream, request_gm

SERVICE = 15
COMMAND = 0x7d
STATUS_NAMES = ('applied','stale','missing','capacity','refused','unchanged','delta','snapshot','reset')
SCENE_MODES = {11,36,37,38,39,40,41}
# GLASSLYCFW/23 and later leave out the profile, modes and emptyGeometry keys.
LEAN_REVISION = 23


class SceneError(RuntimeError):
    pass


class SceneProtocolError(SceneError):
    pass


class SceneNativeError(SceneError):
    def __init__(self, reply):
        self.reply = reply
        super().__init__('Native graphics/scene request rejected: '+repr(reply))


class SceneStatusError(SceneError):
    def __init__(self, reply):
        self.reply = reply
        super().__init__(f'Scene {reply.status_name}: mode={reply.mode}, request={reply.request}, epoch={reply.epoch}, extra={reply.extra.hex()}')


def uint(value, bits, name):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'{name} must be an unsigned{bits}-bit integer')
    return value


def tlv_bytes(value):
    value = bytes(value)
    return b'\x01'+len(value).to_bytes(3,'big')+value


def decode_json(message):
    values=[v for k,v in message['tlvs'] if k==5]
    if len(values)!=1 or len(message['tlvs'])!=1:
        if message['tlvs'] and all(k==6 for k,_ in message['tlvs']):
            raise SceneNativeError({'status_tlvs':[v.hex() for _,v in message['tlvs']]})
        raise SceneProtocolError('Expected one JSON response TLV')
    try:
        result=json.loads(values[0].decode('utf-8').rstrip('\0'))
    except (UnicodeError,ValueError) as exc:
        raise SceneProtocolError('Malformed JSON response') from exc
    if not isinstance(result,dict):
        raise SceneProtocolError('Expected JSON response object')
    return result


@dataclass(frozen=True)
class SceneReply:
    mode: int
    request: int
    status: int
    epoch: int
    revision: int
    extra: bytes

    @property
    def status_name(self):
        return STATUS_NAMES[self.status]

    def as_dict(self):
        return {**asdict(self),'status_name':self.status_name,'extra':self.extra.hex()}


def parse_reply(raw):
    raw=bytes(raw)
    if not 10<=len(raw)<=255:
        raise SceneProtocolError('Scene reply length outside10..255')
    mode,request,status,epoch,revision=struct.unpack('<BHBHI',raw[:10])
    if mode not in range(37,42) or status>=len(STATUS_NAMES) or epoch==0:
        raise SceneProtocolError('Invalid scene reply mode/status/epoch')
    extra=raw[10:]
    if status==0:
        valid=len(extra) in ((1,3) if mode==41 else (1,))
    elif status in (1,5,8):
        valid=not extra
    elif status==2:
        valid=len(extra)>=2 and extra[0]<=16 and extra[1]<=1 and len(extra)==2+4*extra[0]
    elif status in (3,4):
        valid=len(extra)==1 and (status!=4 or 1<=extra[0]<=10)
    elif status==6:
        valid=mode==40 and len(extra)>=1 and len(extra)==1+9*extra[0]
        if valid:valid=all(extra[1+9*i]<=1 for i in range(extra[0]))
    else:
        valid=mode==40 and len(extra)>=5 and len(extra)==5+13*extra[4]
        if valid:
            total,page,count=struct.unpack('<HHB',extra[:5])
            valid=page==request and count<=total and all(extra[5+13*i]<=1 for i in range(count))
    if status in (5,8) and mode!=40:valid=False
    if not valid:raise SceneProtocolError('Malformed status-specific scene reply')
    return SceneReply(mode,request,status,epoch,revision,extra)


class _SceneParser:
    """Filter settled before await_gm can replace a same-event response with it."""
    fragment_acks=True

    def __init__(self, notifications):
        self.parser=GmStream(legacy_repeat_fa=True,fragment_acks=True)
        self.notifications=notifications
        self.pending=None
        self.business_seen=False

    def begin(self,key):
        self.pending=key
        self.business_seen=False

    def feed(self,data):
        result=[]
        for message in self.parser.feed(data):
            key=(message['event'],message['service'],message['command'])
            if key[1:]==(SERVICE,COMMAND) and message['tlvs']:
                reply=decode_json(message)
                if reply.get('glassly')=='scene' and reply.get('result')=='settled':
                    if type(reply.get('abi')) is not int or reply.get('abi')!=1 or type(reply.get('tag')) is not int or not 0<=reply['tag']<=65535:
                        raise SceneProtocolError('Malformed settled notification')
                    if len(self.notifications)>=256:
                        raise SceneProtocolError('Settled notification queue full; drain it explicitly')
                    self.notifications.append({'event':key[0],'tag':reply['tag']})
                    continue
                if key!=self.pending:
                    raise SceneProtocolError('Uncorrelated scene business response')
            if key==self.pending and message['tlvs']:
                if self.business_seen:raise SceneProtocolError('Duplicate correlated business response')
                self.business_seen=True
            result.append(message)
        return result


class _DeadlineIO:
    def __init__(self, io, timeout):
        self.io=io
        self.deadline=time.monotonic()+timeout

    def remaining(self):
        left=self.deadline-time.monotonic()
        if left<=0:raise TimeoutError('Scene request total deadline expired; delivery is ambiguous')
        return left

    def write(self,data):
        left=self.remaining()
        old=getattr(self.io,'timeout',None)
        try:
            if old is not None:self.io.timeout=min(old,left)
            self.io.write(data)
        finally:
            if old is not None:self.io.timeout=old
        self.remaining()

    def read(self,timeout):
        return self.io.read(min(timeout,self.remaining()))


class SceneClient:
    """One sequential owner. Any delivery/protocol/status error poisons the client.

    Explicitly construct a new client/session to recover; no request is retried.
    Notification polling is incidental to responses, not a guarantee of settled
    delivery without another read. Pixel/visual output cannot be verified by this
    response protocol.
    """
    def __init__(self, transport, *, timeout=10, capabilities=None):
        if not 0<timeout<=60:raise ValueError('timeout must be0..60 seconds')
        self.transport=transport
        self.timeout=timeout
        self.notifications=deque()
        self.parser=_SceneParser(self.notifications)
        self.event=0x30
        self.request_id=0
        self.epoch=None
        self.revision=None
        self.failed=False
        self.capabilities=None
        self.message_limit=None
        if capabilities is not None:self.set_capabilities(capabilities)

    def set_capabilities(self,value):
        required={'glassly':'graphics-runtime','abi':1,'width':600,'height':350}
        if any(value.get(k)!=v for k,v in required.items()) or type(value.get('abi')) is not int:
            raise SceneProtocolError('Unexpected scene runtime identity')
        version=value.get('version')
        lean=isinstance(version,str) and re.fullmatch('GLASSLYCFW/[0-9]{1,5}',version) is not None and int(version[11:])>=LEAN_REVISION
        if value.get('profile','H001Y-1.0.3.127' if lean else None)!='H001Y-1.0.3.127':
            raise SceneProtocolError('Unexpected scene runtime identity')
        modes=value.get('modes')
        if not (lean and modes is None) and (not isinstance(modes,list) or not all(type(m) is int for m in modes) or not SCENE_MODES.issubset(modes)):
            raise SceneProtocolError('Runtime does not advertise scene modes')
        # One request carries at most the wire limit; maxMessageBytes counts mode-127 assembly.
        maximum=value.get('maxWireMessageBytes',value.get('maxMessageBytes'))
        if type(maximum) is not int or not 9<=maximum<=65535:
            raise SceneProtocolError('Missing bounded message size capability')
        if type(value.get('storeKiB')) is not int or not 64<=value['storeKiB']<=256:
            raise SceneProtocolError('Missing bounded scene store capacity')
        self.capabilities=dict(value)
        if lean:self.capabilities.setdefault('emptyGeometry','lease-only')
        self.message_limit=maximum

    def _json_request(self,command,body=b''):
        if self.failed:raise SceneError('Client stopped after prior failure; no automatic recovery')
        self.event=self.event%255+1
        key=(self.event,SERVICE,command)
        self.parser.begin(key)
        try:
            result=request_gm(_DeadlineIO(self.transport,self.timeout),self.parser,*key,body,timeout=self.timeout)
            return decode_json(result)
        except Exception:
            self.failed=True
            raise
        finally:
            self.parser.pending=None

    def identity(self):
        value=self._json_request(0x7e)
        try:self.set_capabilities(value)
        except Exception:self.failed=True;raise
        return value

    def _ready(self):
        if self.failed:raise SceneError('Client stopped after prior failure; no automatic recovery')
        if self.capabilities is None:raise SceneError('Query or validate runtime capabilities first')

    def _request(self):
        if self.request_id==65535:raise SceneError('Request sequence exhausted; establish a new scene session')
        self.request_id+=1
        return self.request_id

    def drain_notifications(self):
        result=list(self.notifications)
        self.notifications.clear()
        return result

    def transact(self,message,*,allowed=(0,)):
        self._ready()
        message=bytes(message)
        if not 5<=len(message)<=self.message_limit or message[0] not in range(37,42):
            raise ValueError('Scene packet outside supported mode/advertised size')
        mode=message[0]
        if mode==40 and len(message)!=9:raise ValueError('STATE packet must be9 bytes')
        epoch=int.from_bytes(message[1:3],'little')
        request=int.from_bytes(message[7:9] if mode==40 else message[3:5],'little')
        reset=mode==41 and len(message)>=6 and message[5]==0
        if self.epoch is not None and epoch!=self.epoch and not reset and not (mode==40 and epoch==0):
            raise ValueError('Outgoing scene epoch does not match this client')
        if epoch==0 and not reset and mode!=40:raise ValueError('Zero epoch only allowed for RESET/STATE')
        value=self._json_request(COMMAND,tlv_bytes(message))
        try:
            if value.get('glassly')!='scene' or type(value.get('abi')) is not int or value.get('abi')!=1 or value.get('result')!='ok':
                raise SceneNativeError(value)
            hex_reply=value.get('replyHex')
            if not isinstance(hex_reply,str) or len(hex_reply)%2 or not re.fullmatch('[0-9a-fA-F]+',hex_reply):
                raise SceneProtocolError('Malformed replyHex')
            reply=parse_reply(bytes.fromhex(hex_reply))
            if (reply.mode,reply.request)!=(mode,request):raise SceneProtocolError('Scene mode/request correlation mismatch')
            if reply.status==1:raise SceneStatusError(reply)
            if epoch and reply.epoch!=epoch:raise SceneProtocolError('Scene epoch correlation mismatch')
            if reply.status not in allowed:raise SceneStatusError(reply)
            if reset and (reply.status!=0 or len(reply.extra)!=3):raise SceneProtocolError('RESET reply missing store size')
            if not reset and reply.status==0 and len(reply.extra)!=1:raise SceneProtocolError('Unexpected APPLIED extra fields')
            if reset and int.from_bytes(reply.extra[1:],'little')!=self.capabilities['storeKiB']:
                raise SceneProtocolError('RESET store size differs from advertisement')
            self.epoch=reply.epoch
            self.revision=reply.revision
            return reply
        except Exception:
            self.failed=True
            raise

    def reset(self,epoch=0):
        uint(epoch,16,'epoch')
        message=bytes([41])+struct.pack('<HHBB',epoch,self._request(),0,250)
        return self.transact(message)

    def _header(self,mode):
        if self.epoch is None:raise SceneError('RESET or STATE discovery required')
        return bytes([mode])+struct.pack('<HH',self.epoch,self._request())

    def put_rectangle(self,object_id=1,version=1,*,x=40,y=40,width=200,height=80,color=15,radius=8):
        uint(object_id,32,'object id');uint(version,31,'version');uint(color,4,'color')
        if not object_id or object_id==0xffffffff or not version:raise ValueError('Reserved object id/version')
        for name,value in [('x',x),('y',y),('width',width),('height',height),('radius',radius)]:
            if type(value) is not int or not -32768<=value<=32767:raise ValueError(name+' outside signed16')
        if width<0 or height<0 or radius<0:raise ValueError('Rectangle dimensions must be nonnegative')
        record=bytes((3,1,color,0))+struct.pack('<8h',x,y,width,height,radius,0,0,0)
        return self.transact(self._header(37)+b'\x01'+struct.pack('<II',object_id,version)+record)

    def show(self,references=((1,1),),*,background=0,tag=True):
        uint(background,4,'background')
        refs=list(references)
        if len(refs)>256:raise ValueError('Too many active references')
        for ident,version in refs:
            uint(ident,32,'object id');uint(version,31,'version')
            if not ident or ident==0xffffffff or not version:raise ValueError('Reserved reference')
        return self.transact(self._header(38)+bytes((1|(4 if tag else 0),background,0))+struct.pack('<H',len(refs))+b''.join(struct.pack('<II',*r) for r in refs))

    def state(self,*,discover=False,revision=None,page=0):
        uint(page,16,'page')
        if self.epoch is None and not discover:raise SceneError('STATE requires epoch or explicit discovery')
        if revision is None:revision=0 if discover else (self.revision or 0)
        uint(revision,32,'revision')
        return self.transact(bytes((40,))+struct.pack('<HIH',0 if discover else self.epoch,revision,page),allowed=(5,6,7,8))

    def graphics(self,message,expected):
        self._ready()
        value=self._json_request(COMMAND,tlv_bytes(message))
        if value.get('glassly')!='graphics' or type(value.get('abi')) is not int or value.get('abi')!=1 or value.get('result')!=expected:
            self.failed=True
            raise SceneNativeError(value)
        return value

    def keepalive(self):
        self._ready()
        if self.capabilities.get('emptyGeometry')!='lease-only':
            raise SceneError('Runtime has not advertised non-takeover empty geometry')
        return self.graphics(bytes((36,0)),'ok')

    def clear(self):
        result=self.graphics(bytes((11,)),'cleared')
        self.epoch=None
        self.revision=None
        return result

    def wait(self,milliseconds):
        self._ready()
        uint(milliseconds,32,'delay')
        if milliseconds>60000:raise ValueError('Delay exceeds60000ms')
        if milliseconds>=400 and self.capabilities.get('emptyGeometry')!='lease-only':
            raise SceneError('Cannot preserve scene lease across this delay')
        end=time.monotonic()+milliseconds/1000
        renewal=time.monotonic()+.35
        while time.monotonic()<end:
            time.sleep(min(.1,max(0,end-time.monotonic())))
            if time.monotonic()>=renewal and time.monotonic()<end:
                self.keepalive();renewal=time.monotonic()+.35


def parse_fixture(data,*,max_message=8192,allow_clip=False,source_size=(640,480),target_size=(600,350)):
    """Strict offline preflight. Coordinates are preserved, never rescaled.

    Pixel records are observations requiring visual/framebuffer capture, not
    device assertions supported by this client. Cropping requires explicit opt-in.
    """
    if type(max_message) is not int or not 9<=max_message<=65535:raise ValueError('Invalid fixture message bound')
    if len(data)>64*1024*1024:raise ValueError('Fixture exceeds64MiB')
    if source_size!=target_size and not allow_clip:
        raise ValueError('Fixture640x480 differs from600x350; explicit clipping opt-in required')
    records=[];pos=0
    while pos<len(data):
        kind=data[pos];pos+=1
        def take(n):
            nonlocal pos
            if n>len(data)-pos:raise ValueError('Truncated fixture')
            value=data[pos:pos+n];pos+=n;return value
        if kind==1:
            length=int.from_bytes(take(2),'little');message=take(length)
            if not 5<=length<=max_message or message[0] not in range(37,42):raise ValueError('Unsupported/oversized fixture message')
            if message[0]==40 and length!=9:raise ValueError('Malformed fixture STATE')
            if message[0]==41 and length<6:raise ValueError('Malformed fixture CONTROL')
            if int.from_bytes(message[1:3],'little')!=0:raise ValueError('Fixture must use placeholder epoch0')
            if message[0]!=40 and int.from_bytes(message[3:5],'little')!=0:raise ValueError('Fixture must use placeholder request0')
            records.append({'kind':'message','message':message})
        elif kind==2:
            delay=int.from_bytes(take(4),'little')
            if delay>60000:raise ValueError('Fixture delay exceeds60000ms')
            records.append({'kind':'delay','milliseconds':delay})
        elif kind==3:
            label=take(take(1)[0]).decode('utf-8','replace')
            records.append({'kind':'label','label':label})
        elif kind==4:
            x,y,color=struct.unpack('<HHB',take(5))
            if x>=source_size[0] or y>=source_size[1] or color>15:raise ValueError('Invalid source pixel probe')
            records.append({'kind':'pixel','x':x,'y':y,'color':color,'clipped':x>=target_size[0] or y>=target_size[1]})
        elif kind==5:records.append({'kind':'snapshot'})
        else:raise ValueError('Unknown fixture record kind')
    return records


def replay_fixture(client,records):
    """Execute preflighted cache messages. Pixel expectations stay unverified."""
    replies=[];probes=[];label='fixture';snapshots=0
    for record in records:
        kind=record['kind']
        if kind=='message':
            raw=bytearray(record['message']);mode=raw[0]
            reset=mode==41 and raw[5]==0
            if mode==40:
                if int.from_bytes(raw[1:3],'little')==0 and client.epoch is not None:raw[1:3]=struct.pack('<H',client.epoch)
                allowed=(5,6,7,8)
            else:
                if not reset and client.epoch is None:raise SceneError('Fixture needs RESET before mutations')
                raw[1:3]=struct.pack('<H',0 if reset else client.epoch)
                raw[3:5]=struct.pack('<H',client._request())
                allowed=(0,)
            replies.append({'label':label,**client.transact(raw,allowed=allowed).as_dict()})
        elif kind=='delay':client.wait(record['milliseconds'])
        elif kind=='label':label=record['label']
        elif kind=='pixel':probes.append({'label':label,**record,'verified':False})
        elif kind=='snapshot':snapshots+=1
        else:raise ValueError('Unrecognized preflighted record')
    return {'replies':replies,'pixel_expectations':probes,'snapshot_requests_unavailable':snapshots,
            'visual_confirmation':False,'pixel_probes_verified':0}
