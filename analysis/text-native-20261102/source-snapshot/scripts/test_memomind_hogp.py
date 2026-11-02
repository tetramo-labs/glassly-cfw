from collections import deque
import json
import unittest

from memomind_hogp import (HogpClient, HogpError, HogpProtocolError, HogpNativeError,
                           decode, json_tlv)
from memomind_transport import gm_frames, parse_tlvs


def packet(event, command, tlvs):
    body=b''.join(bytes([kind])+len(data).to_bytes(3,'big')+data for kind,data in tlvs)
    return b''.join(gm_frames(event,16,command,body))


class Fake:
    timeout=10
    def __init__(self):
        self.reads=deque();self.requests=[];self.extra=b'';self.drop=False
        self.edit=None;self.duplicate=False;self.event_delta=0;self.reject=False

    def write(self, frame):
        assert frame[0]==250 and len(frame)==int.from_bytes(frame[1:4],'big')
        assert sum(frame[:-2])&65535==int.from_bytes(frame[-2:],'big')
        event,service,command=frame[4:7];assert service==16
        tlvs=parse_tlvs(frame[7:-2]);meta=json.loads(tlvs[0][1]);self.requests.append((command,meta,tlvs))
        op=meta['op']
        if self.reject:reply=[(6,b'\x01'),(2,b'ERR_GATT_BUSY')]
        elif op in ('query_cap','query_status','enable_hid_event'):
            value={'proto':1,'scan':True} if op=='query_cap' else ({'state':0,'connected':0,'bonded':0} if op=='query_status' else {'enable':True,'raw':True,'rate_hz':10})
            if self.edit:value=self.edit(value)
            reply=[(5,json.dumps(value).encode())]
        else:reply=[(6,b'\0')]
        response=packet((event+self.event_delta)&255,command,reply)
        if self.duplicate:response+=response
        if not self.drop:self.reads.append(self.extra+response)

    def read(self, timeout):
        if not self.reads:raise TimeoutError('idle')
        return self.reads.popleft()


class HogpTests(unittest.TestCase):
    def test_constructor_and_query_are_passive(self):
        io=Fake();client=HogpClient(io);self.assertEqual(io.requests,[])
        self.assertTrue(client.control('query_cap')['json']['scan'])
        self.assertEqual(client.control('query_status')['json']['state'],0)
        self.assertEqual([r[1]['op'] for r in io.requests],['query_cap','query_status'])

    def test_async_before_ack_is_not_completion(self):
        io=Fake();client=HogpClient(io)
        event={'seq':0,'scan_id':9,'state':'scanning','reason':0}
        io.extra=packet(145,9,[(5,json.dumps(event).encode())])
        self.assertEqual(client.control('scan_start',duration_ms=1000),{'kind':'ack','status':0})
        events=client.drain_events();self.assertEqual(events[0]['command'],9)
        self.assertEqual(events[0]['json'],event)
        self.assertEqual(client.drain_events(),[]);self.assertEqual(client.event_bytes,0)

    def test_fragmented_json_preserved(self):
        io=Fake();client=HogpClient(io);io.edit=lambda r:{**r,'padding':'x'*2000}
        self.assertEqual(len(client.control('query_cap')['json']['padding']),2000)

    def test_gatt_ack_and_async_result_use_distinct_identifiers(self):
        io=Fake();client=HogpClient(io)
        result={'seq':12,'event':'read_result','list_id':2,'value_handle':37,'att_err':0}
        io.extra=packet(240,4,[(5,json.dumps(result).encode()),(1,b'\x01\x02')])
        reply=client.gatt('read',seq=12,list_id=2,value_handle=37)
        self.assertEqual(reply['kind'],'ack')
        event=client.drain_events()[0];self.assertEqual(event['event'],240)
        self.assertEqual(event['json']['seq'],12);self.assertEqual(event['data_hex'],'0102')

    def test_write_uses_bytes_tlv_and_native_limit(self):
        io=Fake();client=HogpClient(io)
        client.gatt('write',seq=3,list_id=2,value_handle=37,data=b'\0'*64)
        self.assertEqual(io.requests[0][2][1],(1,b'\0'*64))
        with self.assertRaises(ValueError):client.gatt('write',seq=4,list_id=2,value_handle=37,data=b'\0'*65)
        self.assertEqual(len(io.requests),1)

    def test_subscribe_requires_explicit_handles_and_type(self):
        io=Fake();client=HogpClient(io)
        with self.assertRaises(ValueError):client.gatt('subscribe',seq=1,list_id=1,value_handle=37)
        client.gatt('subscribe',seq=1,list_id=1,value_handle=37,cccd_handle=38,subscribe_type='notify')
        self.assertEqual(io.requests[-1][1]['cccd_handle'],38)
        client.gatt('unsubscribe',seq=2,list_id=1,value_handle=37,cccd_handle=38)
        self.assertNotIn('subscribe_type',io.requests[-1][1])

    def test_invalid_control_never_sent(self):
        io=Fake();client=HogpClient(io)
        for op,fields in [('scan_start',{}),('scan_start',{'duration_ms':0}),('scan_start',{'duration_ms':True}),
                          ('query_cap',{'enable':True}),('enable_hid_event',{'enable':1}),
                          ('connect',{'addr':'bad','addr_type':0}),('connect',{'addr':'AA:BB:CC:DD:EE:FF','addr_type':-1}),
                          ('unknown',{})]:
            with self.assertRaises(ValueError):client.control(op,**fields)
        self.assertEqual(io.requests,[])
        with self.assertRaises(ValueError):json_tlv({'op':'connect','name':'é'*255})

    def test_native_error_poisoned_and_never_retried(self):
        io=Fake();client=HogpClient(io);io.reject=True
        with self.assertRaises(HogpNativeError) as raised:client.control('scan_start',duration_ms=1000)
        self.assertEqual(raised.exception.token,'ERR_GATT_BUSY')
        with self.assertRaises(HogpError):client.control('query_status')
        self.assertEqual(len(io.requests),1)

    def test_request_timeout_is_ambiguous(self):
        io=Fake();client=HogpClient(io);io.drop=True
        with self.assertRaises(TimeoutError):client.control('connect',addr='AA:BB:CC:DD:EE:FF',addr_type=1)
        self.assertTrue(client.failed);self.assertEqual(len(io.requests),1)

    def test_duplicate_and_wrong_event_fail(self):
        for key in ('duplicate','event_delta'):
            io=Fake();client=HogpClient(io);setattr(io,key,1)
            with self.assertRaises(HogpProtocolError):client.control('query_status')
            self.assertTrue(client.failed)

    def test_idle_read_retains_raw_hid_and_zero_fields(self):
        io=Fake();client=HogpClient(io)
        raw={'type':'hid_raw','rid':1,'len':8}
        key={'type':'hid_key','key':0,'phase':0,'val':0,'page':7,'usage':82}
        io.reads.append(packet(12,6,[(5,json.dumps(raw).encode()),(1,b'\0'*8)])+
                        packet(13,6,[(5,json.dumps(key).encode())]))
        events=client.read_events(.1);self.assertEqual(len(events),2)
        self.assertEqual(events[0]['data_hex'],'00'*8);self.assertEqual(events[1]['json']['key'],0)
        self.assertFalse(client.failed)

    def test_bad_raw_length_poisoned(self):
        io=Fake();client=HogpClient(io)
        io.reads.append(packet(1,6,[(5,b'{"type":"hid_raw","rid":1,"len":8}'),(1,b'\0')]))
        with self.assertRaises(HogpProtocolError):client.read_events(.1)
        self.assertTrue(client.failed)

    def test_queue_count_and_byte_bounds_are_errors(self):
        for bodies in ([b'{}']*257,[json.dumps({'padding':'x'*2000}).encode()]*140):
            io=Fake();client=HogpClient(io)
            io.reads.append(b''.join(packet(i%255,2,[(5,b)]) for i,b in enumerate(bodies)))
            with self.assertRaises(HogpProtocolError):client.read_events(.1)
            self.assertTrue(client.failed)

    def test_strict_tlv_and_json_decoding(self):
        invalid=[[],[(5,b'[]')],[(5,b'{"x":1,"x":2}')],[(6,b'')],[(6,b'\0'),(2,b'error')],
                 [(5,b'{}'),(5,b'{}')],[(5,b'{}'),(1,b'x'*8193)]]
        for tlvs in invalid:
            with self.assertRaises(HogpProtocolError):decode({'tlvs':tlvs})


if __name__=='__main__':unittest.main()
