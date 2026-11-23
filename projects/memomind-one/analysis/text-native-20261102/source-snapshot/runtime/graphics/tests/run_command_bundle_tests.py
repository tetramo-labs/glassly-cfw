#!/usr/bin/env python3
"""ASan/UBSan bundle execution, exact pinned envelope branch and native collector."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    upstream=ROOT/'tests/g2_compat/upstream';pin=json.loads((upstream.parent/'UPSTREAM.json').read_text());source=(upstream/'patches/zlib_glue.c').read_text();assert hashlib.sha256(source.encode()).hexdigest()==pin['copied_files']['patches/zlib_glue.c']
    start=source.index('    if (mode == 8) {',source.index('static int image_dispatch(const uint8_t *src, uint32_t srclen, int present, cfw_rectlist *rl) {'));end=source.index('\n    if (mode == 9) {',start);branch=source[start:end]
    reference='''#include <stdint.h>
typedef int cfw_rectlist;
static unsigned ran,presents;static int fail;
static uint32_t rd16(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8);}
static void present_shadow(uint32_t w,uint32_t h,cfw_rectlist *rl){(void)w;(void)h;(void)rl;presents++;}
static int image_dispatch(const uint8_t *src,uint32_t srclen,int present,cfw_rectlist *rl){
 if(!src||!srclen)return -1;uint8_t mode=src[0]&127;uint32_t w=600,h=350;
'''+branch+'''
 if((int)ran==fail)return -1;ran++;return 0;
}
int g2_bundle_reference(const uint8_t *p,uint32_t n,int failure,unsigned *executed,unsigned *published){ran=presents=0;fail=failure;int rc=image_dispatch(p,n,1,0);*executed=ran;*published=presents;return rc;}
''';(out/'g2_bundle_reference.c').write_text(reference)
    mocks=(ROOT/'runtime/graphics/tests/test_graphics.c').read_text();mocks=mocks.replace('static void send(uint8_t event,void *response) {','static void mm_bundle_test_capture(uint8_t,const char *);\nstatic void send(uint8_t event,void *response) {').replace('last_event=event;sends++;strcpy(last_response,response);','last_event=event;sends++;strcpy(last_response,response);mm_bundle_test_capture(event,response);');(out/'bundle_mocks.c').write_text(mocks)
    sources=[ROOT/('runtime/'+n) for n in ('graphics/graphics.c','graphics/scene_session.c','graphics/native_text.c','portable/geometry.c','portable/vector.c','portable/scene.c','portable/rle.c','portable/raster_commands.c','portable/rect_copy_commands.c','graphics/tests/test_command_bundles.c')]
    paths=set(sources)|set((ROOT/'runtime/graphics').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.inc'))|{Path(__file__).resolve(),ROOT/'runtime/graphics/tests/test_graphics.c'}
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(paths)}
    report={'format':'memomind-command-bundles-host-v1','passed':False,'hardware_tested':False,'source_sha256':hashes,'original_branch_sha256':hashlib.sha256(branch.encode()).hexdigest(),'generated_mock_sha256':hashlib.sha256(mocks.encode()).hexdigest(),'commands':[]}
    def run(name,cmd):
        cmd=list(map(str,cmd));r=subprocess.run(cmd,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);report['commands'].append({'name':name,'argv':cmd,'returncode':r.returncode});r.check_returncode()
    try:
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_GRAPHICS_SCENE=1','-DMM_RASTER_COMMANDS=1','-DMM_RECT_COPY=1','-DMM_COMMAND_BUNDLES=1','-I'+str(ROOT/'runtime/portable'),'-I'+str(ROOT/'runtime/graphics'),'-DMM_BUNDLE_MOCKS_SOURCE="'+str(out/'bundle_mocks.c')+'"']
        run('build',['clang',*flags,*sources,out/'g2_bundle_reference.c','-o',out/'test_bundles']);run('host',[out/'test_bundles'])
        report['source_drift']=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h];assert not report['source_drift'];report['passed']=True
    except (AssertionError,OSError,subprocess.CalledProcessError) as e:report['error']=str(e)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256','commands')},indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
