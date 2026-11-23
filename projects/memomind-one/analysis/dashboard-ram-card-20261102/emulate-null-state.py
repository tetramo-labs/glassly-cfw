#!/usr/bin/env python3
"""Actual pinned RV32 card APIs with a cold-zero owner and three witnessed gates.

Only logging-enabled predicate is mocked (disabled). No allocator, LVGL, I/O,
settings, event or cleanup dependency may execute. This does not run the full
launcher parent constructor, which intentionally creates unrelated UI objects.
"""
import argparse,hashlib,json,re,struct,sys
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=0x041eb020
SHA='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
STATE=0x02011d2c
GP=0x02011688
RET=0x05000000
SCRATCH=0x03000000
SP=0x0301fff0
GATES={0x04264f26:bytes.fromhex('011122cc'),0x04265060:bytes.fromhex('011122cc'),0x042652e8:bytes.fromhex('83a7416a')}
GATE=bytes.fromhex('01458280')
def sha(data):return hashlib.sha256(data).hexdigest()
def build():
    stock=(ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin').read_bytes()
    assert sha(stock)==SHA
    body=bytearray(stock)
    for a,before in GATES.items():
        assert body[a-BASE:a-BASE+4]==before
        body[a-BASE:a-BASE+4]=GATE
    functions=[int(a,16) for a in json.loads((HERE/'state-functions.json').read_text())]
    assert len(functions)==30 and len(set(functions))==30
    allowed={}
    for a in functions:
        asm=(HERE/f'native/function-{a:08x}.asm').read_text()
        instructions={int(x,16) for x in re.findall(r'^ram:([0-9a-f]+)  ',asm,re.M)}
        assert a in instructions
        allowed[a]=instructions
    for a in GATES:allowed[a]|={a,a+2}
    return stock,bytes(body),functions,allowed
REG=lambda i:getattr(r,'UC_RISCV_REG_X'+str(i))
def run(body,functions,allowed,entry,pattern):
    m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
    m.mem_map(0x041eb000,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC)
    m.mem_write(BASE,body)
    m.mem_map(0x02000000,0x60000)
    # These are the two pinned reset copy ranges, not invented function bodies.
    m.mem_write(0x02000000,body[0x64:0x64+0xf8b4])
    m.mem_write(0x0200f8b8,body[0x04399fc8-BASE:0x04399fc8-BASE+0x1e78])
    assert int.from_bytes(m.mem_read(STATE,4),'little')==0
    assert not any(m.mem_read(0x02011730,0x0205e128-0x02011730))
    m.mem_map(SCRATCH,0x20000)
    m.mem_write(SCRATCH,bytes([0xa5])*0x10000)
    m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC)
    m.mem_write(RET,bytes.fromhex('67800000'))
    args=[0]*8 if pattern=='zero' else ([0xffffffff]*8 if pattern=='poison' else [SCRATCH+i*64 for i in range(8)])
    for i in range(1,32):m.reg_write(REG(i),0xcafe0000+i)
    m.reg_write(REG(1),RET);m.reg_write(REG(2),SP);m.reg_write(REG(3),GP);m.reg_write(REG(4),0x12345678)
    for i,v in enumerate(args):m.reg_write(REG(10+i),v)
    m.reg_write(r.UC_RISCV_REG_MSTATUS,0x6000)
    before={i:m.reg_read(REG(i)) for i in range(1,32)}
    ram=bytes(m.mem_read(0x02000000,0x60000));borrowed=bytes(m.mem_read(SCRATCH,0x10000))
    # Non-entry native calls are confined to the original null-safe reset used
    # by card builders. Every other dependency is rejected, not returned-success.
    permitted=allowed[entry]|allowed[0x042642ca]
    state={'done':False,'steps':0,'log_predicates':0,'visited_entries':[],'stack_low':SP}
    def code(mu,address,size,_):
        state['steps']+=1
        state['stack_low']=min(state['stack_low'],mu.reg_read(REG(2)))
        if address==RET:state['done']=True;mu.emu_stop();return
        if address==0x02003d5e:
            assert entry not in GATES,'gate called logger'
            state['log_predicates']+=1
            mu.reg_write(REG(10),0)
            mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(REG(1)))
            return
        assert address in permitted,('unmocked external code',hex(entry),hex(address))
        if address in functions:state['visited_entries'].append(hex(address))
    def write(mu,access,address,size,value,_):
        assert entry not in GATES,('gate wrote memory',hex(address))
        assert SP-512<=address and address+size<=SP,('write outside own stack',hex(entry),hex(address),size)
    def read(mu,access,address,size,value,_):
        if entry in GATES:raise AssertionError(('gate read data',hex(address)))
        # NULL pointers and adjacent low memory are deliberately unmapped.
    m.hook_add(u.UC_HOOK_CODE,code);m.hook_add(u.UC_HOOK_MEM_WRITE,write);m.hook_add(u.UC_HOOK_MEM_READ,read)
    m.emu_start(entry,RET+4,count=10000)
    assert state['done'],'instruction budget exhausted'
    for i in (2,3,4,8,9,*range(18,28)):
        assert m.reg_read(REG(i))==before[i],('ABI clobber',hex(entry),i)
    assert bytes(m.mem_read(0x02000000,0x60000))==ram,'native state changed'
    assert bytes(m.mem_read(SCRATCH,0x10000))==borrowed,'borrowed input changed'
    assert int.from_bytes(m.mem_read(STATE,4),'little')==0
    if entry in GATES:
        assert m.reg_read(REG(10))==0
        for i in before:
            if i!=10:assert m.reg_read(REG(i))==before[i],('gate GPR clobber',i)
    if entry==0x042642ca:assert m.reg_read(REG(10))==0
    return {'entry':hex(entry),'pattern':pattern,'gate':entry in GATES,'stack_used':SP-state.pop('stack_low'),**state}
def main():
    assert __debug__,'assertions required'
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    stock,body,functions,allowed=build();cases=[]
    for entry in functions:
        for pattern in ('zero','poison','borrowed'):cases.append(run(body,functions,allowed,entry,pattern))
    report={'passed':True,'cases':len(cases),'recognized_state_apis':30,'gate_cases':9,'unicorn':u.__version__,'source_sha256':SHA,'edited_body_sha256':sha(body),'harness_sha256':sha(Path(__file__).read_bytes()),'max_stack_bytes':max(c['stack_used'] for c in cases),'results':cases,'limitations':['Cold-zero state only; this is not live object teardown.','Only native logging predicate mocked disabled; logging-enabled formatting is not exercised.','No full launcher/other-app constructor, real LVGL, asynchronous queue concurrency or hardware execution.','Enumerated direct state-reader set from saved Ghidra; no universal indirect-alias proof.','No RAM saving measured; static base requested payload lower bound is216B.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
if __name__=='__main__':main()
