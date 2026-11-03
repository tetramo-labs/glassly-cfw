#!/usr/bin/env python3
"""Check candidate container, actual app hook destination and launch suppression."""
import argparse,copy,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from build_memomind_minimal_owner import construct
from build_memomind_graphics import BODY_BASE
from compile_memomind_graphics import compile_graphics
from memomind_ota import unpack_ota,sha
import unicorn as u
from unicorn import riscv_const as r

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    build=json.loads((a.build/'build.json').read_text());blob=(a.build/'graphics.bin').read_bytes()
    source=(ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes();image,manifest=construct(source,blob,build)
    assert image==(a.image/'firmware.bin').read_bytes()
    assert manifest['version']=='GLASSLYCFW/'+str(build['cfw_revision'])
    _,old=unpack_ota(source);_,streams=unpack_ota(image);body=streams[3]['raw'][32:]
    for i in (1,2,4,5,6):assert streams[i]['packed']==old[i]['packed']
    meta=bytearray(old[0]['raw']);struct.pack_into('<I',meta,76,len(body));assert streams[0]['raw']==meta
    site=0x04217568;off=site-BODY_BASE;first,second=struct.unpack_from('<II',body,off)
    assert first&0xfff==0x97 and second&0xfffff==0x080e7
    hi=first&0xfffff000;lo=second>>20;lo=lo-4096 if lo&2048 else lo
    assert (site+hi+lo)&0xffffffff==build['symbols']['glassly_notification_entry']
    launch=0x0421d17c;uc=u.Uc(u.UC_ARCH_RISCV,u.UC_MODE_RISCV32);uc.mem_map(launch&~4095,4096)
    uc.mem_write(launch,body[launch-BODY_BASE:launch-BODY_BASE+8]);uc.reg_write(r.UC_RISCV_REG_RA,launch+0x100)
    uc.reg_write(r.UC_RISCV_REG_A0,0x02060000);uc.reg_write(r.UC_RISCV_REG_SP,0x03001008)
    uc.emu_start(launch,launch+0x100,count=3)
    assert uc.reg_read(r.UC_RISCV_REG_A0)==0 and uc.reg_read(r.UC_RISCV_REG_SP)==0x03001008
    bad=copy.deepcopy(build);bad['cfw_revision']+=1
    try:construct(source,blob,bad);raise AssertionError('accepted mismatched runtime revision')
    except ValueError:pass
    for revision in (0,-1,65536,True):
        try:compile_graphics('/unused',cfw_revision=revision);raise AssertionError('accepted invalid revision')
        except ValueError:pass
    a.report.write_text(json.dumps({'passed':True,'version':manifest['version'],'imageSHA256':sha(image),'runtimeSHA256':sha(blob),'imageBytes':len(image),'runtimeBytes':len(blob),'unchangedComponents':[1,2,4,5,6],'vendorLaunchSuppressedOffline':True,'flashed':False,'bootVerified':False},indent=2)+'\n')
if __name__=='__main__':main()
