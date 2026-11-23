#!/usr/bin/env python3
"""Full optional flash scene backend: sanitizer differentials and RV32 audit."""
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
FIXTURES={
 'vector-fixture.bin':'dbeab3248f1259a06faec40e9c83f0fedc12c674cce7d864f577ca8e1c84d269',
 'gif-300.bin':'d8706a134a268e8ada75a4edd81356eea8d932f48f271c5f2c368f3aef744687',
 'svg-300.bin':'7dc551a4ee22e4cdc1182bb49586889980a6fa1e24f24c905d8cd2d19a6cee1b'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--fixtures-from',required=True,type=Path);p.add_argument('--cc',default='clang');p.add_argument('--rvcc',type=Path,default=REPO/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc');a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 names=('scene','scene_store','scene_flash_store','flash_store','geometry','vector')
 inputs=[*sorted(ROOT.glob('scene*')),*[ROOT/(n+'.'+ext) for n in ('vector','geometry','flash_store') for ext in ('c','h')],Path(__file__),ROOT/'tests/prepare_scene_port.py',*sorted((ROOT/'tests/scene_store').glob('*'))]
 inputs=[x for x in inputs if x.is_file()];before={str(x.relative_to(ROOT)):sha(x) for x in inputs}
 report={'format':'memomind-scene-store-tests-v1','result':'failed','hardware_tested':False,'commands':[],'source_sha256':before,
  'scope':'MM_SCENE_EXTERNAL_STORE optional portable backend; actual production core, mocked physical callbacks',
  'limits':['No native reservation or hardware binding','No full65535 native ingress/inflater integration','Shared framebuffer may be partially modified on render I/O failure; shadow_invalid forbids presentation until redraw','Measured individual stack frames exclude full native call chains']}
 def run(label,cmd):
  cmd=list(map(str,cmd));r=subprocess.run(cmd,capture_output=True);(out/(label+'.stdout')).write_bytes(r.stdout);(out/(label+'.stderr')).write_bytes(r.stderr);report['commands'].append({'label':label,'argv':cmd,'returncode':r.returncode})
  if r.returncode:raise RuntimeError(label+' failed; inspect captured stdout/stderr')
  return r.stdout.decode()
 try:
  run('generated-check',[sys.executable,ROOT/'tests/prepare_scene_port.py','--check'])
  fixtures=[]
  for name,digest in FIXTURES.items():
   source=a.fixtures_from.resolve()/name
   if sha(source)!=digest:raise RuntimeError('Changed fixture '+name)
   copy=out/name;copy.write_bytes(source.read_bytes());fixtures.append(copy)
  report['fixtures_sha256']=FIXTURES
  host=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_SCENE_EXTERNAL_STORE=1','-I'+str(ROOT)]
  run('host-build',[a.cc,*host,ROOT/'tests/scene_store/test_scene_store.c',*[ROOT/(n+'.c') for n in names if n!='scene'],'-o',out/'test_scene_store'])
  run('reader-build',[a.cc,*host,ROOT/'tests/scene_store/test_reader.c',ROOT/'scene_store.c','-o',out/'test_reader'])
  report['reader_result']=run('reader-run',[out/'test_reader']).strip()
  report['host_result']=run('host-run',[out/'test_scene_store',*fixtures]).strip()
  for required in ('reader-owner-aliases=8 initializer-backend-aliases=2 unchanged-on-rejection=yes','messages=24 probes=21','messages=302 probes=7200','fullcapacity=262144 fullmessage=65535 callback_faults=528','asset_faults=33 render_faults=13','external-render cases=4000','paths=512edges/8196bytes scene_edges=4096','PASS scene-store differential and transaction failures'):
   if required not in report['host_result']:raise RuntimeError('Missing coverage: '+required)
  common=['-march=rv32imafc','-mabi=ilp32f','-mstrict-align','-mno-relax','-msmall-data-limit=0','-std=c11','-O2','-ffreestanding','-fno-builtin','-fno-common','-fno-pic','-fno-pie','-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror','-Wno-unused-function','-DMM_SCENE_EXTERNAL_STORE=1','-I'+str(ROOT)]
  prefix=str(a.rvcc).removesuffix('gcc')
  for name in names:run('rv32-build-'+name,[a.rvcc,*common,'-c',ROOT/(name+'.c'),'-o',out/(name+'.o')])
  run('rv32-link',[prefix+'ld','-r',*[out/(n+'.o') for n in names],'-o',out/'scene-store-linked.o'])
  header=run('rv32-header',[prefix+'readelf','-h',out/'scene-store-linked.o'])
  if not re.search(r'Class:\s+ELF32',header) or not re.search(r'Machine:\s+RISC-V',header) or 'little endian' not in header:raise RuntimeError('Not actual RV32 LE ELF')
  undefined=run('rv32-undefined',[prefix+'nm','-u',out/'scene-store-linked.o'])
  if undefined.strip():raise RuntimeError('Undefined imports '+undefined)
  sections=run('rv32-sections',[prefix+'size','-A',out/'scene-store-linked.o'])
  sizes={k:int(v) for k,v in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+',sections,re.M)}
  writable={k:v for k,v in sizes.items() if v and k.startswith(('.data','.bss','.sdata','.sbss','.tdata','.tbss'))}
  if writable:raise RuntimeError('Writable globals '+str(writable))
  stacks=[line for name in names for line in (out/(name+'.su')).read_text().splitlines()]
  if any(line.split('\t')[2]!='static' for line in stacks):raise RuntimeError('Dynamic stack entry')
  maximum=max(int(line.split('\t')[1]) for line in stacks)
  if maximum>768:raise RuntimeError('Individual stack frame exceeds768B review bound')
  run('rv32-disassembly',[prefix+'objdump','-dr',out/'scene-store-linked.o'])
  run('rv32-layout',[a.rvcc,*common,'-c',ROOT/'tests/scene/layout.c','-o',out/'layout.o'])
  run('rv32-layout-extract',[prefix+'objcopy','-O','binary','--only-section=.rodata.mm_scene_layout',out/'layout.o',out/'layout.bin'])
  layout=dict(zip(('context','platform','cache','transaction','object','asset','undo_base','undo_granule','vector_workspace'),struct.unpack('<9I',(out/'layout.bin').read_bytes())))
  report['rv32']={'architecture':'RV32IMAFC ilp32f little endian','undefined_symbols':[],'writable_globals_bytes':0,'text_bytes':sum(v for k,v in sizes.items() if k.startswith('.text')),'rodata_bytes':sum(v for k,v in sizes.items() if k.startswith('.rodata')),'layout':layout,'stack_frames':stacks,'max_individual_stack_bytes':maximum}
  if before!={str(x.relative_to(ROOT)):sha(x) for x in inputs}:raise RuntimeError('Source drift during validation')
  report['source_drift']=False;report['tools']={'cc':run('cc-version',[a.cc,'--version']).splitlines()[0],'rvcc':run('rvcc-version',[a.rvcc,'--version']).splitlines()[0]}
  report['artifact_sha256']={x.name:sha(x) for x in out.iterdir() if x.is_file() and (x.suffix in ('.o','.su','.bin') or x.name=='test_scene_store')};report['result']='passed'
 except Exception as exc:report['error']=str(exc)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('commands','source_sha256','artifact_sha256')},indent=2));return report['result']!='passed'
if __name__=='__main__':raise SystemExit(main())
