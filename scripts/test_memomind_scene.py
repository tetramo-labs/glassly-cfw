import json
import struct
import unittest
from collections import deque
from unittest.mock import patch

from memomind_transport import gm_frames, parse_tlvs
from memomind_scene import (SceneClient,SceneError,SceneProtocolError,SceneNativeError,
                            SceneStatusError,parse_reply,parse_fixture,replay_fixture)
from probe_memomind_scene import smoke

CAPS={'glassly':'graphics-runtime','abi':1,'profile':'H001Y-1.0.3.127',
      'width':600,'height':350,'modes':[11,19,20,36,37,38,39,40,41],
      'maxMessageBytes':8192,'storeKiB':64,'builtinText':False,'emptyGeometry':'lease-only'}
# A lean revision 23+ build: no profile, modes or emptyGeometry; 8192-byte requests, 65535 assembled.
LEAN_CAPS={'glassly':'graphics-runtime','abi':1,'width':600,'height':350,'version':'GLASSLYCFW/27',
           'displayOwner':'minimal','maxMessageBytes':65535,'maxWireMessageBytes':8192,
           'largeMessage':{'mode':127,'chunkBytes':1024,'crc':'crc32-ieee'},'storeKiB':256,
           'freeBytesHex':'00050000','lowWaterBytesHex':'00040000'}


def json_frames(event,value,command=0x7d):
    data=json.dumps(value,separators=(',',':')).encode()
    body=b'\x05'+len(data).to_bytes(3,'big')+data
    return b''.join(gm_frames(event,15,command,body))


def cache_bytes(mode,request,status=0,epoch=0x1234,revision=1,extra=b'\0'):
    return struct.pack('<BHBHI',mode,request,status,epoch,revision)+extra


class NativeFake:
    """Independent native642-byte request assembler and503-byte reply framing."""
    timeout=20
    def __init__(self):
        self.reads=deque();self.writes=[];self.messages=[];self.body=bytearray();self.fragment=0
        self.epoch=0x1234;self.revision=0;self.notifications=True
        self.reply_edit=None;self.envelope_edit=None;self.reply_event_delta=0
        self.reject_fragment=None;self.notify_during_ack=False;self.drop=False
    def write(self,frame):
        self.writes.append(frame)
        assert sum(frame[:-2])&65535==int.from_bytes(frame[-2:],'big')
        if frame[0]==250:self.body.clear();self.fragment=0
        assert frame[0]==(250 if self.fragment==0 else self.fragment)
        total=int.from_bytes(frame[1:4],'big')-9
        assert len(frame)==min(642,total-len(self.body))+9
        event,service,command=frame[4:7];assert service==15
        self.body.extend(frame[7:-2])
        if self.reject_fragment==self.fragment:
            self.reads.append(json_frames(event,{'glassly':'graphics','abi':1,'result':'allocation-failed'}));return
        if len(self.body)<total:
            raw=bytes((frame[0],0,0,9,event,service,command));ack=raw+(sum(raw)&65535).to_bytes(2,'big')
            if self.notify_during_ack:ack=json_frames(event,{'glassly':'scene','abi':1,'result':'settled','tag':31})+ack
            self.reads.append(ack);self.fragment+=1;return
        tlvs=parse_tlvs(self.body)
        if command==0x7e:
            assert not tlvs;self.reads.append(json_frames(event,CAPS,command));return
        assert len(tlvs)==1 and tlvs[0][0]==1
        data=tlvs[0][1];self.messages.append(data)
        if self.drop:return
        if data[0] in (11,36):
            value={'glassly':'graphics','abi':1,'result':'cleared' if data[0]==11 else 'ok'}
        else:
            mode=data[0];request=int.from_bytes(data[7:9] if mode==40 else data[3:5],'little')
            if mode==41 and data[5]==0:
                self.epoch=int.from_bytes(data[1:3],'little') or 0x1234;self.revision=0;status=0;extra=b'\0\x40\0'
            elif mode==40:status=5;extra=b''
            else:
                if mode==37:self.revision+=1
                status=0;extra=b'\0'
            raw=cache_bytes(mode,request,status,self.epoch,self.revision,extra)
            if self.reply_edit:raw=self.reply_edit(raw)
            value={'glassly':'scene','abi':1,'result':'ok','replyHex':raw.hex()}
        if self.envelope_edit:value=self.envelope_edit(value)
        response=json_frames((event+self.reply_event_delta)&255,value)
        if data[0]==38 and self.notifications:
            response+=json_frames(event,{'glassly':'scene','abi':1,'result':'settled','tag':int.from_bytes(data[3:5],'little')})
        self.reads.append(response)
    def read(self,timeout):
        if not self.reads:raise TimeoutError('Fake transport exhausted deadline')
        return self.reads.popleft()


class SceneClientTests(unittest.TestCase):
    def client(self):
        fake=NativeFake();return fake,SceneClient(fake,capabilities=CAPS)
    def test_smoke_exact_wire_sequence_and_same_read_notification(self):
        fake,client=self.client();result=smoke(client)
        self.assertEqual([m[0] for m in fake.messages],[41,37,38,40,11])
        self.assertEqual(fake.messages[0],bytes.fromhex('290000010000fa'))
        self.assertEqual(fake.messages[1][:15],bytes.fromhex('253412020001010000000100000003'))
        self.assertEqual(fake.messages[2],bytes.fromhex('263412030005000001000100000001000000'))
        self.assertEqual(result['settled_notifications'],[{'event':0x33,'tag':3}])
        self.assertEqual(result['steps'][-1]['status_name'],'unchanged')
        self.assertIsNone(client.epoch);self.assertFalse(result['visual_confirmation'])
    def test_identity_and_lease_only_capability(self):
        fake=NativeFake();client=SceneClient(fake)
        self.assertEqual(client.identity(),CAPS)
        client.keepalive();self.assertEqual(fake.messages,[b'\x24\0'])
        client.capabilities.pop('emptyGeometry')
        with self.assertRaises(SceneError):client.keepalive()
        self.assertEqual(len(fake.messages),1)
    def test_fragmented8192_message_uses_native642_acks_and_filters_notifications(self):
        fake,client=self.client();client.reset();fake.notify_during_ack=True
        data=bytes((37,))+struct.pack('<HH',client.epoch,77)+bytes(8192-5)
        start=len(fake.writes);reply=client.transact(data)
        self.assertEqual(reply.request,77)
        frames=fake.writes[start:];self.assertEqual(len(frames),13)
        self.assertEqual([len(f) for f in frames[:-1]],[651]*12)
        self.assertEqual(fake.messages[-1],data)
        self.assertEqual(len(client.drain_notifications()),12)
    def test_oversize_before_any_write_and_no_automatic_chunking(self):
        fake,client=self.client()
        with self.assertRaises(ValueError):client.transact(b'\x25\x34\x12\x01\0'+bytes(8188))
        self.assertEqual(fake.writes,[])
    def test_early_native_failure_stops_fragment_stream(self):
        fake,client=self.client();fake.reject_fragment=0
        with self.assertRaises(SceneNativeError):client.transact(b'\x25\x34\x12\x01\0'+bytes(1000))
        self.assertEqual(len(fake.writes),1);self.assertTrue(client.failed)
        with self.assertRaises(SceneError):client.reset()
        self.assertEqual(len(fake.writes),1)
    def test_ambiguous_timeout_never_retries(self):
        fake,client=self.client();fake.drop=True
        with self.assertRaises(TimeoutError):client.reset()
        with self.assertRaises(SceneError):client.reset()
        self.assertEqual(len(fake.writes),1)
    def test_each_cache_failure_stops_with_original_status(self):
        for status,extra in [(1,b''),(2,b'\x01\0'+struct.pack('<I',99)),(3,b'\0'),(4,b'\x07')]:
            with self.subTest(status=status):
                fake,client=self.client();client.reset()
                fake.reply_edit=lambda raw,s=status,e=extra:cache_bytes(raw[0],int.from_bytes(raw[1:3],'little'),s,extra=e)
                with self.assertRaises(SceneStatusError) as ctx:client.put_rectangle()
                self.assertEqual(ctx.exception.reply.status,status);self.assertTrue(client.failed)
    def test_wrong_mode_request_epoch_and_event_are_rejected(self):
        edits=[lambda r:bytes((39,))+r[1:],lambda r:r[:1]+b'\xff\xff'+r[3:],lambda r:r[:4]+b'\xff\xff'+r[6:]]
        for edit in edits:
            fake,client=self.client();client.reset();fake.reply_edit=edit
            with self.assertRaises(SceneProtocolError):client.put_rectangle()
            self.assertTrue(client.failed)
        fake,client=self.client();fake.reply_event_delta=1
        with self.assertRaises(SceneProtocolError):client.reset()
    def test_reset_accepts_epoch0_result_but_requires_explicit_requested_epoch(self):
        fake,client=self.client();self.assertEqual(client.reset().epoch,0x1234)
        self.assertEqual(client.reset(42).epoch,42)
        fake.reply_edit=lambda r:r[:4]+b'\x2b\0'+r[6:]
        with self.assertRaises(SceneProtocolError):client.reset(42)
    def test_store_mismatch_and_malformed_envelope_fail_closed(self):
        fake,client=self.client();fake.reply_edit=lambda r:r[:-2]+b'\x80\0'
        with self.assertRaises(SceneProtocolError):client.reset()
        for value in [None,'00 xx','a','00 '*10]:
            fake,client=self.client();fake.envelope_edit=lambda r,v=value:{**r,'replyHex':v}
            with self.assertRaises(SceneProtocolError):client.reset()
    def test_notifications_arriving_later_are_drained_before_next_response(self):
        fake,client=self.client();client.reset()
        fake.reads.append(json_frames(7,{'glassly':'scene','abi':1,'result':'settled','tag':12}))
        self.assertEqual(client.put_rectangle().request,2)
        self.assertEqual(client.drain_notifications(),[{'event':7,'tag':12}])
    def test_bad_settled_tag_and_duplicate_business_reply_are_rejected(self):
        fake,client=self.client()
        fake.reads.append(json_frames(7,{'glassly':'scene','abi':1,'result':'settled','tag':True}))
        with self.assertRaises(SceneProtocolError):client.reset()
        fake,client=self.client()
        original=fake.write
        def duplicate(data):
            original(data)
            if fake.reads:fake.reads[-1]*=2
        fake.write=duplicate
        with self.assertRaises(SceneProtocolError):client.reset()
    def test_large_snapshot_response_reassembles503_byte_reply_fragments(self):
        fake,client=self.client();client.reset()
        entries=b''.join(struct.pack('<BIII',0,i+1,1,i) for i in range(18))
        fake.reply_edit=lambda raw:cache_bytes(40,0,7,extra=struct.pack('<HHB',18,0,18)+entries)
        reply=client.state()
        self.assertEqual(reply.status,7);self.assertEqual(len(reply.extra),239)
        self.assertEqual(reply.extra[4],18)
    def test_native_error_envelopes_are_not_cache_replies(self):
        for result in ('invalid','allocation-failed','stock-ui-active'):
            fake,client=self.client()
            fake.envelope_edit=lambda value,r=result:{'glassly':'graphics','abi':1,'result':r}
            with self.assertRaises(SceneNativeError) as error:client.reset()
            self.assertEqual(error.exception.reply['result'],result)
            self.assertTrue(client.failed)
    def test_late_same_event_notification_after_response_does_not_replace_next_reply(self):
        fake,client=self.client();client.reset();fake.notifications=False
        response=client.show()
        fake.reads.append(json_frames(client.event,{'glassly':'scene','abi':1,'result':'settled','tag':response.request}))
        state=client.state()
        self.assertEqual(state.mode,40)
        self.assertEqual(client.drain_notifications(),[{'event':0x32,'tag':2}])
    def test_notification_flood_is_bounded_and_stops_client(self):
        fake,client=self.client()
        fake.reads.append(json_frames(4,{'glassly':'scene','abi':1,'result':'settled','tag':4})*257)
        with self.assertRaises(SceneProtocolError):client.reset()
        self.assertEqual(len(client.notifications),256)
        self.assertTrue(client.failed)
    def test_request_ids_do_not_wrap_into_duplicate_show_ids(self):
        fake,client=self.client();client.request_id=65535
        with self.assertRaises(SceneError):client.reset()
        self.assertFalse(fake.writes)
    def test_total_deadline_restores_transport_timeout(self):
        fake,client=self.client()
        with patch('memomind_scene.time.monotonic',side_effect=[0,11]):
            with self.assertRaises(TimeoutError):client.reset()
        self.assertEqual(fake.timeout,20);self.assertFalse(fake.writes)
    def test_capability_rejections_do_not_send_mutations(self):
        for update in [{'modes':[11,36]},{'maxMessageBytes':0},{'maxMessageBytes':True},{'storeKiB':32},{'width':640}]:
            fake=NativeFake()
            with self.assertRaises(SceneProtocolError):SceneClient(fake,capabilities={**CAPS,**update})
            self.assertFalse(fake.writes)
        for caps in [{k:v for k,v in CAPS.items() if k!='modes'},{k:v for k,v in CAPS.items() if k!='profile'},
                     {**LEAN_CAPS,'version':'GLASSLYCFW/22'},{**LEAN_CAPS,'profile':'H001Y-other'},{**LEAN_CAPS,'modes':[11,36]},
                     {**LEAN_CAPS,'maxWireMessageBytes':70000},{k:v for k,v in LEAN_CAPS.items() if k!='storeKiB'}]:
            fake=NativeFake()
            with self.assertRaises(SceneProtocolError):SceneClient(fake,capabilities=caps)
            self.assertFalse(fake.writes)
    def test_lean_builds_are_accepted_and_bounded_by_the_wire_limit(self):
        fake=NativeFake();client=SceneClient(fake,capabilities=LEAN_CAPS)
        self.assertEqual(client.message_limit,8192)
        client.keepalive();self.assertEqual(fake.messages,[b'\x24\0'],'lean scene builds keep lease-only empty geometry')
        with self.assertRaises(ValueError):client.transact(bytes((37,))+bytes(8192))
        self.assertEqual(len(fake.messages),1,'a request over the wire limit is refused before sending')
        self.assertEqual(SceneClient(NativeFake(),capabilities={**CAPS,'maxWireMessageBytes':4096}).message_limit,4096)
        self.assertEqual(SceneClient(NativeFake(),capabilities=CAPS).message_limit,8192)


class ReplyAndFixtureTests(unittest.TestCase):
    def test_all_state_reply_shapes(self):
        for status,extra in [(5,b''),(6,b'\x01'+struct.pack('<BII',0,1,2)),
                             (7,struct.pack('<HHB',1,0,1)+struct.pack('<BIII',0,1,2,3)),(8,b'')]:
            self.assertEqual(parse_reply(cache_bytes(40,0,status,extra=extra)).status,status)
        for raw in [b'',cache_bytes(40,0,9),cache_bytes(40,0,7,extra=b'\0'*5+b'\0'),cache_bytes(40,0,6,extra=b'\x02')]:
            with self.assertRaises(SceneProtocolError):parse_reply(raw)
    def test_fixture_clipping_and_pixel_probes_are_explicitly_unverified(self):
        reset=bytes.fromhex('290000000000')
        data=b'\x01'+struct.pack('<H',len(reset))+reset+b'\x04'+struct.pack('<HHB',639,479,15)+b'\x05'
        with self.assertRaises(ValueError):parse_fixture(data)
        records=parse_fixture(data,allow_clip=True)
        self.assertTrue(records[1]['clipped'])
        fake=NativeFake();client=SceneClient(fake,capabilities=CAPS)
        result=replay_fixture(client,records)
        self.assertEqual(result['pixel_probes_verified'],0)
        self.assertFalse(result['pixel_expectations'][0]['verified'])
        self.assertEqual(fake.messages[0][3:5],b'\x01\0')
    def test_fixture_preflight_rejects_truncation_oversize_unknownmode_and_delay(self):
        reset=bytes.fromhex('290000000000');valid=b'\x01'+struct.pack('<H',len(reset))+reset
        for n in range(1,len(valid)):
            with self.assertRaises(ValueError):parse_fixture(valid[:n],allow_clip=True)
        for bad in [b'\xff',b'\x02'+struct.pack('<I',60001),b'\x01\x05\0'+b'\x24\0\0\0\0',
                    b'\x04'+struct.pack('<HHB',640,0,0)]:
            with self.assertRaises(ValueError):parse_fixture(bad,allow_clip=True)
        with self.assertRaises(ValueError):parse_fixture(valid,max_message=5,allow_clip=True)
    def test_wait_does_not_use_unadvertised_keepalive(self):
        fake=NativeFake();client=SceneClient(fake,capabilities={**CAPS,'emptyGeometry':'takeover'})
        with self.assertRaises(SceneError):client.wait(400)
        self.assertFalse(fake.writes)


if __name__=='__main__':unittest.main()
