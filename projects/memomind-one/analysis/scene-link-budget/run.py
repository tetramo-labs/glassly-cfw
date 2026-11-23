#!/usr/bin/env python3
"""Isolated size/stack experiment. Writes only beneath this experiment directory."""
import hashlib, json, re, shutil, struct, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts'))
from compile_memomind_graphics import FLAGS, COMPILER
from append_memomind_app import append_app
from build_memomind_graphics import address_pair, pc_relative_call, ENTRY, DISPLAY_GATE, DISPLAY_CALL, INITIALIZER, BODY_BASE
from memomind_ota import unpack_ota,repack,sha

def tool(name,*args,check=True):
    p=subprocess.run([str(COMPILER/f'riscv-none-elf-{name}'),*map(str,args)],capture_output=True)
    if check and p.returncode:raise RuntimeError(p.stderr.decode())
    return p

def main():
    snap=HERE/'snapshot';snap.mkdir(exist_ok=False)
    hashes={}
    for component in ('graphics','portable'):
        dest=snap/component;dest.mkdir()
        for p in sorted((ROOT/'runtime'/component).iterdir()):
            if p.is_file() and p.suffix in ('.c','.h','.inc','.S','.ld'):
                content=p.read_bytes();(dest/p.name).write_bytes(content)
                hashes[str(p.relative_to(ROOT))]=sha(content)
    (HERE/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    current_unchanged=all(sha((ROOT/p).read_bytes())==h for p,h in hashes.items())
    if not current_unchanged:raise RuntimeError('Snapshot input drift')
    original_linker=(snap/'graphics/graphics.ld').read_text()
    linker64=HERE/'experiment-64k.ld';linker64.write_text(original_linker.replace('LENGTH = 0x8000','LENGTH = 0x10000'))
    result={'kind':'Offline snapshot link-budget experiment; no active source/image/profile/device changes',
            'compiler':tool('gcc','--version').stdout.decode().splitlines()[0],'sources':hashes,'builds':[]}
    sources=[snap/'graphics/entry.S',snap/'graphics/graphics.c',snap/'graphics/native.c',
             *[snap/'portable'/f'{n}.c' for n in ('geometry','vector','rle','scene')]]
    for optimize in ('O2','Os'):
        out=HERE/optimize;out.mkdir()
        flags=[x for x in FLAGS if not x.startswith('-O')]+['-'+optimize,'-fcallgraph-info=su',
              '-I'+str(snap/'graphics'),'-I'+str(snap/'portable')]
        objects=[];compile_commands=[]
        for src in sources:
            obj=out/(src.stem+'.o')
            extra=['-Wno-unused-function'] if src.parent.name=='portable' else []
            cmd=[*flags,*extra,'-c',src,'-o',obj]
            compile_commands.append(list(map(str,cmd)))
            tool('gcc',*cmd);objects.append(obj)
        exports=[]
        for obj in objects:
            for row in tool('nm','-g','--defined-only',obj).stdout.decode().splitlines():
                f=row.split()
                if len(f)==3 and re.match(r'mm_(scene|vector|rle|geometry|raster)_',f[2]):exports.append(f[2])
        exports=sorted(set(exports));keep=[f'-Wl,--undefined={n}' for n in exports]
        common=[*flags,'-Wl,--no-relax,--gc-sections,--build-id=none,--fatal-warnings',*keep,*objects]
        trial=tool('gcc',*common,'-T',snap/'graphics/graphics.ld','-o',out/'trial-32k.elf',check=False)
        (out/'trial-32k.log').write_bytes(trial.stdout+trial.stderr)
        elf=out/'full.elf'
        tool('gcc',*common,'-T',linker64,'-Wl,-Map='+str(out/'full.map'),'-o',elf)
        if tool('nm','-u',elf).stdout.strip():raise RuntimeError('Unresolved symbols')
        for name,args,filename in [('objdump',['-d',elf],'full.asm'),('nm',['-S','-n',elf],'symbols.txt'),
                                   ('size',['-A',elf],'size.txt'),('readelf',['-h','-S','-l','-r',elf],'readelf.txt')]:
            (out/filename).write_bytes(tool(name,*args).stdout)
        tool('objcopy','-O','binary',elf,out/'full.bin')
        blob=(out/'full.bin').read_bytes()
        usage=[]
        for p in out.glob('*.su'):
            for row in p.read_text().splitlines():
                label,size,kind=row.split('\t');usage.append({'function':label.rsplit(':',1)[-1],'bytes':int(size),'kind':kind,'object':p.stem})
        # Construct only in memory through existing bounded append then the two
        # fixed hooks. No profile limit is altered and no candidate OTA is saved.
        source=(ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        grown,audit=append_app(source,blob,expected_source_sha256=sha(source),alignment=16)
        _,streams=unpack_ota(grown);body=bytearray(streams[3]['raw'][32:])
        for addr,value in [(INITIALIZER,address_pair(ENTRY)),(DISPLAY_CALL,pc_relative_call(DISPLAY_CALL,DISPLAY_GATE))]:
            off=addr-BODY_BASE;body[off:off+8]=value
        ota=repack(grown,{3:bytes(body)})
        packed_payload=len(ota)-18
        stats={'optimization':optimize,'flags':flags,'commands':compile_commands,'retained_exports':exports,
               'blob_bytes':len(blob),'blob_sha256':sha(blob),'fits_32k':len(blob)<=32768,
               'fits_64k':len(blob)<=65536,'trial_32k_exit':trial.returncode,
               'max_individual_frame':max(x['bytes'] for x in usage),'stack_usage':usage,
               'static_frames_only':all(x['kind']=='static' for x in usage),
               'in_memory_container':{'ota_sha256':sha(ota),'ota_bytes':len(ota),'payload_bytes':packed_payload,
                                      'staging_headroom':0x25e000-packed_payload,'app_raw_bytes':len(body)+32,
                                      'app_headroom':0x200000-len(body)-32,'candidate_ota_written':False}}
        result['builds'].append(stats)
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{k:b[k] for k in ('optimization','blob_bytes','fits_32k','fits_64k','max_individual_frame','in_memory_container')} for b in result['builds']],indent=2))

if __name__=='__main__':main()
