#!/usr/bin/env python3
"""Compare default and opt-in RESET scratch policy under ASan/UBSan."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures-from',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/('runtime/'+n) for n in ('graphics/tests/test_reset_undo_trim.c','graphics/scene_session.c','portable/geometry.c','portable/vector.c','portable/rle.c','portable/raster_commands.c','portable/rect_copy_commands.c')]
    paths=set(sources)|{ROOT/'runtime/portable/scene.c',ROOT/'runtime/graphics/tests/test_scene_session.c',Path(__file__).resolve()}
    paths.update((ROOT/'runtime/portable').glob('*.h'));paths.update((ROOT/'runtime/portable').glob('*.inc'));paths.update((ROOT/'runtime/graphics').glob('*.h'))
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    report={'passed':False,'hardware_tested':False,'source_sha256':hashes,'commands':[]}
    flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMM_RASTER_COMMANDS=1','-DMM_RECT_COPY=1','-DMM_COMMAND_BUNDLES=1','-I'+str(ROOT/'runtime/portable'),'-I'+str(ROOT/'runtime/graphics')]
    def run(name,cmd):
        r=subprocess.run(list(map(str,cmd)),capture_output=True);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        report['commands'].append({'name':name,'argv':list(map(str,cmd)),'returncode':r.returncode});r.check_returncode()
    try:
        for name,extra in [('default',[]),('trim',['-DMM_SCENE_RESET_UNDO_TRIM=1'])]:
            run('build-'+name,['clang',*flags,*extra,*sources,'-o',out/name]);run(name,[out/name])
        if a.fixtures_from:
            fixtures=[]
            for name in ('vector-fixture.bin','gif-300.bin','svg-300.bin'):
                data=(a.fixtures_from/name).read_bytes();dest=out/name;dest.write_bytes(data);fixtures.append(dest)
            report['fixtures']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures}
            replay_sources=[ROOT/'runtime/graphics/tests/test_scene_session.c',ROOT/'runtime/portable/scene.c',*sources[1:]]
            run('build-trim-replay',['clang',*flags,'-DMM_SCENE_RESET_UNDO_TRIM=1',*replay_sources,'-o',out/'trim-replay'])
            run('trim-replay',[out/'trim-replay',*fixtures])
        report['source_drift']=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h]
        assert not report['source_drift'];report['passed']=True
    except (AssertionError,OSError,subprocess.CalledProcessError) as e:report['error']=str(e)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('commands','source_sha256')}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
