#!/usr/bin/env python3
"""Pinned G2 transport assertions on production portable parser; host-only zlib/routing."""
import argparse,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--cc',default='clang')
    ap.add_argument('--rvcc',type=Path,default=REPO/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    upstream=REPO/'tests/g2_compat/upstream';pin=json.loads((REPO/'tests/g2_compat/UPSTREAM.json').read_text())
    report={'format':'memomind-portable-transport-tests-v1','result':'failed','upstream_commit':pin['commit'],'commands':[],'hardware_tested':False,'source_sha256':{},'pending':['Native GM transport adapter, ordering, backpressure, link limits and teardown','Native allocator/budget and handler execution context','Native RFC1950 inflater availability/ABI and integration','Logical destination mapping; MemoMind dual-lens topology is not assumed']}
    def run(label,cmd):
        r=subprocess.run(list(map(str,cmd)),capture_output=True)
        (out/(label+'.stdout')).write_bytes(r.stdout);(out/(label+'.stderr')).write_bytes(r.stderr)
        report['commands'].append({'label':label,'argv':list(map(str,cmd)),'returncode':r.returncode})
        if r.returncode:raise RuntimeError(label+' failed; inspect logs')
        return r.stdout.decode()
    try:
        for name in ['LICENSE','patches/message_transport.c','patches/message_transport.h','patches/transport_compression.c','patches/cfw_context.h','patches/host/transport_host_test.c']:
            digest=hashlib.sha256((upstream/name).read_bytes()).hexdigest()
            if digest!=pin['copied_files'][name]:raise RuntimeError('Upstream mismatch '+name)
            report['source_sha256']['upstream/'+name]=digest
        run('check-original-binding',[sys.executable,ROOT/'tests/transport/prepare_original.py','--check'])
        sys.path.insert(0,str(REPO/'tests/g2_compat'));from inventory import predicates
        original=(upstream/'patches/host/transport_host_test.c').read_text();port=(ROOT/'tests/transport/transport_host_test.c').read_text()
        old=predicates(original,('assert',));new=predicates(port,('assert',))
        if [v['expression'] for v in old]!=[v['expression'] for v in new]:raise RuntimeError('Original assert expressions changed')
        scenarios=['subset_records','outside_records','compressed_records','skipped_reset_is_not_borrowed','handler_failure']
        for name in scenarios:
            # All five original scenario bodies remain exactly unchanged.
            pat=r'static void '+name+r'\([^)]*\) \{[\s\S]*?\n\}'
            if re.search(pat,original)[0]!=re.search(pat,port)[0]:raise RuntimeError('Scenario changed '+name)
        if original[original.index('static const uint8_t LEFT_MSG'):original.index('/* A both-lens')] != port[port.index('static const uint8_t LEFT_MSG'):port.index('/* A both-lens')]:raise RuntimeError('Fixtures changed')
        mapping=[dict(upstream_line=x['line'],ported_line=y['line'],expression=x['expression'],sha256=x['sha256']) for x,y in zip(old,new)]
        (out/'assertion-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
        report['original_assert_sites']=len(old);report['original_scenarios']=scenarios
        report['boundaries']={'production':'transport.c record parser/state/CRC/ACK/reply algorithms','test_only':['G2 BLE/TPL outer-frame validation','Two simulated endpoints and private bridge envelopes','Stock hook passthrough stubs','Host zlib compression/decompression']}
        for file in [ROOT/'transport.c',ROOT/'transport.h',ROOT/'TRANSPORT.md',Path(__file__),*sorted((ROOT/'tests/transport').glob('*'))]:
            if file.is_file():report['source_sha256'][str(file.relative_to(ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT)]
        for label,file in [('original','transport_host_test.c'),('public','public_api_test.c')]:
            run('build-'+label,[a.cc,*flags,ROOT/'tests/transport'/file,ROOT/'transport.c','-lz','-o',out/label]);report[label+'_result']=run('run-'+label,[out/label]).strip()
        common=[a.rvcc,'-march=rv32imafc','-mabi=ilp32f','-mstrict-align','-mno-relax','-std=c11','-Os','-ffreestanding','-fno-builtin','-fno-jump-tables','-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror','-I'+str(ROOT)]
        run('rv32-build',[*common,'-c',ROOT/'transport.c','-o',out/'transport.o']);prefix=str(a.rvcc).removesuffix('gcc')
        undefined=run('rv32-undefined',[prefix+'nm','-u',out/'transport.o'])
        if undefined.strip():raise RuntimeError('Unresolved imports '+undefined)
        sec=run('rv32-sections',[prefix+'size','-A',out/'transport.o']);sizes={m[0]:int(m[1]) for m in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+',sec,re.M)}
        writable={k:v for k,v in sizes.items() if v and k.startswith(('.data','.bss','.sdata','.sbss','.tdata','.tbss'))}
        if writable:raise RuntimeError('Writable globals '+str(writable))
        stack=(out/'transport.su').read_text();report['rv32']={'undefined_symbols':[],'writable_global_bytes':0,'text_bytes':sum(v for k,v in sizes.items() if k.startswith('.text')),'rodata_bytes':sum(v for k,v in sizes.items() if k.startswith('.rodata')),'stack_frames':stack.splitlines(),'max_individual_stack_bytes':max(int(x.split('\t')[1]) for x in stack.splitlines())}
        run('rv32-layout',[*common,'-c',ROOT/'tests/transport/layout.c','-o',out/'layout.o']);run('rv32-layout-extract',[prefix+'objcopy','-O','binary','--only-section=.rodata.mm_transport_layout',out/'layout.o',out/'layout.bin'])
        report['rv32']['layout']=dict(zip(('context_bytes','stream_bytes','platform_bytes'),struct.unpack('<3I',(out/'layout.bin').read_bytes())))
        report['tools']={'cc':run('cc-version',[a.cc,'--version']).splitlines()[0],'rvcc':run('rvcc-version',[a.rvcc,'--version']).splitlines()[0]}
        report['artifact_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and (p.suffix in ('.o','.bin','.su') or p.name in ('original','public'))}
        report['result']='passed'
    except Exception as exc:report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('commands','source_sha256','artifact_sha256')},indent=2));return report['result']!='passed'
if __name__=='__main__':raise SystemExit(main())
