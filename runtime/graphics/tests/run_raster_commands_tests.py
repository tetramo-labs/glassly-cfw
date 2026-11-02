#!/usr/bin/env python3
"""ASan/UBSan mode3/6 tests using exact pinned sender and decoder; no device."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    upstream=ROOT/'tests/g2_compat/upstream';pin=json.loads((upstream.parent/'UPSTREAM.json').read_text())
    for name in ('demos/video-bench.ts','patches/rle.c','patches/host/shapes_host_test.c'):
        assert hashlib.sha256((upstream/name).read_bytes()).hexdigest()==pin['copied_files'][name]
    sources=[ROOT/('runtime/'+n) for n in ('graphics/graphics.c','graphics/scene_session.c','graphics/native_text.c',
        'portable/geometry.c','portable/vector.c','portable/scene.c','portable/rle.c','portable/raster_commands.c',
        'graphics/tests/raster_g2_reference.c','graphics/tests/test_raster_commands.c')]
    inputs=set(sources)|set((ROOT/'runtime/graphics').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.h'))|set((ROOT/'runtime/portable').glob('*.inc'))|{Path(__file__).resolve(),ROOT/'runtime/graphics/tests/test_graphics.c'}
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(inputs)}
    report={'format':'memomind-raster-commands-host-v1','passed':False,'source_sha256':hashes,'hardware_tested':False,'commands':[],'upstream_commit':pin['commit']}
    def run(name,cmd):
        cmd=list(map(str,cmd));r=subprocess.run(cmd,capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        report['commands'].append({'name':name,'argv':cmd,'returncode':r.returncode});r.check_returncode()
    try:
        source=(upstream/'demos/video-bench.ts').read_text()
        def fn(name):
            start=source.index('function '+name+'(');return source[start:source.index('\n}\n',start)+3]
        script='import {deflateSync,inflateSync} from "node:zlib";\ntype Box={left:number,top:number,w:number,h:number};\n'+fn('rleEncode')+fn('pack')+fn('packBox')+'''
const root=process.argv[2]!;
const raw=new Uint8Array(105000);for(let y=0;y<350;y++)raw.fill((y%16)*17,y*300,(y+1)*300);
const key=pack(6,rleEncode(raw));
const delta=packBox({left:596,top:348,w:4,h:2},rleEncode(new Uint8Array([0x12,0x34,0x56,0x78])),0x1234);
for(const [name,msg,prefix] of [["key",key,1],["delta",delta,7]] as const){
 const decoded=new Uint8Array([...msg.subarray(0,prefix),...inflateSync(msg.subarray(prefix))]);
 await Bun.write(root+"/"+name+".message",decoded);await Bun.write(root+"/"+name+".wire",msg);
}
await Bun.write(root+"/key.raw",raw);
console.log("Exact original sender pack/packBox/rleEncode; zlib removed offline at original decompression boundary, not claimed as native inflater support");
'''
        (out/'sender.ts').write_text(script);run('sender',['bun',out/'sender.ts',out])
        flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_GRAPHICS_SCENE=1','-DMM_RASTER_COMMANDS=1','-I'+str(ROOT/'runtime/portable'),'-I'+str(ROOT/'runtime/graphics'),'-I'+str(upstream/'patches'),'-DG2_REFERENCE_SOURCE="'+str(upstream/'patches/host/shapes_host_test.c')+'"','-DG2_RLE_REFERENCE_SOURCE="'+str(upstream/'patches/rle.c')+'"']
        run('build',['clang',*flags,*sources,'-o',out/'test_raster']);run('host',[out/'test_raster',out/'key.message',out/'key.raw',out/'delta.message'])
        report['source_drift']=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h];assert not report['source_drift']
        report['fixtures']={f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in out.iterdir() if f.suffix in ('.message','.wire','.raw')}
        report['passed']=True
    except (AssertionError,OSError,subprocess.CalledProcessError) as e:report['error']=str(e)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('commands','source_sha256')},indent=2))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
