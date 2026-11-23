#!/usr/bin/env python3
"""Execute the stock recording parser with explicit transport/task mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import unicorn as u
from unicorn import riscv_const as r

ROOT = Path(__file__).resolve().parents[2]
BODY = (ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
BODY_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
assert hashlib.sha256(BODY).hexdigest() == BODY_SHA
BASE, RET, GP, SP = 0x041eb020, 0x05000000, 0x02011688, 0x0301fff0
PEER, PACKET = 0x03000000, 0x03000100
REGISTER = lambda i: getattr(r, 'UC_RISCV_REG_X'+str(i))
MOCKS = {0x02000000:'copy',0x02003d5e:'log_enabled',0x04209de8:'negotiate',
         0x0420978e:'peer_transport',0x0431ca9e:'spp_send',0x042463b4:'iap2_channel',
         0x0431b88c:'iap2_send',0x0431a712:'ble_send',0x042361b8:'post',
         0x0420976e:'stop_prepare',0x0420a7ca:'recording_kind',0x0422aefc:'setting'}


def execute(packet, *, transport=1, mode=5, native_state=0, via_callback=True):
    m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
    m.mem_map(BASE & ~4095,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(BASE,BODY)
    m.mem_map(0x02000000,0x60000)
    m.mem_map(0x03000000,0x20000)
    m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC);m.mem_write(RET,bytes.fromhex("67800000"))
    for address in MOCKS:m.mem_write(address,bytes.fromhex("67800000"))
    peer=bytes.fromhex('010203040506')
    m.mem_write(PEER,peer);m.mem_write(PACKET,packet or b'\0')
    m.mem_write(0x020115ff,bytes([mode]));m.mem_write(0x02011968,bytes([native_state]))
    saved={i:0xaabb0000+i for i in (8,9,*range(18,28))}
    args=[0,PEER,PACKET,len(packet)] if via_callback else [PEER,PACKET,len(packet)]
    initial={**saved,1:RET,2:SP,3:GP,4:0x12345678,**{10+i:v for i,v in enumerate(args)}}
    for i,value in initial.items():m.reg_write(REGISTER(i),value)
    calls=[];state={'done':False,'steps':0}
    def hook(mu,address,size,_):
        state['steps']+=1
        if address==RET:state['done']=True;mu.emu_stop();return
        if address in MOCKS:
            a=[mu.reg_read(REGISTER(10+i)) for i in range(4)]
            name=MOCKS[address];result=0;row={'name':name,'args':a}
            if name=='copy':mu.mem_write(a[0],bytes(mu.mem_read(a[1],a[2])));result=a[0]
            elif name=='peer_transport':assert a[0]==PEER;result=transport
            elif name=='iap2_channel':result=7
            elif name=='post':
                assert a[0]==0x13 and a[1] in (1,2)
                row['payload']=bytes(mu.mem_read(a[2],a[3])).hex()
            elif name in ('spp_send','iap2_send','ble_send'):
                row['payload']=bytes(mu.mem_read(a[2],a[3])).hex()
            elif name=='setting':assert a[0]==0x5103 and a[1]<=1
            if name!='copy':calls.append(row)
            continuation=mu.reg_read(REGISTER(1))
            for i in (5,6,7,*range(10,18),28,29,30,31):mu.reg_write(REGISTER(i),0xd0000000+i)
            mu.reg_write(REGISTER(10),result);mu.reg_write(r.UC_RISCV_REG_PC,continuation);return
        assert 0x0420a7da<=address<0x0420aabc,hex(address)
        sp=mu.reg_read(REGISTER(2));assert SP-256<=sp<=SP and sp%16==0
    def write(mu,access,address,size,value,_):
        assert SP-256<=address and address+size<=SP,('unexpected write',hex(address))
    m.hook_add(u.UC_HOOK_CODE,hook);m.hook_add(u.UC_HOOK_MEM_WRITE,write)
    try:
        m.emu_start(0x0420aaa8 if via_callback else 0x0420a7da,RET+4,count=10000)
    except u.UcError as error:
        raise AssertionError((hex(m.reg_read(r.UC_RISCV_REG_PC)),calls)) from error
    assert state['done']
    for i,value in {**saved,2:SP,3:GP,4:initial[4]}.items():assert m.reg_read(REGISTER(i))==value,('ABI',i)
    assert bytes(m.mem_read(PEER,6))==peer
    assert bytes(m.mem_read(PACKET,len(packet)))==packet
    return dict(packet=packet.hex(),transport=transport,mode=mode,nativeState=native_state,calls=calls,**state)


parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--report",type=Path,required=True)
arguments=parser.parse_args()
rows=[]
for transport in (0,1,2,3):
    for flag in (0,1,2):
        row=execute(bytes([0x52,0x12,flag]),transport=transport);rows.append(row)
        assert row['calls'][0]['name']=='negotiate' and row['calls'][0]['args'][0]==int(flag==1)
        send=[c for c in row['calls'] if c['name'].endswith('_send')];assert len(send)==1
        assert send[0]['payload']==bytes([0x52,0x13,int(flag==1),0x31,0x28,0]).hex()
for mode in (1,5):
    for selected in range(9):
        row=execute(bytes([0x52,1,selected]),mode=mode);rows.append(row)
        posts=[c for c in row['calls'] if c['name']=='post'];assert len(posts)==1
        expected=selected if mode==5 and 1<=selected<=7 and selected!=2 else mode
        assert posts[0]['args'][1]==1 and posts[0]['payload']=='010203040506'+bytes([expected]).hex()
for state in (0,1,2,3):
    row=execute(b'\x52\0\0',native_state=state);rows.append(row)
    posts=[c for c in row['calls'] if c['name']=='post'];assert len(posts)==int(state!=2)
    if posts:assert posts[0]['args'][1]==2 and posts[0]['payload']=='010203040506'
for packet in (b'',b'\x52',b'\0\1',b'\x52\xff'):
    row=execute(packet);rows.append(row)
    assert all(c['name']=='log_enabled' for c in row['calls'])
report=dict(passed=True,cases=len(rows),stockBodySHA256=BODY_SHA,unicorn=u.__version__,
            actualCodeRanges=['0420a7da–0420aabc'],hardwareTested=False,
            testSourceSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            mockBoundaries=MOCKS,results=rows,
            limitations=['Task delivery, recorder state, codec, audio, link callbacks and radio are mocked.',
                         'Parser ABI is not proof of a safely leased microphone owner.'])
with arguments.report.open('x') as output:output.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'cases':len(rows),'hardwareTested':False}))
