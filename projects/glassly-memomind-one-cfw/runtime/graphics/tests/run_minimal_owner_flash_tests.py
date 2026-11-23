#!/usr/bin/env python3
"""Rebuild and validate the minimal launcher, COW scene and bounded carrier."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
FLAGS=['--scene-session','--input-observer','--flash-reader','--external-tail-reader','--storage-diagnostics','--full-store-reader','--flash-canary','--raster-commands','--rect-copy','--command-bundles','--text-commands','--diagnostic-commands','--reset-undo-trim','--minimal-launcher','--flash-scene','--rx-profile','app-rx-96k-v1']
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--wake-control',action='store_true');p.add_argument('--rv32-python',type=Path,default=ROOT/'.tools/rv32-tests-venv/bin/python');a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);report={'passed':False,'hardware_tested':False,'commands':[]}
 def run(name,cmd):
  cmd=list(map(str,cmd));r=subprocess.run(cmd,cwd=ROOT,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);report['commands'].append({'name':name,'argv':cmd,'returncode':r.returncode});r.check_returncode()
 try:
  common=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'runtime/graphics'),'-I'+str(ROOT/'runtime/portable')]
  run('large-build',[*common,'runtime/graphics/large_message.c','runtime/graphics/tests/test_large_message.c','-o',out/'large'])
  run('large',[out/'large'])
  run('broker-build',[*common,'-DMM_FLASH_BROKER_TEST=1','-DMM_FLASH_NATIVE_HOST_TEST=1','runtime/graphics/tests/test_flash_broker.c','runtime/graphics/flash_store_native.c','runtime/portable/flash_store.c','-o',out/'broker'])
  for n in [0,1,2,3,4,11,12]:run('broker-'+str(n),[out/'broker',n])
  if a.wake_control:
   run('wake-build',[*common,'runtime/portable/wake.c','runtime/portable/tests/test_wake.c','-o',out/'wake'])
   run('wake-host',[out/'wake'])
  run('compile',[sys.executable,'scripts/compile_memomind_graphics.py',out/'build',*FLAGS,*(['--wake-control'] if a.wake_control else [])])
  run('construct',[sys.executable,'scripts/build_memomind_minimal_owner.py','captures/firmware/ota-1.0.3.127-glassly-text.bin',out/'build',out/'candidate'])
  run('queue-abi',[a.rv32_python,'tests/rv32/flash_broker_queue_abi_test.py','--build',out/'build','--image',out/'candidate/firmware.bin','--report',out/'queue-abi.json'])
  run('rv32',[a.rv32_python,'tests/rv32/minimal_owner_flash_runtime_emulator_test.py','--build',out/'build','--report',out/'rv32.json'])
  run('asset-display',[a.rv32_python,'tests/rv32/flash_asset_display_test.py','--build',out/'build','--report',out/'asset-display.json'])
  run('native-callers',[a.rv32_python,'tests/rv32/minimal_launcher_native_callers_test.py','--build',out/'build','--image',out/'candidate/firmware.bin','--report',out/'native-callers.json'])
  if a.wake_control:
   for name,script in [('wake-runtime','wake_control_runtime_emulator_test.py'),('wake-gates','wake_control_gate_emulator_test.py'),('retained-commands','minimal_owner_flash_commands_test.py')]:
    run(name,[a.rv32_python,'tests/rv32/'+script,'--build',out/'build','--report',out/(name+'.json')])
   run('wake-native',[a.rv32_python,'tests/rv32/wake_native_abi_test.py','--build',out/'build','--image',out/'candidate/firmware.bin','--report',out/'wake-native.json'])
  build=json.loads((out/'build/build.json').read_text());report['runtime_sha256']=build['blob_sha256'];report['image_sha256']=hashlib.sha256((out/'candidate/firmware.bin').read_bytes()).hexdigest()
  report['source_drift']=[n for n,h in build['source_sha256'].items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h]
  assert not report['source_drift'];report['passed']=True
 except (OSError,ValueError,AssertionError,subprocess.CalledProcessError) as e:report['error']=str(e)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
