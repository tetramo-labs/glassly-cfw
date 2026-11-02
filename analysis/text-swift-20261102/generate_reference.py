#!/usr/bin/env python3
"""Independent struct.pack text fixtures checked by pinned G2 production parser.
Font/lease/pixel callbacks are explicit host mocks; no native glyph claims.
"""
import ctypes, hashlib, json, struct, subprocess
from pathlib import Path
if not __debug__: raise RuntimeError('Assertions required; optimized execution refused')
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
pins=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text())
p=ROOT/'tests/g2_compat/upstream/patches/texture_cache.c'; source=p.read_text()
sha=hashlib.sha256(p.read_bytes()).hexdigest(); assert sha==pins['copied_files']['patches/texture_cache.c']
def extract(start,end): return source[source.index(start):source.index(end,source.index(start))]
utf8=extract('static int cfw_texture_utf8(', '\n/* A string asset')
nextglyph=extract('static uint32_t cfw_texture_next_glyph(', '\nstatic int32_t cfw_texture_s16')
draw=extract('static int cfw_builtin_draw_string_buf(', '\n/* Mode 15 entry:')
shim='''#include <stdint.h>
#include <string.h>
#define CFW_TEXT_CONTROL_FLAG 0x80000000u
#define CFW_GLYPH_DSC_SIZE 32u
#define CFW_GLYPH_BOX_W 6u
#define CFW_GLYPH_BOX_H 8u
#define CFW_GLYPH_OFS_X 10u
#define CFW_GLYPH_OFS_Y 12u
#define CFW_GLYPH_ADV_W 4u
#define CFW_FONT_LINE_HEIGHT 12u
#define CFW_FONT_BASE_LINE 16u
#define CFW_TEXTURE_OPT_TRANSPARENT 0x10u
static const uint8_t mock_font[20]={[12]=20,[16]=4};
#define CFW_FONT20_ROOT mock_font
#define CFW_FONT_RELEASE(p) ((void)(p))
typedef struct { int unused; } cfw_rectlist;
static int cfw_fb_lease_active(void){return 1;}
static uint32_t rd16(const uint8_t*p){return p[0]|((uint32_t)p[1]<<8);}
static int32_t cfw_texture_s16(const uint8_t*p){return (int16_t)rd16(p);}
static int32_t cfw_texture_s32(const uint8_t*p){return (int32_t)(p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24));}
static int cfw_builtin_glyph(const uint8_t*f,uint32_t cp,uint32_t next,uint8_t*d,const uint8_t**bits){
(void)f;(void)cp;(void)next;memset(d,0,32);d[4]=1;*bits=0;return 1;}
static void cfw_texture_make_lut(uint8_t o,uint8_t*l){for(unsigned i=0;i<16;i++)l[i]=((o&32)?15-i:i)*(o&15)/15;}
static void cfw_texture_render_a4(uint8_t*s,uint32_t st,uint32_t w,uint32_t h,int32_t x,int32_t y,const uint8_t*b,uint32_t bw,uint32_t bh,const uint8_t*l,int t){
(void)s;(void)st;(void)w;(void)h;(void)x;(void)y;(void)b;(void)bw;(void)bh;(void)l;(void)t;}
static void cfw_texture_add_rect(cfw_rectlist*r,int32_t x,int32_t y,uint32_t w,uint32_t h,uint32_t pw,uint32_t ph){
(void)r;(void)x;(void)y;(void)w;(void)h;(void)pw;(void)ph;}
'''+utf8+nextglyph+draw+'''
uint32_t tokens_out[255];
int reference(const uint8_t *p,uint32_t n){
if(n<1 || (p[0]&127)!=15)return -1;
uint8_t shadow[1];memset(tokens_out,0,sizeof(tokens_out));
return cfw_builtin_draw_string_buf(shadow,300,600,350,p+1,n-1,0,tokens_out,255);}
'''
(HERE/'reference.c').write_text(shim)
cmd=['clang','-dynamiclib','-Wall','-Wextra','-Werror','-O2',str(HERE/'reference.c'),'-o',str(HERE/'reference.dylib')]
subprocess.run(cmd,check=True); lib=ctypes.CDLL(str(HERE/'reference.dylib'));lib.reference.argtypes=[ctypes.POINTER(ctypes.c_ubyte),ctypes.c_uint32]
checks=0
def check(wire,valid):
 global checks
 buf=(ctypes.c_ubyte*len(wire)).from_buffer_copy(wire)
 result=lib.reference(buf,len(wire)); assert (result==0)==valid,(wire.hex(),result,valid)
 checks+=1

def wire(x,y,options,text,mode=15): return bytes([mode])+struct.pack('<hhBB',x,y,options,len(text))+text
cases=[('empty',0,0,15,b''),('ascii',123,45,15,b'Glassly'),('signed-extremes',-32768,32767,255,b'A'),
('offscreen',-1,-2,0,b'B'),('controls',0,0,63,bytes(range(1,32))),('del',0,0,128,b'\x7f'),
('unicode',256,-256,31,'A\u0080\u07ff\u0800\ud7ff\ue000\uffff\U00010000\U0010ffff'.encode()),
('bom',1,2,15,b'\xef\xbb\xbf'),('decomposed',3,4,15,'e\u0301'.encode()),('max-bytes',0,0,15,b'A'*255)]
fixtures=[]
for name,x,y,opt,text in cases:
 raw=wire(x,y,opt,text);check(raw,True);check(bytes([143])+raw[1:],True)
 fixtures.append(dict(name=name,x=x,y=y,options=opt,text_hex=text.hex(),wire_hex=raw.hex()))
 for n in range(len(raw)):check(raw[:n],False)
 check(raw+b'\0',False)
for opt in range(256):check(wire(-123,321,opt,b'A\x01B'),True)
for b in range(256):check(wire(0,0,15,bytes([b])),1<=b<=127)
invalid=['00','80','bf','c0af','c180','c2','c220','df7f','e08080','ed a0 80','e1','e180','e18020','f0808080','f4908080','f5808080','f1','f180','f18080','f1808020','ff','fe','eda080','41c242']
invalid=[bytes.fromhex(s) for s in invalid]
for raw in invalid:check(wire(0,0,15,raw),False)
report={'upstream_commit':pins['commit'],'source':str(p.relative_to(ROOT)),'source_sha256':sha,
'utf8_sha256':hashlib.sha256(utf8.encode()).hexdigest(),'draw_sha256':hashlib.sha256(draw.encode()).hexdigest(),
'checks':checks,'build_command':cmd,'mock_boundary':'Live lease, font metrics and zero-area glyph callbacks mocked; full original parser/tokenization/preflight/control loop executes. No hardware or real glyph/pixel claim.',
'fixtures':fixtures,'invalid_utf8_or_nul':[x.hex() for x in invalid]}
(HERE/'reference.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['// SPDX-License-Identifier: MIT','// Independent struct.pack fixtures checked by verbatim pinned G2 text parser.', '// SourceSHA256 '+sha,'// Evidence: analysis/text-swift-20261102/reference.json','enum TextReferenceVectors {','    static let cases: [(name: String, x: Int, y: Int, options: UInt8, bytes: String, wire: String)] = [']
for c in fixtures:lines.append(f'        ("{c["name"]}", {c["x"]}, {c["y"]}, {c["options"]}, "{c["text_hex"]}", "{c["wire_hex"]}"),')
lines+=['    ]','    static let invalid = ['+', '.join('"'+x.hex()+'"' for x in invalid)+']','}','']
(ROOT/'swift/MemoMindKit/Tests/MemoMindCoreTests/TextReferenceVectors.swift').write_text('\n'.join(lines))
print(checks,'pinned original parser checks passed')
