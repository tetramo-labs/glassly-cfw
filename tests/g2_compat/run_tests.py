#!/usr/bin/env python3
"""Run copied offline source suites; distinguish Memo ports from G2 baselines."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New output directory')
    parser.add_argument('--cc',default='clang')
    parser.add_argument('--require-complete',action='store_true',help='Exit2 if required in-scope MemoMind coverage remains unimplemented/platform-specific')
    parser.add_argument('--include-keyboard-reference',action='store_true',help='Run optional historical keyboard checks; their failures do not block in-scope parity')
    parser.add_argument('--include-volume-gate-reference',action='store_true',help='Run optional volume-gate reference; excluded from parity')
    parser.add_argument('--bun',default='bun')
    parser.add_argument('--demos-dependencies',type=Path,default=Path.home()/'dev/glassly-g2-cfw/demos/node_modules',
                        help='Existing installed dependency tree copied into output; no install scripts or downloads')
    parser.add_argument('--g2-media',type=Path,default=Path.home()/'dev/glassly-g2-cfw/demos',
                        help='Read-only upstream media directory (GIF required; prepared SVG video optional)')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    pin=json.loads((ROOT/'UPSTREAM.json').read_text())
    for name,digest in pin['copied_files'].items():
        if hashlib.sha256((ROOT/'upstream'/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Changed pinned source: '+name)
    patches=ROOT/'upstream/patches'
    # These tests intentionally exercise unchanged pure algorithms. Detect drift
    # before describing their execution as an upstream assertion port.
    if (ROOT/'portable_algorithms/volume_gate_core.h').read_bytes() != (patches/'volume_gate_core.h').read_bytes():
        raise RuntimeError('Portable volume gate differs from pinned upstream')
    easing=(ROOT/'portable_algorithms/easing.h').read_text()
    easing_body=easing[easing.index('static uint32_t cfw_ease_byte_q15'):].rstrip()
    if easing_body not in (patches/'scene.c').read_text():
        raise RuntimeError('Portable easing differs from pinned upstream')
    # Exact extractions used by upstream aggregate runner; only output files are generated.
    functions=[]
    for source,name in (('settings_ext.c','glassly_read_varint'),('settings_ext.c','glassly_scan_settings_control'),
                        ('settings_ext.c','settings_send_wrapper'),('zlib_glue.c','is_shadow_message')):
        code=(patches/source).read_text()
        match=re.search(r'^(?:static )?(?:int|void) '+name+r'\([^;{]*\) \{\n.*?^\}',code,re.M|re.S)
        if not match:raise RuntimeError('Missing upstream function '+name)
        functions.append(match[0])
    fields=re.findall(r'^#define (?:GLASSLY|MIC|ANCS|BLE|KEYBOARD|VOLUME_GATE)_CONTROL_FIELD .*',(patches/'settings_ext.c').read_text(),re.M)
    (out/'upstream_functions.inc').write_text('\n\n'.join(fields+functions)+'\n')
    if args.include_keyboard_reference:
        functions=[]
        for name in ('kb_kick','kb_schedule','kb_tick'):
            match=re.search(r'static void '+name+r'\([^;{]*\) \{\n.*?^\}',(patches/'keyboard.c').read_text(),re.M|re.S)
            if not match:raise RuntimeError('Missing upstream timer '+name)
            functions.append(match[0])
        (out/'keyboard_timer_functions.inc').write_text('\n\n'.join(functions)+'\n')
    results=[]
    def step(name,scope,command,cwd):
        result=subprocess.run(command,cwd=cwd,capture_output=True)
        (out/(name+'.stdout')).write_bytes(result.stdout)
        (out/(name+'.stderr')).write_bytes(result.stderr)
        results.append({'name':name,'scope':scope,'command':[str(x) for x in command],
                        'result':'passed' if result.returncode==0 else 'failed','returncode':result.returncode})
        return result.returncode==0
    flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all']
    def run(name,kind,sources,includes=(),libraries=(),argv=(),stdin=None):
        binary=out/name
        command=[args.cc,*flags,*['-I'+str(p) for p in includes],*[str(p) for p in sources],*libraries,'-o',str(binary)]
        build=subprocess.run(command,capture_output=True,text=True)
        (out/(name+'.build.stderr')).write_text(build.stderr)
        if build.returncode:
            results.append({'name':name,'scope':kind,'result':'build-failed','returncode':build.returncode,'build_command':command});return
        result=subprocess.run([str(binary),*[str(p) for p in argv]],input=stdin,capture_output=True)
        (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        results.append({'name':name,'scope':kind,'result':'passed' if result.returncode==0 else 'failed','returncode':result.returncode,
                        'build_command':command,'test_command':[str(binary),*[str(p) for p in argv]],
                        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()})
    run('ported_shapes','MemoMind geometry API: 14 original geometric assertion sites',
        [ROOT/'ported_shapes.c',REPO/'runtime/portable/geometry.c'],[patches,REPO/'runtime/portable'],argv=[out])
    run('ported_easing','portable copied algorithm; animation integration unimplemented',[ROOT/'ported_easing.c'])
    if args.include_volume_gate_reference:
        run('ported_volume_gate','Optional historical volume-gate reference; excluded from parity',
            [patches/'host/volume_gate_host_test.c'],[ROOT/'portable_algorithms'])
    for test in ('ancs_relay','upstream','keyboard','transport','shapes','vector'):
        if test=='keyboard' and not args.include_keyboard_reference:continue
        run('reference_'+test,'G2 reference baseline only; not a MemoMind feature pass',
            [patches/f'host/{test}_host_test.c'],[patches,out],['-lz'] if test=='transport' else [],[out] if test in ('shapes','vector') else [])
    # Preserve the entire original TS tests and modules. Existing node_modules
    # is copied, so Bun cannot write to the original G2 checkout.
    if args.demos_dependencies.is_dir() and shutil.which(args.bun):
        demos=out/'demos';shutil.copytree(ROOT/'upstream/demos',demos)
        shutil.copytree(args.demos_dependencies,demos/'node_modules',symlinks=False)
        files=['vector-protocol.test.ts','svg-video.test.ts']
        cmd=[args.bun,'test',*files]
        result=subprocess.run(cmd,cwd=demos,capture_output=True)
        (out/'typescript.stdout').write_bytes(result.stdout);(out/'typescript.stderr').write_bytes(result.stderr)
        results.append({'name':'typescript','scope':'copied phone-side algorithms/protocol fixtures; G2-specific wire cases do not establish MemoMind routing',
                        'result':'passed' if result.returncode==0 else 'failed','returncode':result.returncode})
        if args.include_keyboard_reference:
            step('typescript_keyboard','Optional historical keyboard reference, excluded from parity',
                 [args.bun,'test','keyboard.test.ts'],demos)
        for config in ('vector','keyboard'):
            if config=='keyboard' and not args.include_keyboard_reference:continue
            step('typecheck_'+config,'Unchanged upstream TypeScript type check',
                 [args.bun,'node_modules/typescript/bin/tsc','-p',f'tsconfig.{config}.json'],demos)
        scope='Generated upstream fixture replay against G2 reference runtime; production MemoMind scene/path replays run in the separate scene/session stages'
        fixtures=[('vector_fixture',['--dump',str(out/'vector-fixture.bin')],out/'vector-fixture.bin')]
        media={}
        gif=args.g2_media.resolve()/'bad_apple_quarter.gif'
        if gif.is_file():
            media[str(gif)]={'bytes':gif.stat().st_size,'sha256':hashlib.sha256(gif.read_bytes()).hexdigest()}
            fixtures.append(('gif_300',['--bad-apple','--frames','300','--gif',str(gif),
                                       '--dump',str(out/'gif-300.bin')],out/'gif-300.bin'))
        else:
            results.append({'name':'gif_300','scope':scope,'result':'dependency-missing','path':str(gif)})
        svg=args.g2_media.resolve()/'.cache/bad-apple/smooth/video.json'
        if svg.is_file():
            media[str(svg)]={'bytes':svg.stat().st_size,'sha256':hashlib.sha256(svg.read_bytes()).hexdigest()}
            fixtures.append(('svg_300',['--svg-video',str(svg),'--frames','300',
                                       '--dump',str(out/'svg-300.bin')],out/'svg-300.bin'))
        else:
            results.append({'name':'svg_300','scope':'Optional prepared upstream media absent; not counted as passed',
                            'result':'optional-not-run','path':str(svg)})
        (out/'media-sha256.json').write_text(json.dumps(media,indent=2)+'\n')
        for name,arguments,fixture in fixtures:
            if step(name+'_generate','Upstream phone-side offline fixture generator; no Bluetooth access',
                    [args.bun,'vector-suite.ts',*arguments],demos):
                replay_out=out/(name+'-replay');replay_out.mkdir()
                binary=out/'reference_vector'
                if binary.is_file():
                    step(name+'_replay',scope,[str(binary),str(replay_out),str(fixture)],out)
                else:
                    results.append({'name':name+'_replay','scope':scope,'result':'dependency-missing'})
        packages={}
        for p in (demos/'node_modules').rglob('package.json'):
            try:
                v=json.loads(p.read_text());packages[str(p.relative_to(demos/'node_modules'))]={'name':v.get('name'),'version':v.get('version'),'package_json_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            except (ValueError,OSError):pass
        (out/'dependency-versions.json').write_text(json.dumps(packages,indent=2)+'\n')
        hashes={str(p.relative_to(demos/'node_modules')):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((demos/'node_modules').rglob('*')) if p.is_file()}
        (out/'dependency-file-sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    else:
        results.append({'name':'typescript','scope':'required Bun or installed dependency tree unavailable','result':'dependency-missing'})
    results.append({'name':'keyboard_arm_emulator','scope':'Optional historical keyboard reference; excluded from required parity, not a pass','result':'excluded-not-run'})
    results.append({'name':'device_demos','scope':'require real G2 BLE/device hardware; no device actions permitted','result':'platform-specific-not-run'})
    for row in results:
        row['parity_required']=row['name'] not in ('reference_keyboard','typescript_keyboard','typecheck_keyboard','keyboard_arm_emulator','ported_volume_gate')
    report={'keyboard_reference_requested':args.include_keyboard_reference,
            'volume_gate_reference_requested':args.include_volume_gate_reference,
            'excluded_features':['Bluetooth keyboard/HOGP accessory support','Mode5 sound and tone commands','Microphone volume gating'],
            'source_commit':pin['commit'],'results':results,'hardware_tested':False,
            'memo_full_suite_port_complete':False,'skipped_or_unimplemented_count_as_pass':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    if any(r['parity_required'] and r['result'] in ('failed','build-failed','dependency-missing') for r in results):return 1
    return 2 if args.require_complete else 0


if __name__=='__main__':raise SystemExit(main())
