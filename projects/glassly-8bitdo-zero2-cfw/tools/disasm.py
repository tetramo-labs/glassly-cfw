"""Print a bounded Thumb range with resolved literal loads (analysis only)."""
import argparse
from pathlib import Path
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS, CS_OP_MEM
p=argparse.ArgumentParser();p.add_argument('file');p.add_argument('start',type=lambda s:int(s,0));p.add_argument('end',type=lambda s:int(s,0));p.add_argument('--base',type=lambda s:int(s,0),default=0x1018000)
a=p.parse_args();data=Path(a.file).read_bytes();md=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS);md.detail=True
for ins in md.disasm(data[a.start:a.end],a.base+a.start):
 comment=''
 if ins.mnemonic=='ldr' and len(ins.operands)>1 and ins.operands[1].type==CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base)=='pc':
  off=((ins.address+4)&~3)+ins.operands[1].mem.disp-a.base
  if 0<=off<=len(data)-4:comment=f' ; [{off:x}] = {struct.unpack_from("<I",data,off)[0]:08x}'
 if ins.mnemonic=='adr':
  off=((ins.address+4)&~3)+ins.operands[1].imm-a.base
  if 0<=off<len(data):comment=f' ; {off:x}: {data[off:off+60].split(bytes([0]))[0]!r}'
 print(f'{ins.address:08x}: {ins.bytes.hex():8} {ins.mnemonic:8} {ins.op_str}{comment}')
