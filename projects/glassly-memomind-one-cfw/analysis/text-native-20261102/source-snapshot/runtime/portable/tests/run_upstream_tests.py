#!/usr/bin/env python3
"""Original G2 upstream assertions against production portable core, plus RV32 audit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cc',default='clang')
    p.add_argument('--rvcc',type=Path,default=REPO/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    upstream=REPO/'tests/g2_compat/upstream';pin=json.loads((REPO/'tests/g2_compat/UPSTREAM.json').read_text())
    report={'format':'memomind-portable-upstream-tests-v1','result':'failed','commands':[],
            'upstream_commit':pin['commit'],'hardware_tested':False,
            'pending':['MemoMind native settings write/readback and user-facing semantics','Accessory battery source and lifecycle','Native heading source/diagnostics and stock-hook adapter','Native BLE scheduling/profile ownership; classic RFCOMM unaffected','Native extension routing/capability publication'],
            'source_sha256':{}}
    def run(label,cmd):
        result=subprocess.run(list(map(str,cmd)),capture_output=True)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label':label,'argv':list(map(str,cmd)),'returncode':result.returncode})
        if result.returncode:raise RuntimeError(label+' failed; see captured output')
        return result.stdout.decode()
    try:
        for name in ('LICENSE','patches/protobuf.c','patches/settings_ext.c','patches/zlib_glue.c','patches/ring_battery.c','patches/compass.c','patches/ble_link.c','patches/host/upstream_host_test.c'):
            digest=hashlib.sha256((upstream/name).read_bytes()).hexdigest()
            if digest!=pin['copied_files'][name]:raise RuntimeError('Upstream source mismatch '+name)
            report['source_sha256']['upstream/'+name]=digest
        sys.path.insert(0,str(REPO/'tests/g2_compat'));from inventory import predicates
        original=(upstream/'patches/host/upstream_host_test.c').read_text()
        port=(ROOT/'tests/upstream/upstream_host_test.c').read_text()
        old=predicates(original,('assert',));new=predicates(port,('assert',))
        if [x['expression'] for x in old]!=[x['expression'] for x in new]:raise RuntimeError('Changed original assert expressions')
        scenarios=['routing','batteries','settings','headings','ble_link']
        def function(text,name):
            match=re.search(r'\b'+name+r'\(void\)\s*\{',text)
            if not match:raise RuntimeError('Missing function '+name)
            start=match.start();end=match.end();depth=1
            while depth:
                depth+=(text[end]=='{')-(text[end]=='}');end+=1
            return text[start:end]
        original_main=function(original,'main');ported_main=function(port,'main')
        report['scenario_main_calls']={}
        for name in scenarios:
            if len(re.findall(r'static void '+name+r'\(void\)',port))!=1:raise RuntimeError('Missing/duplicate scenario '+name)
            calls=len(re.findall(r'\b'+name+r'\(\)\s*;',ported_main))
            if calls!=1 or len(re.findall(r'\b'+name+r'\(\)\s*;',original_main))!=1:raise RuntimeError('Missing/duplicate main call '+name)
            report['scenario_main_calls'][name]=calls
            expected=function(original,name)
            if expected!=function(port,name):raise RuntimeError('Changed scenario body '+name)
        mapping=[dict(upstream_line=x['line'],ported_line=y['line'],expression=x['expression'],sha256=x['sha256']) for x,y in zip(old,new)]
        (out/'assertion-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
        report['original_assert_sites']=len(old);report['original_scenarios']=scenarios
        files=[ROOT/'upstream.c',ROOT/'upstream.h',Path(__file__),*sorted((ROOT/'tests/upstream').glob('*'))]
        for file in files:
            if file.is_file():report['source_sha256'][str(file.relative_to(ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT)]
        run('build-original',[a.cc,*flags,ROOT/'tests/upstream/upstream_host_test.c',ROOT/'upstream.c','-o',out/'original'])
        report['original_result']=run('run-original',[out/'original']).strip()
        report['original_assert_evaluations']=int(re.search(r'assert evaluations: (\d+)',report['original_result'])[1])
        report['file_status']='mixed-portable-core-tested-native-adapter-pending'
        if report['original_assert_evaluations']!=25620:raise RuntimeError('Original scenario evaluation count changed')
        run('build-public',[a.cc,*flags,ROOT/'tests/upstream/public_api_test.c',ROOT/'upstream.c','-o',out/'public_api'])
        report['public_api_result']=run('run-public',[out/'public_api']).strip()
        common=[a.rvcc,'-march=rv32imafc','-mabi=ilp32f','-mstrict-align','-mno-relax','-std=c11','-Os','-ffreestanding','-fno-builtin','-fno-jump-tables','-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror','-I'+str(ROOT)]
        run('rv32-build',[*common,'-c',ROOT/'upstream.c','-o',out/'upstream.o'])
        prefix=str(a.rvcc).removesuffix('gcc')
        unresolved=run('rv32-undefined',[prefix+'nm','-u',out/'upstream.o'])
        if unresolved.strip():raise RuntimeError('Unresolved imports '+unresolved)
        sections=run('rv32-sections',[prefix+'size','-A',out/'upstream.o'])
        sizes={m[0]:int(m[1]) for m in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+',sections,re.M)}
        writable={name:size for name,size in sizes.items() if size and name.startswith(('.data','.bss','.sdata','.sbss','.tdata','.tbss'))}
        if writable:raise RuntimeError('Writable global sections '+str(writable))
        report['rv32']={'undefined_symbols':[],'writable_global_bytes':0,'text_bytes':sum(v for k,v in sizes.items() if k.startswith('.text')),'rodata_bytes':sum(v for k,v in sizes.items() if k.startswith('.rodata'))}
        stack=(out/'upstream.su').read_text();report['rv32']['stack_frames']=stack.splitlines()
        report['rv32']['max_individual_stack_bytes']=max(int(line.split('\t')[1]) for line in stack.splitlines())
        run('rv32-layout',[*common,'-c',ROOT/'tests/upstream/layout.c','-o',out/'layout.o'])
        run('rv32-layout-extract',[prefix+'objcopy','-O','binary','--only-section=.rodata.mm_upstream_layout',out/'layout.o',out/'layout.bin'])
        report['rv32']['layout']=dict(zip(('state_bytes','profile_bytes','sample_bytes','record_bytes','link_platform_bytes','extension_bytes','battery_bytes','capture_bytes'),struct.unpack('<8I',(out/'layout.bin').read_bytes())))
        report['tools']={'cc':run('cc-version',[a.cc,'--version']).splitlines()[0],'rvcc':run('rvcc-version',[a.rvcc,'--version']).splitlines()[0]}
        report['artifact_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and (p.suffix in ('.o','.bin','.su') or p.name in ('original','public_api'))}
        report['result']='passed'
    except Exception as exc:report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('commands','source_sha256','artifact_sha256')},indent=2))
    return report['result']!='passed'
if __name__=='__main__':raise SystemExit(main())
