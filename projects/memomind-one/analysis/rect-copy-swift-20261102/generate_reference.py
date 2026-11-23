#!/usr/bin/env python3
"""Offline mode9 wire fixtures checked by the pinned original dispatch branch.

Mocked calls record selected coordinates only; this is not a framebuffer, native
MemoMind runtime, ownership, or hardware test. No firmware/device access.
"""
import ctypes, hashlib, json, struct, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
source = ROOT/'tests/g2_compat/upstream/patches/zlib_glue.c'
pin = json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text())
sha = hashlib.sha256(source.read_bytes()).hexdigest()
assert sha == pin['copied_files']['patches/zlib_glue.c']
text = source.read_text()
start = text.index('    if (mode == 9) {', text.index('static int image_dispatch('))
end = text.index('\n    if ((mode != 3', start)
branch = text[start:end]
# Whole original mode9 dispatch branch is retained verbatim. Only its platform
# dependencies are mocked, explicitly recording the chosen source/destination.
shim = '''#include <stdint.h>
static uint8_t dummy;
uint32_t seen[7];
static uint32_t rd16(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8);}
static uint8_t*cfw_shadow_buffer(void){return &dummy;}
static void rect_copy_4bpp(uint8_t*b,uint32_t stride,uint32_t sx,uint32_t sy,uint32_t dx,uint32_t dy,uint32_t w,uint32_t h){(void)b;seen[0]=stride;seen[1]=sx;seen[2]=sy;seen[3]=dx;seen[4]=dy;seen[5]=w;seen[6]=h;}
static void rl_add(void*r,uint32_t x,uint32_t y,uint32_t w,uint32_t h){(void)r;(void)x;(void)y;(void)w;(void)h;}
static void present_shadow(uint32_t w,uint32_t h,void*r){(void)w;(void)h;(void)r;}
#define FW_SIDE() side
int reference(const uint8_t*src,uint32_t srclen,uint32_t side){
if(!src||!srclen)return -1;
uint32_t w=600,h=350;void*rl=0;int present=0;
int lenses_differ=src[0]&0x80;uint8_t mode=src[0]&0x7f;
'''+branch+'\nreturn -1;\n}\n'
(HERE/'reference.c').write_text(shim)
subprocess.run(['clang','-dynamiclib','-Wall','-Wextra','-Werror','-O2',str(HERE/'reference.c'),'-o',str(HERE/'reference.dylib')],check=True)
lib = ctypes.CDLL(str(HERE/'reference.dylib'))
lib.reference.argtypes=[ctypes.POINTER(ctypes.c_ubyte),ctypes.c_uint32,ctypes.c_uint32]
seen=(ctypes.c_uint32*7).in_dll(lib,'seen')
def check(raw,side,expected):
    inp=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
    result=lib.reference(inp,len(raw),side)
    if expected is None:assert result==-1
    else:assert result==0 and list(seen)==expected,(raw.hex(),result,list(seen),expected)
    return result
cases=[('odd', (1,3,7,5),(11,13,7,5)),('full',(0,0,600,350),(0,0,600,350)),
       ('last-pixel',(599,349,1,1),(0,0,1,1)),('high-bytes',(256,257,257,3),(0,0,257,3)),
       ('overlap',(0,0,10,10),(1,1,10,10)),('self',(3,5,9,7),(3,5,9,7))]
rows=[]
for name,src,dst in cases:
    raw=bytes([9])+struct.pack('<8H',*src,*dst)
    expected=[300,src[0],src[1],dst[0],dst[1],src[2],src[3]]
    check(raw,2,expected);check(raw,1,expected)
    rows.append(dict(name=name,source=src,destination=dst,hex=raw.hex()))
left=struct.pack('<8H',1,3,7,5,11,13,7,5)
right=struct.pack('<8H',100,110,2,4,120,130,2,4)
check(b'\x89'+left+right,2,[300,1,3,11,13,7,5])
check(b'\x89'+left+right,1,[300,100,110,120,130,2,4])
# Original selection validates only the chosen lens, and accepts trailing bytes.
check(b'\x89'+left+b'\xff'*16,2,[300,1,3,11,13,7,5])
check(b'\x89'+left+b'\xff'*16,1,None)
check(b'\x09'+left+b'ignored',2,[300,1,3,11,13,7,5])
for length in range(17):check((b'\x09'+left)[:length],2,None)
for length in range(1,33):check((b'\x89'+left+right)[:length],2,None)
for values in [(0,0,0,1,0,0,0,1),(0,0,1,0,0,0,1,0),(0,0,2,1,0,0,1,1),
               (600,0,1,1,0,0,1,1),(0,350,1,1,0,0,1,1),(0,0,1,1,599,350,1,1)]:
    check(b'\x09'+struct.pack('<8H',*values),2,None)
report=dict(source=str(source.relative_to(ROOT)),source_sha256=sha,branch_sha256=hashlib.sha256(branch.encode()).hexdigest(),
            upstream_commit=pin['commit'],mock_boundary='rd16,shadow pointer,copy call recorder,rectlist,present; no framebuffer/device',
            cases=rows,ordinary_checks=12,lens_and_trailing_checks=5,truncation_checks=49,rejection_checks=6,total_native_checks=72)
(HERE/'reference.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['// SPDX-License-Identifier: MIT','// Independent struct.pack LE16 fixtures verified by the verbatim pinned G2mode9 branch.',
       '// SourceSHA256 '+sha,'// Evidence: analysis/rect-copy-swift-20261102/reference.json',
       'enum RectangleCopyVectors {','    static let cases: [(name: String, source: [Int], destination: [Int], hex: String)] = [']
for row in rows:lines.append(f'        ("{row["name"]}", {list(row["source"])}, {list(row["destination"])}, "{row["hex"]}"),')
lines+=['    ]','}','']
(ROOT/'swift/MemoMindKit/Tests/MemoMindCoreTests/RectangleCopyVectors.swift').write_text('\n'.join(lines))
print('72 independent original-branch checks pass; six pinned wire vectors generated.')
