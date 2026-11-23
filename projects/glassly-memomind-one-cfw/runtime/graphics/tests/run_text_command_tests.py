#!/usr/bin/env python3
"""Real G2 builtin function differential, native font and queued mode15 under ASan/UBSan."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('inventory',ROOT/'tests/g2_compat/inventory.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    pin=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text());parts=[];rows=[]
    requested={'patches/utils.c':['bzero','rd16'],'patches/texture_cache.c':['cfw_texture_make_lut','cfw_texture_render_a4','cfw_texture_add_rect','cfw_texture_utf8','cfw_texture_next_glyph','cfw_texture_s16','cfw_texture_s32','cfw_builtin_glyph','cfw_builtin_draw_string_buf','cfw_builtin_draw_string']}
    for name,functions in requested.items():
        path=ROOT/'tests/g2_compat/upstream'/name;source=path.read_text();assert hashlib.sha256(path.read_bytes()).hexdigest()==pin['copied_files'][name]
        for f in functions:
            body,lo,hi=mod.function(source,f);parts.append(body);rows.append({'function':f,'source':name,'lines':[lo,hi],'sha256':hashlib.sha256(body.encode()).hexdigest()})
    texture=(ROOT/'tests/g2_compat/upstream/patches/texture_cache.c').read_text()
    defines='\n'.join(line for line in texture.splitlines() if line.startswith('#define CFW_') and not line.startswith(('#define CFW_FONT_GET_','#define CFW_FONT_RELEASE','#define CFW_FONT20_ROOT')))
    prefix='''#include <stdint.h>
/* Synthetic equivalent3x2 glyph: Memo2bpp1b90 -> G2A4-aligned05a0/fa50. */
typedef int cfw_rectlist;
static const uint8_t mock_font[20]={[12]=4,[16]=1},bits[]={0x05,0xa0,0xfa,0x50};
static int cfw_fb_lease_active(void){return 1;}
static void rl_add(cfw_rectlist *r,uint32_t x,uint32_t y,uint32_t w,uint32_t h){(void)r;(void)x;(void)y;(void)w;(void)h;}
static int mock_metrics(const void *f,void *out,uint32_t cp,uint32_t next){(void)f;(void)next;uint8_t *d=out;d[0]=1;d[4]=3;d[6]=cp==32?0:3;d[8]=cp==32?0:2;d[14]=0x14;return 1;}
static const uint8_t *mock_bitmap(void *d,void *buf){(void)d;(void)buf;return bits;}
static void mock_release(void *d){(void)d;}
#define CFW_FONT_GET_DSC mock_metrics
#define CFW_FONT_GET_BITMAP mock_bitmap
#define CFW_FONT_RELEASE mock_release
#define CFW_FONT20_ROOT mock_font
'''
    reference=prefix+defines+'\n'+'\n\n'.join(parts)+'''\nint g2_text_reference(uint8_t *p,uint32_t stride,uint32_t w,uint32_t h,const uint8_t *src,uint32_t n){return cfw_builtin_draw_string(p,stride,w,h,src,n,0);}\n'''
    (out/'g2_text_reference.c').write_text(reference)
    graphics=(ROOT/'runtime/graphics/graphics.c').read_text();needle='return mm_native_builtin_text(0,raster,data,size,dirty,tokens,count);';assert graphics.count(needle)==1
    graphics=graphics.replace(needle,'extern const mm_native_text_api mm_text_test_api;\n    return mm_native_builtin_text((void *)&mm_text_test_api,raster,data,size,dirty,tokens,count);');(out/'graphics_injected.c').write_text(graphics)
    originals=[ROOT/('runtime/'+n) for n in ['graphics/graphics.c','graphics/scene_session.c','graphics/native_text.c','portable/geometry.c','portable/vector.c','portable/scene.c','portable/rle.c','portable/raster_commands.c','portable/rect_copy_commands.c','graphics/tests/test_text_commands.c','graphics/tests/test_native_text.c','graphics/tests/test_graphics.c']]
    paths=set(originals)|set((ROOT/'runtime/graphics').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.inc'))|{Path(__file__).resolve()}
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(paths)}
    sources=[out/'graphics_injected.c',*originals[1:10],out/'g2_text_reference.c']
    flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_GRAPHICS_SCENE=1','-DMM_RASTER_COMMANDS=1','-DMM_RECT_COPY=1','-DMM_COMMAND_BUNDLES=1','-DMM_TEXT_COMMANDS=1','-I'+str(ROOT/'runtime/portable'),'-I'+str(ROOT/'runtime/graphics')]
    report={'format':'memomind-text-command-host-v1','passed':False,'hardware_tested':False,'source_sha256':hashes,'original_functions':rows,'reference_sha256':hashlib.sha256(reference.encode()).hexdigest(),'injected_graphics_sha256':hashlib.sha256(graphics.encode()).hexdigest(),'commands':[],'limits':['Native metrics/bitmaps are synthetic equivalent glyphs; no real G2/Memo font equality.','Missing-glyph fallback and native fallback baselines intentionally differ; native resource failures reject.']}
    try:
        for name,cmd in [('build',['clang',*flags,*map(str,sources),'-o',str(out/'test_text')]),('host',[str(out/'test_text')])]:
            r=subprocess.run(cmd,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);report['commands'].append({'argv':cmd,'returncode':r.returncode});r.check_returncode()
        report['source_drift']=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h];assert not report['source_drift'];report['passed']=True
    except (AssertionError,OSError,subprocess.CalledProcessError) as e:report['error']=str(e)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256','commands','original_functions')},indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
