#!/usr/bin/env python3
"""Live bounded graphics regression: malformed requests, max records, clear.

This sends drawing commands on the connected owned glasses. No OTA or permanent
configuration change. Every draw has the firmware's1s lease, plus explicit clear.
"""
import argparse
import json
from pathlib import Path
import struct
import time
from memomind_transport import RfcommBridge,GmStream,gm_frames,await_gm,request_gm
from probe_memomind import probe
from probe_memomind_runtime import json_reply


def exercise(transport,address):
    device=probe(transport,address,legacy_repeat_fa=True)['device']
    parser=GmStream(legacy_repeat_fa=True,fragment_acks=True);event=30;cases=[]
    def tlv(data):return bytes((1,))+len(data).to_bytes(3,'big')+data
    def call(label,body,expected,command=0x7d):
        nonlocal event
        event+=1;frames=gm_frames(event,15,command,body,fragment_payload=642);start=time.monotonic()
        result=json_reply(request_gm(transport,parser,event,15,command,body))
        if expected is not None and result.get('result')!=expected:
            raise RuntimeError(label+': '+repr(result))
        cases.append({'name':label,'frames':len(frames),'bytes':len(body),
                      'result':result,'elapsed_ms':round((time.monotonic()-start)*1000,2)})
        return result
    identity=call('identity_before',b'',None,0x7e)
    if identity.get('glassly')!='graphics-runtime':raise RuntimeError('Graphics runtime required')
    call('empty_geometry',tlv(bytes((36,0))),'ok')
    call('truncated_count',tlv(bytes((36,))),'invalid')
    one=bytes((36,1,1,0,15,0))+struct.pack('<8h',20,20,20,20,0,0,0,0)
    call('unsupported_shape',tlv(one[:2]+bytes((14,))+one[3:]),'invalid')
    call('trailing_byte',tlv(one+b'\0'),'invalid')
    call('extra_nonempty_tlv',tlv(one)+bytes.fromhex('0800000101'),'invalid')
    many=bytearray((36,255))
    for i in range(255):
        many+=bytes((1,0,1+i%15,0))+struct.pack('<8h',i,100,i,100,0,0,0,0)
    call('maximum_255_records',tlv(many),'ok')
    call('explicit_clear',tlv(bytes((11,))),'cleared')
    after=call('identity_after',b'',None,0x7e)
    transport.write(gm_frames(0xf1,1,1)[0])
    heartbeat=await_gm(transport,parser,0xf1,1,1)
    if heartbeat['tlvs']!=[(6,b'\0')]:raise RuntimeError('Heartbeat failed')
    return {'device':device,'cases':cases,'heartbeat':0,'identity_after':after,
            'hardware_execution_replies':True,'physical_display_confirmation':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address',required=True);p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=38741);p.add_argument('--trace',type=Path,required=True)
    a=p.parse_args()
    with a.trace.open('x') as trace:
        def record(row):trace.write(json.dumps(row)+'\n');trace.flush()
        with RfcommBridge(a.host,a.port,trace=record) as t:result=exercise(t,a.address)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
