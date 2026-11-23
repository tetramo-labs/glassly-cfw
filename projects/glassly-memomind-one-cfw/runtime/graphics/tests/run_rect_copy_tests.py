#!/usr/bin/env python3
"""Mode9 sanitizer differential against the exact pinned G2 copy function."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    upstream=ROOT/'tests/g2_compat/upstream';pin=json.loads((upstream.parent/'UPSTREAM.json').read_text());source=(upstream/'patches/draw.c').read_text()
    assert hashlib.sha256(source.encode()).hexdigest()==pin['copied_files']['patches/draw.c']
    start=source.index('static void rect_copy_4bpp(');end=source.index('\n}\n',start)+3;function=source[start:end]
    ref='#include <stdint.h>\n#include <string.h>\n'+function+'\nvoid g2_rect_copy_reference(uint8_t *p,uint32_t stride,uint32_t sx,uint32_t sy,uint32_t dx,uint32_t dy,uint32_t w,uint32_t h){rect_copy_4bpp(p,stride,sx,sy,dx,dy,w,h);}\n';(out/'original_copy.c').write_text(ref)
    sources=[ROOT/('runtime/'+n) for n in ('graphics/graphics.c','graphics/scene_session.c','graphics/native_text.c','portable/geometry.c','portable/vector.c','portable/scene.c','portable/rle.c','portable/raster_commands.c','portable/rect_copy_commands.c','graphics/tests/test_rect_copy.c')]
    paths=set(sources)|set((ROOT/'runtime/graphics').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.inc'))|{Path(__file__).resolve(),ROOT/'runtime/graphics/tests/test_graphics.c'}
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(paths)}
    report={'format':'memomind-rect-copy-host-v1','passed':False,'hardware_tested':False,'source_sha256':hashes,'original_function_sha256':hashlib.sha256(function.encode()).hexdigest(),'commands':[]}
    def run(name,cmd):
        cmd=list(map(str,cmd));r=subprocess.run(cmd,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);report['commands'].append({'name':name,'argv':cmd,'returncode':r.returncode});r.check_returncode()
    try:
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_GRAPHICS_SCENE=1','-DMM_RASTER_COMMANDS=1','-DMM_RECT_COPY=1','-I'+str(ROOT/'runtime/portable'),'-I'+str(ROOT/'runtime/graphics')]
        run('build',['clang',*flags,*sources,out/'original_copy.c','-o',out/'test_rect_copy']);run('host',[out/'test_rect_copy'])
        report['source_drift']=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h];assert not report['source_drift'];report['passed']=True
    except (AssertionError,OSError,subprocess.CalledProcessError) as e:report['error']=str(e)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256','commands')},indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
