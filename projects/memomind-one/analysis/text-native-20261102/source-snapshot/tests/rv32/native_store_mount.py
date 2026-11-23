"""Local native mount harness for external reservation regression tests.

Extracted from analysis/ghidra/native-store-inventory/inventory.py. Native RV32
mount, CRC and directory validation execute from the supplied pinned app bytes.
Only directory reads and synthetic badmap retrieval are callbacks. Mutation,
repair and package-validation callbacks fail immediately; hardware is unmapped.
"""
import hashlib, struct
import unicorn as u
from unicorn import riscv_const as r
ENTRY, CTX, CFG, STACK, RET = 0x042a0e46,0x03000000,0x03002000,0x03010000,0x05000000
READ,BAD,FORBIDDEN = 0x05000010,0x05000020,0x05000030

def sha(b): return hashlib.sha256(b).hexdigest()

def native_mount(data, body, capacity, badmap=bytes(96), badmap_status=0):
    if len(data)!=65536 or len(badmap)!=96: raise ValueError('directory/badmap size')
    m=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
    m.mem_map(0x041eb000,0x200000,u.UC_PROT_READ|u.UC_PROT_EXEC)
    m.mem_write(0x041eb020,body)
    m.mem_map(0x02000000,0x100000)
    m.mem_write(0x02000000,body[0x64:0x64+0xf8b4])
    off=0x04399fc8-0x041eb020
    m.mem_write(0x0200f8b8,body[off:off+0x1e78])
    m.mem_map(CTX,0x10000)
    m.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC)
    for a in (RET,READ,BAD,FORBIDDEN):m.mem_write(a,bytes.fromhex('67800000'))
    m.mem_write(CFG,struct.pack('<10I',0,READ,FORBIDDEN,FORBIDDEN,FORBIDDEN,BAD,FORBIDDEN,0,1822432,0))
    reg=lambda x: getattr(r,'UC_RISCV_REG_X'+str(x))
    for i,v in {1:RET,2:STACK-16,3:0x02011688,10:CTX,11:CFG,12:capacity,13:0}.items():m.reg_write(reg(i),v)
    reads=[]; steps=0; minsp=STACK-16; stopped=False
    def hook(mu,a,size,_):
        nonlocal steps,minsp,stopped
        steps+=1;minsp=min(minsp,mu.reg_read(reg(2)))
        if a==RET: stopped=True;mu.emu_stop();return
        if a==FORBIDDEN:raise RuntimeError('unexpected native mutation/validation callback')
        if a in (READ,BAD):
            args=[mu.reg_read(reg(i)) for i in range(10,14)]
            if a==READ:
                _,off,dst,n=args
                if off>len(data) or n>len(data)-off or not CTX<=dst<STACK or n>STACK-dst:raise RuntimeError('callback bounds')
                mu.mem_write(dst,data[off:off+n]);reads.append({'offset':off,'length':n});status=0
            else:
                _,dst,n,_=args
                if dst!=CTX+0x1120 or n!=96:raise RuntimeError('badmap callback ABI')
                mu.mem_write(dst,badmap);status=badmap_status
            mu.reg_write(reg(10),status&0xffffffff);mu.reg_write(r.UC_RISCV_REG_PC,mu.reg_read(reg(1)))
    m.hook_add(u.UC_HOOK_CODE,hook)
    m.emu_start(ENTRY,0,count=8000000)
    if not stopped:raise RuntimeError('native instruction budget exhausted')
    result=m.reg_read(reg(10));result=result if result<2**31 else result-2**32
    ctx=bytes(m.mem_read(CTX,0x11a0))
    return {'return_code':result,'read_callbacks':reads,'instructions':steps,'max_stack_bytes':STACK-16-minsp,
            'mutating_callbacks':0,'synthetic_badmap_sha256':sha(badmap),'badmap_callback_status':badmap_status},ctx
