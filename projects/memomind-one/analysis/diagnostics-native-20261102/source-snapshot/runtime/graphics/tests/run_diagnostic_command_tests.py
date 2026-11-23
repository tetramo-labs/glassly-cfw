#!/usr/bin/env python3
"""Exact pinned G2 FID/control differential and native owner ASan/UBSan model."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 spec=importlib.util.spec_from_file_location('inventory',ROOT/'tests/g2_compat/inventory.py');inv=importlib.util.module_from_spec(spec);spec.loader.exec_module(inv)
 pin=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text());parts={}
 for name in ['debug.c','zlib_glue.c']:
  f=ROOT/'tests/g2_compat/upstream/patches'/name;s=f.read_text();assert hashlib.sha256(f.read_bytes()).hexdigest()==pin['copied_files']['patches/'+name];parts[name]=s
 frame,_,_=inv.function(parts['debug.c'],'cfw_diag');s=parts['zlib_glue.c'];start=s.index('    if (mode == 7) {');end=s.index('    if (mode == 10) {',start);branch=s[start:end]
 ref='''#include <stdint.h>
#define CFW_FID_RING 16
typedef struct {uint8_t f_reorder,f_skip,f_dup,diag_hide,diag_seen,fid_resync,recent_pos;uint16_t last_fid,high_fid,recent_fids[16];uint32_t nack_count,nack_reason,worker_fail_count,worker_fail_mode,alloc_fail_count,alloc_fail_bytes,alloc_fail_heap,gate_timeouts;} customCfwContext;
static customCfwContext ctx={.diag_hide=1};
static customCfwContext *getCustomCfwContext(void){return &ctx;}
static void cfw_alloc_diag_clear(void){}
'''+frame+'''\nvoid g2_reference_frame(int has,uint16_t fid){cfw_diag(has,fid);}
static int dispatch(const uint8_t *src,uint32_t srclen){unsigned mode=7;
'''+branch+'''return -1;}
void g2_reference_control(unsigned sub){uint8_t src[2]={7,(uint8_t)sub};dispatch(src,2);}
void g2_reference_snapshot(uint32_t *r){r[0]=ctx.f_reorder;r[1]=ctx.f_skip;r[2]=ctx.f_dup;r[3]=ctx.diag_hide;r[4]=ctx.diag_seen;r[5]=ctx.fid_resync;r[6]=ctx.last_fid;r[7]=ctx.high_fid;r[8]=ctx.recent_pos;for(unsigned i=0;i<16;i++)r[9+i]=ctx.recent_fids[i];}
''';(out/'reference.c').write_text(ref)
 paths=[ROOT/'runtime/graphics/tests/test_diagnostic_commands.c',ROOT/'runtime/graphics/diagnostics.c',ROOT/'runtime/graphics/diagnostics.h',ROOT/'runtime/graphics/graphics.h',Path(__file__).resolve()];hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 report={'passed':False,'hardware_tested':False,'source_sha256':hashes,'original_frame_sha256':hashlib.sha256(frame.encode()).hexdigest(),'original_control_branch_sha256':hashlib.sha256(branch.encode()).hexdigest(),'scope':'standalone diagnostic owner and actual G2 state machine; full graphics/input command integration not yet covered'}
 try:
  for name,cmd in [('build',['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_DIAGNOSTIC_COMMANDS=1','-I'+str(ROOT/'runtime/graphics'),'-I'+str(ROOT/'runtime/portable'),str(paths[0]),str(out/'reference.c'),'-o',str(out/'test_diagnostics')]),('host',[str(out/'test_diagnostics')])]:
   r=subprocess.run(cmd,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);r.check_returncode()
  report['source_drift']=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h];assert not report['source_drift'];report['passed']=True
 except (AssertionError,OSError,subprocess.CalledProcessError) as e:report['error']=str(e)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
