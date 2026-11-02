import copy
import json
import struct
import zlib
import unittest
from collections import deque
from memomind_flash_read import DIAGNOSTIC_PROFILE, PROFILES, FlashReadError, FlashReadProtocolError
from memomind_storage_diag import StorageDiagnosticClient, TOPOLOGY_LIMITS, validate_topology, validate_badmap, tail_unavailable_map
from memomind_transport import gm_frames, parse_tlvs

def topology():
    return dict(glassly='flash-read', abi=1, result='ok', diagnostic='topology',
                **{k: 0 for k in TOPOLOGY_LIMITS})

def badmap():
    raw=struct.pack('<4I',0x474d4231,1,0x01500000,0x00300000)+bytes(64)+b'\1'+bytes(30)+b'\x80'
    raw+=struct.pack('<I',zlib.crc32(raw))
    return dict(glassly='flash-read',abi=1,result='ok',diagnostic='badmap',kvStatus=0,
                actualLength=116,recordState='present',mapHex=raw[16:112].hex(),recordHex=raw.hex())

class Wire:
    timeout=20
    def __init__(self):
        self.messages=[];self.incoming=deque();self.edit=lambda x:x
    def write(self, frame):
        if len(frame)==9:return
        body=parse_tlvs(frame[7:-2]);assert len(body)==1 and body[0][0]==1
        body=body[0][1];self.messages.append(body)
        if body==b'\0':
            reply=dict(glassly='flash-read',abi=1,result='ok',profile=DIAGNOSTIC_PROFILE,
                       maxRead=256,alignment=256,ranges=[dict(device=d,start=b,end=e) for d,b,e in PROFILES[DIAGNOSTIC_PROFILE].values()])
        else:
            assert body in (b'\2',b'\3');reply=topology() if body==b'\2' else badmap()
        raw=json.dumps(self.edit(reply),separators=(',',':')).encode()
        wire=b''.join(gm_frames(frame[4],15,0x7b,b'\5'+len(raw).to_bytes(3,'big')+raw))
        self.incoming.extend(wire[n:n+13] for n in range(0,len(wire),13))
    def read(self,timeout):
        if not self.incoming:raise TimeoutError('No reply')
        return self.incoming.popleft()

class StorageDiagnosticsTests(unittest.TestCase):
    def test_actual_record_independent_crc_and_tail_slice(self):
        w=Wire();c=StorageDiagnosticClient(w)
        with self.assertRaises(FlashReadError):c.badmap()
        c.query();r=c.badmap();self.assertEqual(r,badmap())
        self.assertEqual(tail_unavailable_map(r),b'\1'+bytes(30)+b'\x80')
        for byte in range(116):
            r=badmap();raw=bytearray.fromhex(r['recordHex']);raw[byte]^=1;r['recordHex']=raw.hex()
            with self.assertRaises(FlashReadProtocolError):validate_badmap(r)
        for bit in range(16):
            r=badmap();raw=bytearray.fromhex(r['recordHex']);raw[16+bit//8]|=1<<(bit%8);raw[112:]=struct.pack('<I',zlib.crc32(raw[:112]));r['recordHex']=raw.hex();r['mapHex']=raw[16:112].hex()
            with self.assertRaises(FlashReadProtocolError):validate_badmap(r)

    def test_absence_invalid_and_unavailable_are_distinct(self):
        r=badmap();r.update(recordState='absent',kvStatus=7,actualLength=0,recordHex='',mapHex='00'*96)
        validate_badmap(r);self.assertEqual(tail_unavailable_map(r),bytes(32))
        for patch in ({'actualLength':116},{'kvStatus':0},{'mapHex':'01'+'00'*95},{'recordHex':'00'}):
            with self.assertRaises(FlashReadProtocolError):validate_badmap({**r,**patch})
        for state,status in [('invalid',0),('unavailable',2),('unavailable',4),('unavailable',13)]:
            r.update(recordState=state,kvStatus=status,mapHex='');validate_badmap(r)
            with self.assertRaises(FlashReadError):tail_unavailable_map(r)
        for patch in ({'kvStatus':7},{'mapHex':'00'*96},{'recordHex':'00'*116},{'recordState':'unknown'},{'abi':True},{'result':'failed'}):
            with self.assertRaises(FlashReadProtocolError):validate_badmap({**r,**patch})

    def test_malformed_badmap_stops_client(self):
        w=Wire();c=StorageDiagnosticClient(w);c.query()
        w.edit=lambda r:{**r,'mapHex':'00'*96}
        with self.assertRaises(FlashReadProtocolError):c.badmap()
        sent=list(w.messages)
        with self.assertRaises(FlashReadError):c.badmap()
        self.assertEqual(w.messages,sent)

    def test_requires_exact_profile_before_query(self):
        w=Wire();c=StorageDiagnosticClient(w)
        with self.assertRaises(FlashReadError):c.topology()
        self.assertFalse(w.messages);c.query();self.assertEqual(c.topology(),topology())
        self.assertEqual(w.messages,[b'\0',b'\2'])

    def test_fixed_fields_and_integer_limits(self):
        for key,maximum in TOPOLOGY_LIMITS.items():
            for value in (-1,maximum+1,True,False,'0',None,0.0):
                reply=topology();reply[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(FlashReadProtocolError):validate_topology(reply)
        for key in topology():
            reply=topology();del reply[key]
            with self.assertRaises(FlashReadProtocolError):validate_topology(reply)
        reply=topology();reply['address']=0x02012334
        with self.assertRaises(FlashReadProtocolError):validate_topology(reply)

    def test_probe_scope_and_consistency_are_preserved(self):
        reply=topology();reply['xip1LegacyId']=0x8517
        with self.assertRaises(FlashReadProtocolError):validate_topology(reply)
        reply['xip1ProbeValid']=1
        for driver in (0,2,3):
            reply['xip1Driver']=driver
            with self.assertRaises(FlashReadProtocolError):validate_topology(reply)
        reply['xip1Driver']=1;validate_topology(reply)
        self.assertEqual(reply['consistent'],0)

    def test_malformed_response_poisoned_without_retry(self):
        w=Wire();c=StorageDiagnosticClient(w);c.query()
        def wrong(r):r['consistent']=True;return r
        w.edit=wrong
        with self.assertRaises(FlashReadProtocolError):c.topology()
        sent=list(w.messages)
        with self.assertRaises(FlashReadError):c.topology()
        self.assertEqual(w.messages,sent)

    def test_unknown_profile_rejected_without_diagnostic(self):
        w=Wire();c=StorageDiagnosticClient(w)
        def wrong(r):r['profile']='H001Y-1.0.3.127-external-v1';return r
        w.edit=wrong
        with self.assertRaises(FlashReadProtocolError):c.query()
        self.assertEqual(w.messages,[b'\0'])

if __name__=='__main__':unittest.main()
