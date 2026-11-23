import binascii
import importlib.util
import json
from pathlib import Path
import struct
import zlib
p = Path(__file__).with_name('verify-records.py')
spec = importlib.util.spec_from_file_location('verifier', p)
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
from memomind_transport import gm_frames

def fixture(mutate=None):
    rows=[]; sequence=250; event=0; compressor=zlib.compressobj()
    dictionary=b'\x08\0'+bytes((i*37)&255 for i in range(4094))
    commands=[dictionary,dictionary,b'\x08\0'+b'x'*65533,b'\x07\x01',b'\x0b']
    def emit(kind,event,payload,direction):
        body=bytes([kind])+len(payload).to_bytes(3,'big')+payload
        rows.extend(dict(event=direction,hex=frame.hex()) for frame in gm_frames(event,15,125,body))
    for index,body in enumerate(commands):
        wire=compressor.compress(body)+compressor.flush(zlib.Z_SYNC_FLUSH)
        crc=binascii.crc_hqx(body,65535)
        record=struct.pack('<BHH',13 if not index else 5,len(wire),crc)+wire
        stream=sequence
        for offset in range(0,len(record),128):
            end=offset+128>=len(record); event=event%255+1
            packet=bytearray([126,1,sequence,1|(128 if not offset else 0)|(64 if end else 0)])+record[offset:offset+128]
            if mutate=='sequence' and index==0 and offset==128: packet[2]^=1
            if mutate=='crc' and index==0 and offset==0: packet[7]^=1
            if mutate=='context' and index==0 and offset==0: packet[4]&=~8
            emit(1,event,packet,'transmitSubmission'); sequence=(sequence+1)&255
            frames=[]
            if end:
                if body[0]==7: frames.append((bytes([5,stream,0,0,1])+bytes(20)).hex())
                ack=bytearray([1,stream,0,0,1])+struct.pack('<HH',len(body),crc)
                if mutate=='ack' and index==0:ack[7]^=1
                frames.append(ack.hex())
            reply=dict(glassly='record-transport',abi=1,status=0,closing=int(end and body[0]==11),frames=frames)
            emit(5,event,json.dumps(reply).encode(),'receive')
    return b'\n'.join(json.dumps(r).encode() for r in rows)

assert len(v.verify(fixture())['records'])==5
for mutation in ('sequence','crc','context','ack'):
    try:v.verify(fixture(mutation))
    except (AssertionError,zlib.error):pass
    else:raise AssertionError('Accepted '+mutation)
try:v.verify(b'\n'.join(fixture().splitlines()[:-1]))
except AssertionError:pass
else:raise AssertionError('Accepted lost ACK')
print('PASS: exact reconstruction and five rejection cases')
