#!/usr/bin/env python3
"""Compose the pinned RESET undo runtime with reviewed dashboard/owner gates."""
import argparse,json
from pathlib import Path
from build_memomind_flash_canary import construct_canary
from build_memomind_dashboard_ram import apply_ram_gates
from build_memomind_graphics import _guard_final_bounds,ENTRY,BODY_BASE
from memomind_ota import repack,unpack_ota,sha,require
RUNTIME_SHA='93040b1de94b52b710d7a3e37a3adef2f1e840108fb53ab69b9ecf46e14102f4'
RUNTIME_BYTES=60256

def construct(source,blob):
    require(len(blob)==RUNTIME_BYTES and sha(blob)==RUNTIME_SHA,'Requires reviewed RESET undo runtime')
    base,canary,proof=construct_canary(source,blob)
    _,streams=unpack_ota(base);original=streams[3]['raw'][32:]
    body,gates=apply_ram_gates(original)
    require(body[ENTRY-BODY_BASE:ENTRY-BODY_BASE+len(blob)]==blob,'Runtime mapping mismatch')
    output=repack(base,{3:body});_guard_final_bounds(len(output),len(body)+32)
    decoded,final=unpack_ota(output)
    require(final[3]['raw'][32:]==body,'Final body mismatch')
    for i in (0,1,2,4,5,6):require(final[i]['packed']==streams[i]['packed'],'Unrelated stream changed')
    manifest=dict(format='memomind-reset-undo-trim-v1',source_sha256=sha(source),output_sha256=sha(output),blob_sha256=sha(blob),blob_bytes=len(blob),base_manifest=canary,dashboard_ram_gates=gates,cold_boot_required=True,policy='Standalone successful RESET releases undo; mutating PUT/SHOW requires rollback allocation; bundles retain scratch',hardware_validated=False)
    evidence=dict(output_bytes=len(output),app_raw_bytes=len(final[3]['raw']),runtime_offset=ENTRY-BODY_BASE,unchanged_component_indices=[0,1,2,4,5,6],checksums=decoded['checksums'],base_proof=proof,live_admission='Separate exact Swift catalog pin; no canary operation authorized by this constructor')
    return output,manifest,evidence

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('runtime',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    blob=a.runtime.read_bytes();data,manifest,proof=construct(a.source.read_bytes(),blob)
    a.output.mkdir(parents=True,exist_ok=False)
    for name,body in [('firmware.bin',data),('runtime.bin',blob)]: (a.output/name).write_bytes(body)
    for name,obj in [('manifest.json',manifest),('proof.json',proof)]: (a.output/name).write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps({'bytes':len(data),'sha256':sha(data)}))
if __name__=='__main__':main()
