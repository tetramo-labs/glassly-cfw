#!/usr/bin/env python3
"""Pinned G2 dispatcher oracle; diagnostic context and cleanup callback mocked.
No native controllers, timer deletion, display quiescence or device actions.
"""
from pathlib import Path
import ctypes,hashlib,json,subprocess,re
if not __debug__:raise RuntimeError('Assertions required; optimized execution refused')
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
pins=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text());p=ROOT/'tests/g2_compat/upstream/patches/zlib_glue.c';source=p.read_text();sha=hashlib.sha256(p.read_bytes()).hexdigest();assert sha==pins['copied_files']['patches/zlib_glue.c']
context_path=ROOT/'tests/g2_compat/upstream/patches/cfw_context.h'
context_sha=hashlib.sha256(context_path.read_bytes()).hexdigest();assert context_sha==pins['copied_files']['patches/cfw_context.h']
ring=int(re.search(r'#define CFW_FID_RING\s+(\d+)',context_path.read_text())[1]);assert ring==16
def branch(start,end):
 a=source.index(start,source.index('static int image_dispatch(const uint8_t *src, uint32_t srclen, int present, cfw_rectlist *rl) {'));return source[a:source.index(end,a)]
diag=branch('    if (mode == 7) {','\n    if (mode == 10)')
cleanup=branch('    if (mode == 11) {','\n    /* Custom shadow geometry')
shim='''#include <stdint.h>
#include <string.h>
#define CFW_FID_RING 16
// Deliberately host-owned fields; not the production G2/native ABI layout.
typedef struct {
 uint32_t f_reorder,f_skip,f_dup,diag_seen,fid_resync,last_fid,high_fid;
 uint32_t nack_count,nack_reason,worker_fail_count,worker_fail_mode;
 uint32_t alloc_fail_count,alloc_fail_bytes,alloc_fail_heap,gate_timeouts;
 uint32_t recent_fids[CFW_FID_RING],recent_pos,diag_hide;
} customCfwContext;
static customCfwContext ctx;static int present;
uint32_t alloc_clears,cleanups;
static customCfwContext*getCustomCfwContext(void){return present?&ctx:0;}
static void cfw_alloc_diag_clear(void){alloc_clears++;}
static int cfw_cleanup_session(void){cleanups++;return 37;}
void prepare(int has_context){memset(&ctx,0x5a,sizeof(ctx));present=has_context;alloc_clears=cleanups=0;}
uint32_t field(uint32_t i){uint32_t v;memcpy(&v,(uint8_t*)&ctx+4*i,4);return v;}
int reference(const uint8_t*src,uint32_t srclen){
 if(src==0 || srclen<1)return -1;uint8_t mode=src[0]&0x7f;
'''+diag+cleanup+'\nreturn -1;\n}\n'
(HERE/'reference.c').write_text(shim)
cmd=['clang','-dynamiclib','-Wall','-Wextra','-Werror','-O2',str(HERE/'reference.c'),'-o',str(HERE/'reference.dylib')];subprocess.run(cmd,check=True)
lib=ctypes.CDLL(str(HERE/'reference.dylib'));lib.reference.argtypes=[ctypes.POINTER(ctypes.c_ubyte),ctypes.c_uint32];lib.field.restype=ctypes.c_uint32
checks=0
def check(raw,has_context=1):
 global checks
 lib.prepare(has_context);data=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw);rc=lib.reference(data,len(raw));mode=raw[0]&127 if raw else -1;sub=raw[1] if len(raw)>1 else 255
 assert rc==({7:0,11:37}.get(mode,-1))
 got=[lib.field(i) for i in range(17+ring)];expected=[0x5a5a5a5a]*(17+ring)
 if mode==7 and has_context:
  if sub==0:expected=[0]*15+[65535]*ring+[0,0x5a5a5a5a]
  if sub in [1,2]:expected[16+ring]=2-sub
 assert got==expected,(raw.hex(),got,expected)
 assert ctypes.c_uint32.in_dll(lib,'alloc_clears').value==int(mode==7 and sub==0 and has_context)
 assert ctypes.c_uint32.in_dll(lib,'cleanups').value==int(mode==11)
 checks+=1
for mode in [7,135]:
 for context in [0,1]:
  check(bytes([mode]),context)
  for sub in range(256):
   check(bytes([mode,sub]),context);check(bytes([mode,sub,0,255,11]),context)
for mode in [11,139]:
 for context in [0,1]:
  for trailing in [b'',b'\0',b'\xff\x07\x02',bytes(range(256))]:check(bytes([mode])+trailing,context)
check(b'');check(bytes([0]));check(bytes([255]));
report={'upstream_commit':pins['commit'],'source':str(p.relative_to(ROOT)),'source_sha256':sha,'context_header_sha256':context_sha,'frame_id_ring_entries':ring,'diagnostic_branch_sha256':hashlib.sha256(diag.encode()).hexdigest(),'cleanup_branch_sha256':hashlib.sha256(cleanup.encode()).hexdigest(),'checks':checks,'build_command':cmd,'mock_boundary':'Host-owned diagnostic field context, allocator diagnostic reset counter and cleanup callback return37. No actual cleanup internals/native controller or display claims.','canonical_fixtures':{'clear':'0700','hide':'0701','show':'0702','cleanup':'0b'}}
(HERE/'reference.json').write_text(json.dumps(report,indent=2)+'\n');print(checks,'pinned original dispatcher checks passed')
