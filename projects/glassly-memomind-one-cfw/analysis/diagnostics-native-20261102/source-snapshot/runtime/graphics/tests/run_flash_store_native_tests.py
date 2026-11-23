#!/usr/bin/env python3
"""Sanitizer, real RV32 build/import audit, and actual adapter machine tests."""
import argparse,hashlib,json,re,struct,subprocess,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 files=[ROOT/x for x in ['runtime/graphics/flash_store_native.c','runtime/graphics/flash_store_native.h','runtime/portable/flash_store.h',
  'runtime/graphics/tests/flash_store_native/test_flash_store_native.c','runtime/graphics/tests/flash_store_native/layout.c',
  'runtime/graphics/tests/run_flash_store_native_tests.py','tests/rv32/flash_store_native_emulator_test.py']]
 hashes={str(x.relative_to(ROOT)):sha(x) for x in files}
 report={'format':'memomind-native-flash-binding-tests-v1','passed':False,'device_actions':False,'source_sha256':hashes,'commands':[],
 'limitations':['Four native APIs mocked; no actual flash/cache hardware, waits or concurrent ownership proof.',
 'Host test seam bypasses numeric SRAM-range check; actual RV32 execution tests that production check.',
 'No task/queue creation, integration, native badmap acquisition or physical reservation established.']}
 def run(label,args):
  args=list(map(str,args));r=subprocess.run(args,capture_output=True,text=True);(out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
  report['commands'].append({'label':label,'argv':args,'returncode':r.returncode})
  if r.returncode:raise RuntimeError(label+' failed')
  return r.stdout
 status=1
 try:
  if not __debug__:raise RuntimeError('Assertions must be enabled')
  app=ROOT/'analysis/extracted/validated-1.0.3.127/segment-3.body.bin'
  if sha(app)!='81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8':raise RuntimeError('Pinned native ABI source mismatch')
  report['native_abi_source_sha256']=sha(app)
  report['native_abi_evidence_sha256']={str(x.relative_to(ROOT)):sha(x) for x in [ROOT/'analysis/ghidra/external-xip-review/report.md', ROOT/'analysis/ghidra/external-xip-review/byte-witnesses.json']}
  c=ROOT/'runtime/graphics/flash_store_native.c';test=ROOT/'runtime/graphics/tests/flash_store_native'
  includes=['-I'+str(ROOT/'runtime/graphics'),'-I'+str(ROOT/'runtime/portable')]
  run('host-build',['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_FLASH_NATIVE_HOST_TEST',*includes,c,test/'test_flash_store_native.c','-o',out/'host-test'])
  report['host_result']=run('host-run',[out/'host-test']).strip()
  if not re.search(r'PASS checks=\d+ sectors=256 pages=4096 badbits=256 erase_readback_faults=16 context_bytes=300',report['host_result']):raise RuntimeError('Host coverage incomplete')
  cc=ROOT/'.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc';prefix=str(cc).removesuffix('gcc')
  version=run('rv32-version',[cc,'--version']).splitlines()[0]
  if '15.2.0' not in version:raise RuntimeError('Unexpected compiler version')
  flags=['-march=rv32imafc','-mabi=ilp32f','-mstrict-align','-mno-relax','-msmall-data-limit=0','-mcmodel=medany','-std=c11','-O2','-ffreestanding','-fno-builtin','-fno-common','-fno-pic','-fno-pie','-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror',*includes]
  run('rv32-build',[cc,*flags,'-c',c,'-o',out/'adapter.o'])
  undef=run('rv32-undefined',[prefix+'nm','-u',out/'adapter.o']);assert not undef.strip(),undef
  symbols=run('rv32-symbols',[prefix+'nm','--defined-only',out/'adapter.o']);assert not re.search(r'^\w+\s+[BbCcDdGgSsVv]\s+',symbols,re.M)
  elf=run('rv32-header',[prefix+'readelf','-h',out/'adapter.o']);assert re.search(r'Class:\s+ELF32',elf) and re.search(r'Machine:\s+RISC-V',elf) and 'little endian' in elf
  sections=run('rv32-size',[prefix+'size','-A',out/'adapter.o']);sizes={n:int(z) for n,z in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+',sections,re.M)}
  assert not any(v for n,v in sizes.items() if n.startswith(('.data','.bss','.sdata','.sbss','.tdata','.tbss')))
  stack=(out/'adapter.su').read_text().splitlines();assert stack and all(x.split('\t')[2]=='static' for x in stack)
  maximum=max(int(x.split('\t')[1])for x in stack);assert maximum<=128
  run('rv32-layout-build',[cc,*flags,'-c',test/'layout.c','-o',out/'layout.o'])
  run('rv32-layout-extract',[prefix+'objcopy','-O','binary','--only-section=.rodata.mm_flash_native_layout',out/'layout.o',out/'layout.bin'])
  layout=dict(zip(['context_bytes','status_offset','verification_offset','busy_offset','phase_offset'],struct.unpack('<5I',(out/'layout.bin').read_bytes())))
  assert list(layout.values())==[300,4,40,296,297],layout
  run('rv32-link',[cc,*flags,'-nostdlib','-Wl,-Ttext=0x043b0000,--no-relax,-e,mm_flash_native_init',out/'adapter.o','-o',out/'adapter.elf'])
  run('rv32-binary',[prefix+'objcopy','-O','binary',out/'adapter.elf',out/'adapter.bin'])
  nm=run('rv32-linked-symbols',[prefix+'nm','--defined-only',out/'adapter.elf'])
  syms={name:int(address,16) for address,name in re.findall(r'^(\w+)\s+[Tt]\s+(\w+)',nm,re.M)}
  run('rv32-disassembly',[prefix+'objdump','-dr',out/'adapter.elf'])
  build={'source_sha256':hashes,'binary_sha256':sha(out/'adapter.bin'),'symbols':syms,'layout':layout,'compiler':version,'base':0x043b0000}
  (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
  run('rv32-execute',[ROOT/'.tools/rv32-tests-venv/bin/python',ROOT/'tests/rv32/flash_store_native_emulator_test.py','--build',out,'--output',out/'emulation'])
  machine=json.loads((out/'emulation/report.json').read_text());assert machine['passed']
  report['rv32']={'layout':layout,'max_individual_stack_bytes':maximum,'stack_frames':stack,'undefined_symbols':[], 'writable_global_bytes':0,'binary_sha256':build['binary_sha256'],'binary_bytes':(out/'adapter.bin').stat().st_size,'checks':machine['case_count']}
  after={str(x.relative_to(ROOT)):sha(x) for x in files};assert after==hashes,'source drift'
  report['passed']=True;report['source_drift']=[];status=0
 except Exception as exc:report.update(error=str(exc),traceback=traceback.format_exc())
 finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'passed':status==0,'report':str(out/'report.json'),'host':report.get('host_result')}));return status
if __name__=='__main__':raise SystemExit(main())
