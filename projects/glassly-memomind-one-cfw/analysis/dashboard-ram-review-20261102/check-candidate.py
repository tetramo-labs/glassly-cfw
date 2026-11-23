"""Read-only independent candidate range reconstruction and admission pins."""
if not __debug__:raise RuntimeError('Refuse -O')
from pathlib import Path
import hashlib,json,sys,struct,zlib
ROOT=Path(__file__).resolve().parents[2];sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts'))
from memomind_ota import unpack_ota,repack
from build_memomind_dashboard_ram import construct_dashboard_ram,verify_dashboard_ram,GATES
sha=lambda b:hashlib.sha256(b).hexdigest()
source=(ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
folder=ROOT/'captures/firmware/dashboard-ram-002';image=(folder/'firmware.bin').read_bytes()
assert sha(source)=='a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917'
assert sha(image)!='c6adcbfbba6ea0f340670daa495f4d8db354fcf3362036af90402897e9eb6c08'
manifest=json.loads((folder/'manifest.json').read_text());proof=json.loads((folder/'verification.json').read_text())
rebuilt,expected,p=construct_dashboard_ram(source);assert rebuilt==image and manifest==expected and proof==p
assert verify_dashboard_ram(source,manifest)[0]==image
old,oldstreams=unpack_ota(source);new,newstreams=unpack_ota(image)
# Independently pin six addresses/before/after rather than trusting constructor's table.
recipe=[(0x04264f26,'011122cc'),(0x04265060,'011122cc'),(0x042652e8,'83a7416a'),(0x0426f2c2,'411122c4'),(0x04268336,'011106ce'),(0x042683f0,'411122c6')]
assert [(a,b,c) for a,b,c,_ in GATES]==[(a,b,'01458280') for a,b in recipe]
base=0x041eb020;before=oldstreams[3]['raw'][32:];after=newstreams[3]['raw'][32:]
assert len(before)==len(after)
independent=bytearray(before);spans=[]
for a,b in recipe:
 off=a-base;assert before[off:off+4].hex()==b and after[off:off+4].hex()=='01458280'
 independent[off:off+4]=bytes.fromhex('01458280');spans.extend(range(off,off+4))
assert len(set(spans))==24 and bytes(independent)==after
assert repack(source,{3:bytes(independent)})==image
actual=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b]
assert set(actual)<=set(spans)
for i in (0,1,2,4,5,6):assert oldstreams[i]['raw']==newstreams[i]['raw'] and oldstreams[i]['packed']==newstreams[i]['packed']
runtime=(ROOT/'runtime/build/diagnostic-commands-001/graphics.bin').read_bytes();entry=0x0439bea0-base
assert after[entry:]==before[entry:]==runtime and len(runtime)==65456
assert sha(runtime)=='c1d8a1ffdd4f2799de4149d2e113527b29716886f6530549e56f68f61333d3b3'
header=newstreams[3]['raw'][:256];assert (folder/'expected-app-header.bin').read_bytes()==header
assert newstreams[3]['raw'][32:256]==oldstreams[3]['raw'][32:256]
payload=len(image)-18;rounded=(payload+4095)&~4095
assert payload<=0x25e000 and rounded<=0x25e000 and len(newstreams[3]['raw'])<=0x200000
assert int.from_bytes(image[6:10],'big')==payload and int.from_bytes(image[14:18],'big')==zlib.crc32(image[18:])
card=json.loads((ROOT/'analysis/dashboard-ram-card-20261102/proof.json').read_text())
assert {(int(r['address'],16),r['before4'],r['proposed4']) for r in card['cold_boot_candidate_gates']}=={(a,b,'01458280') for a,b in recipe[:3]}
report=dict(passed=True,device_actions=False,candidate=str(folder.relative_to(ROOT)),image_bytes=len(image),image_sha256=sha(image),source_sha256=sha(source),outer_header150_sha256=sha(image[:150]),app_header256_sha256=sha(header),runtime_sha256=sha(runtime),runtime_bytes=len(runtime),gate_span_bytes=24,actual_changed_body_bytes=len(actual),changed_body_offsets=actual,entire_body_outside_six_spans_identical=True,unchanged_streams=[0,1,2,4,5,6],unchanged_runtime=True,exact_constructor_and_independent_repack=True,checksums=new['checksums'],bounds=dict(app_raw_bytes=len(newstreams[3]['raw']),app_allocation=0x200000,payload_bytes=payload,rounded_payload_bytes=rounded,staging_capacity=0x25e000),stream_pins=[dict(index=i,packed_bytes=len(s['packed']),raw_bytes=len(s['raw']),packed_sha256=sha(s['packed'])) for i,s in enumerate(newstreams)],rejected001_sha256='c6adcbfbba6ea0f340670daa495f4d8db354fcf3362036af90402897e9eb6c08')
out=Path(__file__).with_name('candidate-check.json');assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','image_sha256','image_bytes','actual_changed_body_bytes','bounds')}))
