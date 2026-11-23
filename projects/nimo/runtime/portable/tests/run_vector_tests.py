#!/usr/bin/env python3
"""Run portable vector original assertions, differential tests and RV32 audit."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--g2-source',type=Path,default=Path(__file__).resolve().parents[4]/'memomind-one/tests/g2_compat/upstream')
    p.add_argument('--cc',default='clang')
    p.add_argument('--rvcc',type=Path,default=REPO/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=a.g2_source.resolve();pin=json.loads((ROOT/'UPSTREAM.json').read_text())
    report={'hardware_tested':False,'scope':'portable compiler/raster; no scene/cache/timer/lease port','commands':[],
            'result':'failed','source_commit':pin['source_commit']}
    def run(label,command,input=None,accepted=(0,)):
        result=subprocess.run([str(v) for v in command],input=input,capture_output=True)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label':label,'argv':[str(v) for v in command],'returncode':result.returncode})
        if result.returncode not in accepted:raise RuntimeError(label+' failed; see recorded stdout/stderr')
        return result
    try:
        reference_pins={k:v for k,v in pin['files'].items() if k!='LICENSE'}
        for name,digest in reference_pins.items():
            if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Changed source '+name)
        report['source_hashes_verified']=len(pin['files'])
        report['portable_input_sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(ROOT.rglob('*')) if f.is_file() and f.suffix in ('.c','.h','.py','.json')}
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Wno-unused-function','-fsanitize=address,undefined',
               '-fno-sanitize-recover=all','-I'+str(source/'patches')]
        files=[ROOT/'geometry.c',ROOT/'vector.c']
        run('build-tests',[a.cc,*flags,'-DMM_VECTOR_TESTING',
            '-DG2_REFERENCE_SOURCE="'+str(source/'patches/host/shapes_host_test.c')+'"',*files,
            ROOT/'tests/g2_vector_reference.c',ROOT/'tests/test_vector.c','-o',out/'test_vector'])
        result=run('vector-tests',[out/'test_vector']);report['tests']=result.stdout.decode().strip()
        run('build-portable-path-check',[a.cc,*flags,*files,ROOT/'tests/vector_path_check.c','-o',out/'portable_path_check'])
        run('build-original-path-check',[a.cc,*flags,source/'patches/host/vector_path_check.c','-o',out/'original_path_check'])
        point=lambda op,x,y:bytes([op])+struct.pack('<hh',x,y)
        box=point(0,0,0)+point(1,1600,0)+point(1,1600,1600)+point(1,0,1600)+b'\x04'
        rng=random.Random(0x103127)
        cases=[b'',b'\x04',b'\x63',point(0,0,0)+b'\x04',box,box*2,
               point(0,-32768,32767)+b'\x03'+struct.pack('<hhhhhh',32767,-32768,-32768,-32768,32767,32767)+b'\x04']
        cases += [box[:n] for n in range(1,len(box))]
        for n in (510,511,512,513):
            cases.append(point(0,0,0)+b''.join(point(1,(i%2)*1600,i+1) for i in range(n))+b'\x04')
        cases += [(point(0,0,0)+b'\x04')*n for n in (512,513)]
        cases += [rng.randbytes(n) for n in range(1,257)]
        cases += [b'\0'*8192,b'\0'*8193]
        comparisons=[]
        for i,data in enumerate(cases):
            # Preserve exact inputs for replay; errors are expected corpus outcomes.
            (out/f'path-{i:03}.bin').write_bytes(data)
            old=run(f'path-{i:03}-original',[out/'original_path_check'],data,(0,1))
            new=run(f'path-{i:03}-portable',[out/'portable_path_check'],data,(0,1))
            if (old.returncode,old.stdout)!=(new.returncode,new.stdout):raise RuntimeError('Path checker mismatch '+str(i))
            comparisons.append({'index':i,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'returncode':new.returncode,'edges':int(new.stdout)})
        (out/'path-check-cases.json').write_text(json.dumps(comparisons,indent=2)+'\n')
        report['original_path_harness_comparisons']=len(cases)
        common=[a.rvcc,'-march=rv32imac','-mabi=ilp32','-mstrict-align','-mno-relax','-std=c11','-Os',
                '-ffreestanding','-fno-builtin','-fno-jump-tables','-ffunction-sections','-fdata-sections',
                '-fstack-usage','-Wall','-Wextra','-Werror','-Wno-unused-function']
        for name in ('geometry','vector'):
            run('rv32-'+name,[*common,'-c',ROOT/(name+'.c'),'-o',out/(name+'.o')])
        prefix=str(a.rvcc).removesuffix('gcc')
        run('rv32-link',[prefix+'ld','-r',out/'geometry.o',out/'vector.o','-o',out/'vector-linked.o'])
        undefined=run('rv32-undefined',[prefix+'nm','-u',out/'vector-linked.o']).stdout.decode()
        if undefined.strip():raise RuntimeError('Unexpected RV32 imports '+undefined)
        run('rv32-sections',[prefix+'size','-A',out/'vector-linked.o'])
        run('rv32-vector-sections',[prefix+'size','-A',out/'vector.o'])
        report['rv32_undefined_symbols']=[]
        report['workspace_bytes']=10752;report['maximum_path_bytes']=8196
        report['tools']={'clang':run('clang-version',[a.cc,'--version']).stdout.decode().splitlines()[0],
                         'riscv_gcc':run('riscv-version',[a.rvcc,'--version']).stdout.decode().splitlines()[0]}
        report['artifact_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())
                                  if f.is_file() and (f.suffix in ('.o','.su') or f.name in ('test_vector','portable_path_check','original_path_check'))}
        report['result']='passed'
    except Exception as exc:
        report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('commands','portable_input_sha256','artifact_sha256')},indent=2))
    return 0 if report['result']=='passed' else 1


if __name__=='__main__':sys.exit(main())
