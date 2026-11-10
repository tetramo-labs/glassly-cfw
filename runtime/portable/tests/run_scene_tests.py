#!/usr/bin/env python3
"""Full original shape/vector assertions routed to portable scene/cache production."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fixtures-from',type=Path,help='Existing vector-fixture.bin, gif-300.bin, svg-300.bin; copied and hashed')
    parser.add_argument('--cc',default='clang')
    parser.add_argument('--rvcc',type=Path,default=REPO/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    reference=REPO/'tests/g2_compat/upstream';pin=json.loads((ROOT/'UPSTREAM.json').read_text())
    report={'format':'memomind-portable-scene-tests-v1','result':'failed','commands':[],
            'upstream_commit':pin['source_commit'],'hardware_tested':False,
            'scope':'Production portable scene/cache/assets + portable geometry/vector, original full host assertion bodies',
            'pending_boundary':'Native built-in font uses explicit callback; host retains unchanged upstream box-font stub'}
    def run(label,cmd,accepted=(0,)):
        result=subprocess.run([str(v) for v in cmd],capture_output=True)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label':label,'argv':[str(v) for v in cmd],'returncode':result.returncode})
        if result.returncode not in accepted:raise RuntimeError(label+' failed: see stdout/stderr')
        return result
    try:
        for name,digest in pin['files'].items():
            if name=='LICENSE':continue  # upstream license text not retained; repo is MIT
            if hashlib.sha256((reference/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source mismatch '+name)
        run('generated-source-check',[sys.executable,ROOT/'tests/prepare_scene_port.py','--check'])
        report['source_hashes_verified']=len(pin['files'])
        report['portable_source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ROOT.rglob('*')) if p.is_file() and p.suffix in ('.c','.h','.inc','.py','.json')}
        sys.path.insert(0,str(REPO/'tests/g2_compat'));from inventory import predicates
        original_assertions={}
        for filename in ('shapes_host_test.c','vector_host_test.c'):
            original=predicates((reference/'patches/host'/filename).read_text(),('CHECK',))
            port=predicates((ROOT/'tests/scene'/filename).read_text(),('CHECK',))
            if [p['expression'] for p in original]!=[p['expression'] for p in port]:raise RuntimeError('Changed predicate '+filename)
            original_assertions[filename]=[{'upstream_line':a['line'],'ported_line':b['line'],'expression':a['expression'],'sha256':a['sha256']} for a,b in zip(original,port)]
        (out/'assertion-map.json').write_text(json.dumps(original_assertions,indent=2)+'\n')
        report['original_check_sites']={name:len(values) for name,values in original_assertions.items()}
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT)]
        sources=[ROOT/'geometry.c',ROOT/'vector.c']
        run('build-original-suites-port',[args.cc,*flags,'-DMM_VECTOR_TESTING',ROOT/'tests/scene/vector_host_test.c',*sources,'-o',out/'test_scene'])
        result=run('original-suites-port',[out/'test_scene',out]);report['original_suite_result']=result.stdout.decode().strip()
        run('build-public-api',[args.cc,*flags,ROOT/'tests/scene/public_api_test.c',ROOT/'scene.c',*sources,'-o',out/'test_public_api'])
        result=run('public-api',[out/'test_public_api']);report['public_api_result']=result.stdout.decode().strip()
        if args.fixtures_from:
            report['fixture_replays']=[]
            for name in ('vector-fixture.bin','gif-300.bin','svg-300.bin'):
                origin=args.fixtures_from.resolve()/name;data=origin.read_bytes();copy=out/name;copy.write_bytes(data)
                result=run('replay-'+origin.stem,[out/'test_scene',out,copy])
                report['fixture_replays'].append({'file':str(origin),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'result':result.stdout.decode().strip()})
        else:report['fixture_replays']={'result':'not-run','reason':'Optional existing generated media corpus not supplied; not counted as pass'}
        layout_names=['context','platform','cache','transaction','object','asset','undo_base','undo_granule','vector_workspace']
        run('build-host-layout',[args.cc,*flags,'-DMM_SCENE_HOST_LAYOUT',ROOT/'tests/scene/layout.c',*sources,'-o',out/'host_layout'])
        result=run('host-layout',[out/'host_layout']);report['host_layout']=dict(zip(layout_names,map(int,result.stdout.split())))
        common=[args.rvcc,'-march=rv32imafc','-mabi=ilp32f','-mstrict-align','-mno-relax','-std=c11','-Os',
                '-ffreestanding','-fno-builtin','-fno-jump-tables','-ffunction-sections','-fdata-sections','-fstack-usage',
                '-Wall','-Wextra','-Werror','-Wno-unused-function']
        for name in ('geometry','vector','scene'):
            run('rv32-build-'+name,[*common,'-c',ROOT/(name+'.c'),'-o',out/(name+'.o')])
        prefix=str(args.rvcc).removesuffix('gcc')
        run('rv32-link',[prefix+'ld','-r',out/'scene.o',out/'geometry.o',out/'vector.o','-o',out/'scene-linked.o'])
        result=run('rv32-undefined',[prefix+'nm','-u',out/'scene-linked.o'])
        if result.stdout.strip():raise RuntimeError('Unresolved imports '+result.stdout.decode())
        run('rv32-sections',[prefix+'size','-A',out/'scene-linked.o'])
        run('rv32-scene-sections',[prefix+'size','-A',out/'scene.o'])
        run('rv32-layout-build',[*common,'-c',ROOT/'tests/scene/layout.c','-o',out/'layout.o'])
        run('rv32-layout-extract',[prefix+'objcopy','-O','binary','--only-section=.rodata.mm_scene_layout',out/'layout.o',out/'layout.bin'])
        report['rv32_layout']=dict(zip(layout_names,struct.unpack('<9I',(out/'layout.bin').read_bytes())))
        v=report['rv32_layout'];report['rv32_small_transaction_core_bytes']=v['cache']+65536+v['vector_workspace']+v['undo_base']+64*v['undo_granule']
        report['rv32_undefined_symbols']=[]
        report['tools']={'clang':run('clang-version',[args.cc,'--version']).stdout.decode().splitlines()[0],
                         'riscv_gcc':run('riscv-version',[args.rvcc,'--version']).stdout.decode().splitlines()[0]}
        report['artifact_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and (p.suffix in ('.o','.su','.bin') or p.name in ('test_scene','test_public_api','host_layout'))}
        report['result']='passed'
    except Exception as exc:report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('commands','portable_source_sha256','artifact_sha256')},indent=2))
    return 0 if report['result']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
