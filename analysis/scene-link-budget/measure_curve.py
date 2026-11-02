#!/usr/bin/env python3
"""Measure actual RV32 vector compiler recursive stack on isolated linked blobs."""
import json,struct
from pathlib import Path
import unicorn as u
from unicorn import riscv_const as r
HERE=Path(__file__).resolve().parent
BASE,RET,STACK,WORK,SOURCE,PATH=0x0439bea0,0x05000000,0x03002000,0x06000000,0x06010000,0x06020000
reports=[]
for mode in ('O2','Os'):
    blob=(HERE/mode/'full.bin').read_bytes();symbols={}
    for row in (HERE/mode/'symbols.txt').read_text().splitlines():
        f=row.split()
        if len(f)==4:symbols[f[3]]=int(f[0],16)
    cases={
        'closed_line':bytes([0])+struct.pack('<hh',0,0)+bytes([1])+struct.pack('<hh',160,160)+bytes([4]),
        'high_curvature_cubic':bytes([0])+struct.pack('<hh',-32768,-32768)+bytes([3])+struct.pack('<6h',32767,-32768,-32768,32767,32767,32767)+bytes([4]),
        'opposed_control_cubic':bytes([0])+struct.pack('<hh',0,0)+bytes([3])+struct.pack('<6h',32767,-32768,-32768,32767,16,0)+bytes([4]),
    }
    for name,payload in cases.items():
        machine=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32)
        start=BASE&~4095;end=(BASE+len(blob)+4095)&~4095
        machine.mem_map(start,end-start,u.UC_PROT_READ|u.UC_PROT_EXEC);machine.mem_write(BASE,blob)
        machine.mem_map(RET,4096,u.UC_PROT_READ|u.UC_PROT_EXEC);machine.mem_write(RET,bytes.fromhex('13000000'))
        machine.mem_map(STACK-8192,8192);machine.mem_map(WORK,0x30000)
        machine.mem_write(SOURCE,payload)
        for index in range(1,32):machine.reg_write(getattr(r,f'UC_RISCV_REG_X{index}'),0xa0000000+index*0x101)
        initial={1:RET,2:STACK,3:0x02011688,4:0x0200abcd}
        for index,value in initial.items():machine.reg_write(getattr(r,f'UC_RISCV_REG_X{index}'),value)
        for index,value in enumerate((WORK,10752,SOURCE,len(payload),0,PATH,8196)):
            machine.reg_write(getattr(r,f'UC_RISCV_REG_X{index+10}'),value)
        saved={i:machine.reg_read(getattr(r,f'UC_RISCV_REG_X{i}')) for i in (1,2,3,4,8,9,*range(18,28))}
        stats={'min_sp':STACK,'instructions':0,'curve_depths':[],'writes':0}
        def code(uc,address,size,data):
            assert BASE<=address<BASE+len(blob)
            sp=uc.reg_read(r.UC_RISCV_REG_SP);assert STACK-8192<=sp<=STACK and sp%16==0
            stats['min_sp']=min(stats['min_sp'],sp);stats['instructions']+=1
            if address==symbols['cv_curve']:stats['curve_depths'].append(uc.reg_read(r.UC_RISCV_REG_A3))
        def write(uc,access,address,size,value,data):
            assert (STACK-8192<=address and address+size<=STACK) or (WORK<=address and address+size<=WORK+10752) or (PATH<=address and address+size<=PATH+8196)
            stats['writes']+=1
        machine.hook_add(u.UC_HOOK_CODE,code);machine.hook_add(u.UC_HOOK_MEM_WRITE,write)
        machine.emu_start(symbols['mm_vector_compile'],RET,count=10000000)
        assert machine.reg_read(r.UC_RISCV_REG_PC)==RET
        for index,value in saved.items():assert machine.reg_read(getattr(r,f'UC_RISCV_REG_X{index}'))==value
        result=machine.reg_read(r.UC_RISCV_REG_A0);result=result-0x100000000 if result&0x80000000 else result
        reports.append({'optimization':mode,'case':name,'result':result,'input_hex':payload.hex(),
                        'observed_stack_bytes':STACK-stats['min_sp'],'instructions':stats['instructions'],
                        'maximum_curve_depth_argument':max(stats['curve_depths'],default=None),
                        'curve_entry_count':len(stats['curve_depths']),'writes':stats['writes'],
                        'saved_gp_tp_registers_preserved':True,'scope':'Actual linked RV32 mm_vector_compile and all callees; no native functions or scene callbacks invoked'})
(HERE/'curve-stack-measurements.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports,indent=2))
