#!/usr/bin/env python3
"""Execute stock recording task/start/stop/reset/format, mocking hardware and tasks."""
import argparse, hashlib, json, struct
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r
ROOT=Path(__file__).resolve().parents[2]
BASE,RET,GP,SP,PEER=0x041eb020,0x05000000,0x02011688,0x0301fff0,0x03000000
BODY=(ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
SHA='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
assert hashlib.sha256(BODY).hexdigest()==SHA
MOCKS={0x02000000:'copy',0x0200b27e:'zero',0x02003d5e:'log',0x0200f6e8:'clock',
  0x0420978e:'transport',0x04209a00:'channel',0x0422b05a:'setting',0x04246384:'route',
  0x04246282:'peer',0x04216450:'other_peer',0x042163f6:'special',0x0430bdac:'config',
  0x042170ce:'priority',0x0430bd60:'noise',0x04208ec0:'audio_busy',0x04209c6e:'audio_open',
  0x0431ca9e:'spp',0x042463b4:'iap_channel',0x0431b88c:'iap',0x0431a712:'ble',
  0x04236404:'cancel',0x042363f4:'delay',0x042361b8:'post',0x0430b8c0:'audio_close',
  0x0422724a:'release',0x0420995c:'cleanup',0x042096fe:'notify'}
RANGES=[(0x0420a316,0x0420a7ca),(0x0420a00c,0x0420a0c0),(0x0420a232,0x0420a316),
        (0x04209998,0x04209a00),(0x0420976e,0x0420978e),(0x04209de8,0x04209e00)]
def execute(entry,args,*,transport=1,active=0,state=0,cooldown=0,busy=0,close_error=0,open_error=0):
    m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
    m.mem_map(BASE&~4095,0x200000);m.mem_write(BASE,BODY)
    m.mem_map(0x02000000,0x60000);m.mem_map(0x03000000,0x20000);m.mem_map(RET,4096)
    m.mem_write(RET,bytes.fromhex('13000000'))
    for a in MOCKS:m.mem_write(a,bytes.fromhex('67800000'))
    m.mem_write(PEER,bytes(range(1,7))+b'\5');m.mem_write(0x0201196c,bytes([active]));m.mem_write(0x02011968,struct.pack('<I',state));m.mem_write(0x02011960,struct.pack('<I',cooldown))
    reg=lambda i:getattr(r,'UC_RISCV_REG_X'+str(i))
    def get(i):return m.reg_read(reg(i))
    def put(i,v):m.reg_write(reg(i),v)
    for i in range(1,32):put(i,0xaabb0000+i)
    put(1,RET);put(2,SP);put(3,GP)
    for i,v in enumerate(args):put(10+i,v)
    saved={i:get(i) for i in (1,2,3,4,8,9,*range(18,28))};calls=[]
    def hook(mu,address,size,_):
        if address in MOCKS:
            a=[get(10+i) for i in range(5)];name=MOCKS[address];value=0
            if name=='copy':m.mem_write(a[0],bytes(m.mem_read(a[1],a[2])));value=a[0]
            elif name=='zero':assert a[1:]==[14,0,14,a[4]];m.mem_write(a[0],bytes(14))
            elif name=='clock':value=1000
            elif name=='transport':assert bytes(m.mem_read(a[0],6))==bytes(range(1,7));value=transport
            elif name in ('channel','iap_channel'):value=4
            elif name=='route':value=transport-1
            elif name=='peer':value=1
            elif name=='config':assert a[0]==5;m.mem_write(a[4],bytes(4))
            elif name=='audio_busy':value=busy
            elif name=='audio_open':value=open_error
            elif name=='audio_close':assert a[:2]==[0,1];value=close_error
            row={'name':name,'args':a}
            if name in ('spp','iap','ble','post','delay'):row['payload']=bytes(m.mem_read(a[2],a[3])).hex()
            if name not in ('copy','zero','log'):calls.append(row)
            ret=get(1)
            for i in (5,6,7,*range(10,18),28,29,30,31):put(i,0xd0000000+i)
            put(10,value);m.reg_write(r.UC_RISCV_REG_PC,ret);return
        assert any(lo<=address<hi for lo,hi in RANGES),(hex(address),calls)
        assert SP-256<=get(2)<=SP and get(2)%16==0
    def write(mu,access,address,size,value,_):
        assert (SP-256<=address and address+size<=SP) or any(lo<=address and address+size<=hi for lo,hi in ((0x0201194f,0x0201196d),(0x020127e0,0x020127ee)))
    m.hook_add(u.UC_HOOK_CODE,hook);m.hook_add(u.UC_HOOK_MEM_WRITE,write)
    m.emu_start(entry,RET,count=10000);assert m.reg_read(r.UC_RISCV_REG_PC)==RET
    for i,v in saved.items():assert get(i)==v,(i,hex(get(i)),hex(v))
    assert bytes(m.mem_read(PEER,7))==bytes(range(1,7))+b'\5'
    return dict(entry=hex(entry),transport=transport,initialActive=active,initialState=state,busy=busy,closeError=close_error,openError=open_error,calls=calls,
        active=m.mem_read(0x0201196c,1)[0],state=struct.unpack('<I',m.mem_read(0x02011968,4))[0],format=struct.unpack('<I',m.mem_read(0x02011964,4))[0],result=get(10))
def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args();rows=[]
    for transport in (1,2):
        row=execute(0x0420a316,[1,PEER,7],transport=transport);rows.append(row)
        assert row['active']==1 and row['state']==1
        sends=[c for c in row['calls'] if c['name'] in ('spp','iap')];assert len(sends)==1 and sends[0]['payload']=='521100000001'
    for busy,open_error in ((1,0),(0,9)):
        row=execute(0x0420a316,[1,PEER,7],busy=busy,open_error=open_error);rows.append(row)
        assert row['active']==0 and row['state']==int(bool(busy))
    row=execute(0x0420a316,[1,PEER,7],cooldown=2000);rows.append(row)
    assert not row['active'] and next(c for c in row['calls'] if c['name']=='delay')['args'][4]==1000
    for active,busy,close_error in ((0,0,0),(1,0,0),(1,0,9),(1,1,0)):
        row=execute(0x0420a232,[],active=active,state=active,busy=busy,close_error=close_error);rows.append(row)
        assert row['active']==int(active and close_error!=0) and row['state']==row['active']
    row=execute(0x04209998,[PEER],state=1);rows.append(row);assert row['state']==0 and row['active']==0
    for format in (0,1,2):
        row=execute(0x04209de8,[format]);rows.append(row);assert row['format']==int(format==1)
    a.report.write_text(json.dumps(dict(passed=True,cases=len(rows),stockBodySHA256=SHA,actualCodeRanges=RANGES,mockBoundaries=MOCKS,hardwareTested=False,results=rows),indent=2)+'\n')
    print(f'Native microphone ABI: {len(rows)} cases passed')
if __name__=='__main__':main()
