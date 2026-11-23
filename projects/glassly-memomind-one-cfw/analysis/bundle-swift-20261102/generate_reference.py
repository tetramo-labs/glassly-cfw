#!/usr/bin/env python3
"""Original G2mode8 envelope/order oracle with explicit child-dispatch mocks.
This does not validate child semantics, render frames, or access any device.
"""
from pathlib import Path
import ctypes,hashlib,json,struct,subprocess
if not __debug__:raise RuntimeError('Assertions required; optimized execution refused')
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
source=ROOT/'tests/g2_compat/upstream/patches/zlib_glue.c'
pins=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text());sha=hashlib.sha256(source.read_bytes()).hexdigest()
assert sha==pins['copied_files']['patches/zlib_glue.c']
s=source.read_text();a=s.index('    if (mode == 8) {',s.index('static int image_dispatch('));b=s.index('\n    if (mode == 9)',a);branch=s[a:b]
# Keep whole original loop verbatim. Child calls record bytes/order/present=0 and
# may fail at a selected ordinal; prior effects remain counted after failure.
shim='''#include <stdint.h>
uint32_t calls,presents,effects,fail_at,invalid_present;
uint32_t lengths[255],heads[255],checksums[255];
static uint32_t rd16(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8);}
static int image_dispatch(const uint8_t*p,uint32_t n,int present,void*rl){
(void)rl;uint32_t i=calls++;if(present)invalid_present++;
lengths[i]=n;heads[i]=p[0];uint32_t sum=0;for(uint32_t j=0;j<n;j++)sum+=p[j];checksums[i]=sum;
if(calls==fail_at)return -1;effects++;return 0;}
static void present_shadow(uint32_t w,uint32_t h,void*r){(void)w;(void)h;(void)r;presents++;}
int reference(const uint8_t*src,uint32_t srclen,int present,uint32_t failure){
calls=presents=effects=invalid_present=0;fail_at=failure;
if(!src||!srclen)return -1;uint8_t mode=src[0]&127;void*rl=0;uint32_t w=600,h=350;
'''+branch+'\nreturn -1;\n}\n'
(HERE/'reference.c').write_text(shim)
subprocess.run(['clang','-dynamiclib','-Wall','-Wextra','-Werror','-O2',str(HERE/'reference.c'),'-o',str(HERE/'reference.dylib')],check=True)
lib=ctypes.CDLL(str(HERE/'reference.dylib'));lib.reference.argtypes=[ctypes.POINTER(ctypes.c_ubyte),ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
def scalar(k):return ctypes.c_uint32.in_dll(lib,k).value
checks=0
def check(raw,result,segments=(),present=1,failure=0,effects=None,final=None):
 global checks
 data=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw);rc=lib.reference(data,len(raw),present,failure)
 assert rc==result,(raw.hex(),rc,result)
 assert scalar('calls')==len(segments) and not scalar('invalid_present')
 for name,wanted in [('lengths',[len(x) for x in segments]),('heads',[x[0] for x in segments]),('checksums',[sum(x) for x in segments])]:
  actual=list((ctypes.c_uint32*255).in_dll(lib,name))[:len(segments)];assert actual==wanted
 assert scalar('effects')==(len(segments) if effects is None else effects)
 assert scalar('presents')==(int(result==0) if final is None else final)
 checks+=1

def bundle(commands):return bytes([8,len(commands)])+b''.join(struct.pack('<H',len(c))+c for c in commands)
copy=b'\x09'+struct.pack('<8H',100,180,63,31,101,181,63,31)
delta=bytes.fromhex('0300000101010080')
reset=bytes.fromhex('290000010000')
cases=[('empty',[]),('geometry',[b'\x24\0']),('copy-then-delta',[copy,delta]),('reset-geometry',[reset,b'\x24\0']),('highbit-image',[bytes.fromhex('93010000000000000000')])]
for name,children in cases:check(bundle(children),0,children)
# Count255, each allowed mode and its high-bit form (original also accepts15).
check(bundle([b'\x24\0']*255),0,[b'\x24\0']*255)
for base in [3,6,9,15,19,20,36,37,38,39,40,41]:
 for high in (0,128):check(bundle([bytes([base|high])]),0,[bytes([base|high])])
# Every unsupported base is refused, in both raw-bit forms.
for base in range(128):
 if base in [3,6,9,15,19,20,36,37,38,39,40,41]:continue
 for high in (0,128):check(bundle([bytes([base|high])]),-1)
check(b'\x08\0trailing',0);check(b'\x88\0',0)
check(b'\x08\0',-1,present=0);check(b'\x08',-1);check(b'',-1)
check(b'\x08\x01\0\0',-1);check(b'\x08\x01\xff\xff\x24',-1)
check(b'\x08\x01\x02\0\x24',-1)
# All truncations of a two-child packet: first child effect survives if complete.
children=[copy,delta];raw=bundle(children)
for n in range(len(raw)):
 completed=children[:1] if n>=2+2+len(copy) else []
 check(raw[:n],-1,completed,final=0)
check(raw,-1,children,failure=2,effects=1,final=0)
check(raw,0,children);check(raw+b'ignored',0,children)
# Native G2envelope has no8192 cap itself; Memo ingress does. Check exact limits.
for size in [8188,8189,65535]:
 child=b'\x25'+bytes(size-1);check(bundle([child]),0,[child])
report={'source':str(source.relative_to(ROOT)),'source_sha256':sha,'branch_sha256':hashlib.sha256(branch.encode()).hexdigest(),'upstream_commit':pins['commit'],
'checks':checks,'mock_boundary':'Child dispatcher records length/head/checksum/order and simulated effect; no child semantics/display/native claims.',
'known_profile_differences':['Swift refuses mode15 until native adapter exists.','Swift enforces child minimum envelopes and complete command<=8192; original loop only checks nonemptysegments and outerbounds.','Swift emits canonical08 with no trailing bytes.'],
'fixtures':[{'name':name,'children_hex':[x.hex() for x in children],'hex':bundle(children).hex()} for name,children in cases]}
(HERE/'reference.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['// SPDX-License-Identifier: MIT','// struct.pack fixtures checked by verbatim pinned G2mode8 dispatch; child calls mocked.', '// SourceSHA256 '+sha,'// Evidence analysis/bundle-swift-20261102/reference.json','enum BundleReferenceVectors {','    static let cases: [(name: String, children: [String], wire: String)] = [']
for row in report['fixtures']:
 children=', '.join('"'+x+'"' for x in row['children_hex']);lines.append(f'        ("{row["name"]}", [{children}], "{row["hex"]}"),')
lines+=['    ]','}',''];(ROOT/'swift/MemoMindKit/Tests/MemoMindCoreTests/BundleReferenceVectors.swift').write_text('\n'.join(lines))
print(checks,'original branch checks passed')
