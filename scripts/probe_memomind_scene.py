#!/usr/bin/env python3
"""Scene identity query, explicit smoke session, or preflighted fixture replay.

Default only queries identity after stock heartbeat/device-info. --smoke or
--fixture opts into display/cache mutation and ends with mode11 clear on success.
Failure stops immediately; cleanup/recovery is explicit, never an ambiguous retry.
No reported reply proves a visible pixel. Fixtures preserve640x480 coordinates
and require --clip-fixture to crop to600x350; pixel probes remain unverified.
"""
import argparse
import hashlib
import json
from pathlib import Path

from memomind_transport import RfcommBridge
from probe_memomind import probe
from memomind_scene import SceneClient, SceneProtocolError, parse_fixture, replay_fixture


def smoke(client,hold_ms=0):
    replies=[client.reset(),client.put_rectangle(),client.show(),client.state()]
    if replies[-1].status!=5:
        client.failed=True
        raise SceneProtocolError('Smoke STATE did not report unchanged current revision')
    if hold_ms:client.wait(hold_ms)
    cleared=client.clear()
    return {'steps':[r.as_dict() for r in replies],'clear':cleared,
            'settled_notifications':client.drain_notifications(),
            'rectangle':{'x':40,'y':40,'width':200,'height':80,'radius':8,'gray':15},
            'visual_confirmation':False}


def verify(transport,address,*,run_smoke=False,fixture_data=None,clip_fixture=False,hold_ms=0,timeout=10):
    if run_smoke and fixture_data is not None:raise ValueError('Choose smoke or fixture, not both')
    if type(hold_ms) is not int or not 0<=hold_ms<=60000 or (hold_ms and not run_smoke):raise ValueError('Hold requires smoke and0..60000ms')
    # Full fixture structural/size validation occurs before any phone operation.
    records=None if fixture_data is None else parse_fixture(fixture_data,allow_clip=clip_fixture)
    initial=probe(transport,address,legacy_repeat_fa=True)
    client=SceneClient(transport,timeout=timeout)
    before=client.identity()
    result={'device':initial['device'],'identity_before':before,'operations':'identity-only','visual_confirmation':False}
    if run_smoke:
        result['operations']='reset-put-show-state-clear'
        result['smoke']=smoke(client,hold_ms)
    elif records is not None:
        # Revalidate against advertised capacity, without modifying coordinates.
        records=parse_fixture(fixture_data,max_message=client.message_limit,allow_clip=clip_fixture)
        if any(r['kind']=='delay' and r['milliseconds']>=400 for r in records) and client.capabilities.get('emptyGeometry')!='lease-only':
            raise SceneProtocolError('Fixture delays require advertised lease-only keepalive')
        result['operations']='fixture-replay-clear'
        result['fixture']={'sha256':hashlib.sha256(fixture_data).hexdigest(),
                           'source_dimensions':[640,480],'target_dimensions':[600,350],
                           'coordinate_policy':'preserve coordinates; clip right40/bottom130 pixels; no scaling',
                           **replay_fixture(client,records)}
        result['clear']=client.clear()
        result['settled_notifications']=client.drain_notifications()
    result['identity_after']=client.identity()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',required=True)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=38741)
    parser.add_argument('--trace',type=Path,required=True,help='New JSONL trace, exclusive creation')
    parser.add_argument('--timeout',type=float,default=10,help='Total deadline per request, max60s')
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--smoke',action='store_true')
    selection.add_argument('--fixture',type=Path)
    parser.add_argument('--clip-fixture',action='store_true')
    parser.add_argument('--hold-ms',type=int,default=0,help='Smoke display hold with lease-only keepalive,0..60000ms')
    args=parser.parse_args()
    if not 0<=args.hold_ms<=60000 or (args.hold_ms and not args.smoke):parser.error('--hold-ms requires --smoke and0..60000')
    if args.clip_fixture and not args.fixture:parser.error('--clip-fixture requires --fixture')
    if not 0<args.timeout<=60:parser.error('--timeout must be positive and<=60')
    data=args.fixture.read_bytes() if args.fixture else None
    if data is not None:parse_fixture(data,allow_clip=args.clip_fixture)
    with args.trace.open('x') as trace:
        def record(row):trace.write(json.dumps(row)+'\n');trace.flush()
        with RfcommBridge(args.host,args.port,timeout=args.timeout,trace=record) as transport:
            result=verify(transport,args.address,run_smoke=args.smoke,fixture_data=data,
                          clip_fixture=args.clip_fixture,hold_ms=args.hold_ms,timeout=args.timeout)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
