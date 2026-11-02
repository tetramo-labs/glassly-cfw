#!/usr/bin/env python3
"""Analysis-only inventory using the pinned native RV32 mount implementation.
No native flash API executes: callbacks read an immutable local byte string.
Bad-sector bitmap is an explicit synthetic input, never an inferred device fact.
"""
import argparse, hashlib, json, struct, zlib
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r
ROOT = Path(__file__).resolve().parents[3]
APP = ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin'
APP_SHA = '81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8'
ENTRY, CTX, CFG, STACK, RET = 0x042a0e46,0x03000000,0x03002000,0x03010000,0x05000000
READ,BAD,FORBIDDEN = 0x05000010,0x05000020,0x05000030
CAPACITY, COMMIT = 0x300000,0x434f4d54

def sha(b): return hashlib.sha256(b).hexdigest()
def words(b,off,n): return struct.unpack_from('<'+'I'*n,b,off)
def rounded(n): return (n+4095)&~4095

def native_mount(data, badmap=bytes(96), badmap_status=0):
    if len(data)!=65536 or len(badmap)!=96: raise ValueError('directory/badmap size')
    body=APP.read_bytes()
    if sha(body)!=APP_SHA: raise ValueError('native source hash mismatch')
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
    for i,v in {1:RET,2:STACK-16,3:0x02011688,10:CTX,11:CFG,12:CAPACITY,13:0}.items():m.reg_write(reg(i),v)
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

def entries_from_context(ctx):
    entries=[]
    for i in range(28):
        off=0x58+i*0x90;e=ctx[off:off+0x90];state=words(e,0x78,1)[0]
        if not state:continue
        w=words(e,0x60,12);name=e[:64].split(b'\0',1)[0]
        start=w[3];end=start+rounded(w[1])
        entries.append({'index':i,'name_utf8':name.decode('utf-8','backslashreplace'),'name_hex':name.hex(),
          'content_sha256':e[64:96].hex(),'version':w[0],'length':w[1],'abi':w[2],
          'relative_start':start,'relative_end_exclusive':end,'completed_length':w[4],'flags':w[5],
          'protected':bool(w[5]&1),'state':state,'use_counter':w[8]|w[9]<<32,
          'validated_app_length':w[10],'validated_app_crc32':w[11],
          'overlaps_last_256k':start<0x300000 and 0x2c0000<end})
    return entries

def inventory(data,expected=None):
    if len(data)!=65536:raise ValueError('expected exactly65536 bytes')
    if expected and sha(data)!=expected:raise ValueError('capture SHA mismatch')
    snapshots=[]
    for i in range(8):
        s=data[i*8192:(i+1)*8192];w=words(s,0,12)
        journals=[words(s,0xff8+24*j,6) for j in range(170)]
        snapshots.append({'slot':i,'erased_bytes':sum(x==255 for x in s),'magic':hex(w[0]),'version':w[1],
          'generation_raw':w[2]|w[3]<<32,'capacity_raw':w[6],'cursor_raw':w[7],
          'crc_stored':hex(words(s,0xff0,1)[0]),'crc_computed':hex(zlib.crc32(s[:0xff0])&0xffffffff),
          'crc_matches':words(s,0xff0,1)[0]==zlib.crc32(s[:0xff0])&0xffffffff,
          'commit':hex(words(s,0x1ffc,1)[0]),'committed':words(s,0x1ffc,1)[0]==COMMIT,
          'nonerased_journal_slots':[j for j,x in enumerate(journals) if x!=(0xffffffff,)*6]})
    mount,ctx=native_mount(data)
    # A failed mount leaves unvalidated snapshot bytes in context: never parse as live entries.
    selected=words(ctx,0x1180,1)[0] if mount['return_code']==0 else None
    records=entries_from_context(ctx) if selected is not None else []
    erased=all(x==255 for x in data)
    return {'format':'memomind-native-directory-inventory-v1','source_sha256':sha(data),'bytes':len(data),
      'all_bytes_erased':erased,'snapshot_slots':snapshots,'native_mount_conditional':mount,
      'native_source_sha256':APP_SHA,'unicorn_version':u.__version__,
      'selected_snapshot':selected,'classification':'erased-unformatted' if erased and mount['return_code']==-1 else ('mounted' if mount['return_code']==0 else 'native-mount-rejected'),
      'entries':records,'protected_entries':[x['index'] for x in records if x['protected']],
      'candidate_entries':[x['index'] for x in records if x['state']==1],
      'pending_move':dict(zip(('entry_plus_one','destination','progress'),words(ctx,0x48,3))) if selected is not None else None,
      'recorded_overlap_last_256k':any(x['overlaps_last_256k'] for x in records) if selected is not None or erased else None,
      'journal_replay_performed':selected is not None,'badmap_acquired':False,
      'consistent_atomic_snapshot_proven':False,'reservation_established':False,
      'limitations':['Native mount executed with synthetic zero badmap, not actual KV0x6009','Capture is sequential256-byte reads, not atomic','Payload sectors and live RAM owners not acquired','No directory entries does not reserve flash; native allocator/reset still owns full partition']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--expected-sha256');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(inventory(a.capture.read_bytes(),a.expected_sha256),indent=2)+'\n')
