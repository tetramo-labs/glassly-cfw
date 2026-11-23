#!/usr/bin/env python3
"""Query graphics-runtime identity or exercise an explicitly selected draw session.

Default is passive diagnostic/stock heartbeat. --draw sends opt-in mode36 and
mode11, checks execution replies, lease expiry and allocator snapshots. It does
not claim a photographed/visually confirmed panel result.
"""
import argparse
import json
from pathlib import Path
import struct
import time

from memomind_transport import RfcommBridge,GmStream,gm_frames,await_gm,request_gm
from probe_memomind import probe
from probe_memomind_runtime import json_reply


def pattern():
    # Original G2 mode36 wire records; display spans600x350, tightshadow300bytes.
    def record(kind,color,width,*parameters):
        return bytes((kind,0,color,width))+struct.pack('<8h',*(list(parameters)+[0]*(8-len(parameters))))
    records=[record(2,15,2,20,20,560,310,16),record(5,12,0,140,175,70),
             record(4,15,3,140,175,80),record(3,8,0,280,85,230,45,8),
             record(3,12,0,280,153,180,45,8),record(3,15,0,280,221,130,45,8)]
    return bytes((36,len(records)))+b''.join(records)


def verify(transport,address,count=4,draw=False,cycles=3,hold_seconds=0):
    if not 1<=count<=32 or not 1<=cycles<=32:raise ValueError('Counts must be1..32')
    if not 0<=hold_seconds<=60:raise ValueError('Hold must be0..60 seconds')
    initial=probe(transport,address,legacy_repeat_fa=True)
    parser=GmStream(legacy_repeat_fa=True,fragment_acks=True);event=10
    def query(command,body=b''):
        nonlocal event
        event=(event+1)&255
        return json_reply(request_gm(transport,parser,event,15,command,body,timeout=10))
    def identity():
        result=query(0x7e)
        required={'glassly':'graphics-runtime','abi':1,'profile':'H001Y-1.0.3.127',
                  'width':600,'height':350,'modes':[11,36],'maxGeometryRecords':255,'tickMs':1,
                  'shapeTypes':list(range(1,14)),
                  'writableStaticBytes':0}
        if any(result.get(k)!=v for k,v in required.items()):raise RuntimeError('Unexpected graphics identity: '+repr(result))
        for field in ('freeBytesHex','lowWaterBytesHex'):
            if not isinstance(result.get(field),str) or len(result[field])!=8:raise RuntimeError('Missing allocator snapshot')
            int(result[field],16)
        return result
    def graphics(message):
        body=bytes((1,))+len(message).to_bytes(3,'big')+message
        result=query(0x7d,body)
        if result.get('glassly')!='graphics' or result.get('abi')!=1:raise RuntimeError('Unexpected execution reply')
        return result
    caps_before=query(0x20)
    snapshots=[identity() for _ in range(count)];sessions=[]
    if draw:
        for i in range(cycles):
            before=identity();result=graphics(pattern())
            if result.get('result')!='ok':raise RuntimeError('Draw rejected: '+repr(result))
            active=identity()
            renewals=0
            if i==0 and hold_seconds:
                deadline=time.monotonic()+hold_seconds
                while time.monotonic()<deadline:
                    time.sleep(.4)
                    renewed=graphics(bytes((36,0)))
                    if renewed.get('result')!='ok':raise RuntimeError('Lease renewal failed: '+repr(renewed))
                    renewals+=1
            if i%2:
                # No request refreshes this lease: expiry is driven by stock UI timer.
                time.sleep(1.3)
                release={'result':'lease-wait'}
            else:
                time.sleep(.25)
                release=graphics(bytes((11,)))
                if release.get('result')!='cleared':raise RuntimeError('Clear failed: '+repr(release))
            after=identity()
            sessions.append({'before':before,'execution':result,'active':active,'lease_renewals':renewals,
                             'release':release,'after':after})
    caps_after=query(0x20)
    if caps_before!=caps_after:raise RuntimeError('Stock capabilities changed')
    transport.write(gm_frames(0xf0,1,1)[0])
    heartbeat=await_gm(transport,parser,0xf0,1,1)
    if heartbeat['tlvs']!=[(6,b'\x00')]:raise RuntimeError('Final heartbeat failed')
    return {'device':initial['device'],'snapshots':snapshots,'sessions':sessions,
            'stock_capabilities_unchanged':True,'heartbeat':0,
            'visual_confirmation':False,'allocator_snapshots_are_not_leak_proof':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address',required=True);p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=38741);p.add_argument('--count',type=int,default=4)
    p.add_argument('--draw',action='store_true');p.add_argument('--cycles',type=int,default=3)
    p.add_argument('--hold-seconds',type=float,default=0,help='Renew first pattern lease for0..60 seconds')
    p.add_argument('--trace',type=Path,required=True);args=p.parse_args()
    with args.trace.open('x') as trace:
        def record(row):trace.write(json.dumps(row)+'\n');trace.flush()
        with RfcommBridge(args.host,args.port,trace=record) as transport:
            result=verify(transport,args.address,args.count,args.draw,args.cycles,args.hold_seconds)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
