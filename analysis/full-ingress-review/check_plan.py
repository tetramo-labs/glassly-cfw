#!/usr/bin/env python3
"""Offline arithmetic/ownership model only; no native I/O or production proof."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
checks=[]
def require(name,condition):
 if not condition:raise AssertionError(name)
 checks.append(name)
def allocate(bad):
 good=[i for i in range(256) if i not in bad]
 if len(good)<177:return None
 spools=[good[i:i+16] for i in (0,16,32)]
 private=bad|set(sum(spools,[]))
 require('partition-'+str(len(checks)),len(set(sum(spools,[])))==48 and not set(sum(spools,[]))&bad and len(set(range(256))-private)>=129)
 return spools,private
for bit in range(256):
 native={bit};before=native.copy();a=allocate(native)
 require('single-bit-'+str(bit),a is not None and native==before and bit in a[1])
for count in (0,1,48,78,79,80,127,128,255,256):
 for side in ('low','high'):
  bad=set(range(count)) if side=='low' else set(range(256-count,256))
  require('capacity-'+str(count)+'-'+side,(allocate(bad) is not None)==(count<=79))
for origin in (0,1):
 other=origin^1
 roles=['wire0','wire1','free']
 # Compressed input has a distinct decoded destination throughout decoding.
 roles[2]='decoded';require('compressed-input-'+str(origin),roles[origin]=='wire'+str(origin) and roles[other]=='wire'+str(other))
 roles[origin]='undo';require('compressed-dispatch-'+str(origin),len(set(roles))==3 and roles[2]=='decoded' and roles[other]=='wire'+str(other))
 roles=['wire0','wire1','undo'];roles[origin]='plain-record'
 require('plain-dispatch-'+str(origin),len(set(roles))==3 and roles[other]=='wire'+str(other))
require('full-record-overflow-slot',65535+1==16*4096)
require('old-queue-wrap',(65535+4)&65535==3)
require('direct-queue-ceiling',65535-4==65531)
require('max-inner-packet',255+8==263 and 263-11==252)
require('wrapped-packet-single-GM-frame',3+263+4<=642)
require('wrapped-packet-queue-u16',4+3+263<65536)
require('minimum-capacity',48+129==177 and 256-177==79)
require('immutable-metadata-capacity', (43420+4095)//4096==11 and 48+11+129==188 and 256-188==68)
for origin in (0,1):
 # 59 private sectors: other wire16, sealed record16, active11, candidate11, free5.
 require('immutable-metadata-roles-'+str(origin),16+16+11+11+5==59 and 11+5==16)
require('undo-fits-recycled-slot',45468<65536 and (45468+4095)//4096==12)
ram={'canvas_palette':105064,'inflater_two_origins':79888,'scene_cache':43420,'scene_undo':45468,
     'vector_workspace':10752,'flash_workspace':4096,'flash_context':320,'scene_context':1056,'transport_context':648}
full=sum(ram.values());spooled=full-ram['scene_undo']
require('ram-arithmetic',full==290712 and spooled==245244)
require('old-sample-headroom-gap',333956-full<49152)
paths=['runtime/portable/transport.c','runtime/portable/transport.h','runtime/portable/TRANSPORT.md',
 'runtime/portable/scene.c','runtime/portable/scene.h','runtime/portable/scene_cache.inc','runtime/portable/scene_internal.h',
 'runtime/portable/scene_assets_external.inc','runtime/portable/scene_store.c','runtime/portable/scene_store.h',
 'runtime/portable/flash_store.c','runtime/portable/flash_store.h','runtime/portable/scene_flash_store.c',
 'runtime/portable/vector.c','runtime/portable/vector.h','runtime/graphics/graphics.c','runtime/graphics/graphics.h',
 'runtime/graphics/native.c','runtime/graphics/scene_session.c','runtime/graphics/scene_session.h',
 'scripts/memomind_transport.py','tests/g2_compat/upstream/patches/message_transport.c',
 'analysis/ghidra/transport-inflater/report.md','analysis/ghidra/transport-inflater/memory-budget.json',
 'analysis/ghidra/display-adapter/report.md','analysis/ghidra/display-adapter/queue/function-0425a764.c',
 'analysis/ghidra/display-adapter/fragment-review/report.md','analysis/ghidra/memory-capacity/report.md',
 'analysis/flash-store/scene-integration-002/report.json','analysis/portable-transport-tests-02/report.json']
report={'format':'memomind-full-ingress-design-model-v1','design_only':True,'production_tests':False,'passed':True,
 'checks':checks,'check_count':len(checks),'sector_plan':{'physical':256,'spools':48,'cache_minimum':129,'minimum_good':177,'maximum_bad':79},'immutable_metadata_alternative':{'private_pool_sectors':59,'active_metadata_sectors':11,'minimum_good':188,'maximum_bad':68},
 'ram_existing_layouts':ram,'subtotal_current_undo':full,'subtotal_spooled_undo':spooled,
 'parent_reported_new_idle_sample_not_reacquired':334076,'historical_free_heap_sample':333956,'historical_remaining_after_spooled_subtotal':333956-spooled,
 'historical_remaining_after_spooled_subtotal_and_48KiB_headroom':333956-spooled-49152,
 'limitations':['Arithmetic/role model only; no native flash, inflater adapter, reader parser or asynchronous queue implementation tested.',
 'RAM excludes new spool buffers, allocator overhead, native queues, owner/timers, real RTOS and task/interrupt stack; historical free sample is not admission.'],
 'sources_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
(HERE/'plan-model.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'model_checks':len(checks),'design_only':True,'ram_subtotal':spooled,'minimum_good_sectors':177}))
