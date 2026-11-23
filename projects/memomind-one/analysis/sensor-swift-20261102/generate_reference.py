#!/usr/bin/env python3
"""Pinned production compass dispatcher + ALS control/parameter-boundary oracle.
Hardware functions are mocked; no sensor access, ownership or report equivalence.
"""
from pathlib import Path
import ctypes,hashlib,json,struct,subprocess
if not __debug__:raise RuntimeError('Assertions required; optimized execution refused')
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
pins=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text());sources={};digests={}
for f in ['patches/zlib_glue.c','patches/als_sensor.c','patches/compass.c']:
 p=ROOT/'tests/g2_compat/upstream'/f;digests[f]=hashlib.sha256(p.read_bytes()).hexdigest();assert digests[f]==pins['copied_files'][f];sources[f]=p.read_text()
z=sources['patches/zlib_glue.c'];a=sources['patches/als_sensor.c']
compass=z[z.index('    if (mode == 10) {'):z.index('\n    if (mode == 17)',z.index('    if (mode == 10) {'))]
alsbranch=z[z.index('    if (mode == 16) {'):z.index('\n    if (mode == 11)',z.index('    if (mode == 16) {'))]
control=a[a.index('int als_control('):a.index('\n/* Mode-11 session cleanup')]
start=a[a.index('static int als_passive_start('):a.index('\n    if (!ctx->als_hooked)',a.index('static int als_passive_start('))]
shim='''#include <stdint.h>
#include <string.h>
// Host context fields/callbacks, NOT native G2 memory layout or hardware.
typedef struct {uint32_t compass_forward,als_flags,als_interval_ms,als_min_delta,als_heartbeat_ms;} customCfwContext;
static customCfwContext ctx;static int side,have,start_result,config_result;
uint32_t starts,stops,configs,interval_value,change_value,als_starts,queries,als_stops;
static customCfwContext*getCustomCfwContext(void){return have?&ctx:0;}
static int FW_SIDE(void){return side;}
static int FW_COMPASS_START(void){starts++;return start_result;}
static int FW_COMPASS_STOP(void){stops++;return 0;}
static int FW_COMPASS_CONFIG(uint32_t kind,uint32_t*c){if(kind!=2)return -99;configs++;interval_value=c[0];change_value=c[1];return config_result;}
#define ALS_INTERVAL_MIN 100u
#define ALS_INTERVAL_MAX 5000u
#define ALS_INTERVAL_DEFAULT 500u
#define ALS_REASON_QUERY 0u
#define ALS_REASON_STOP 3u
#define ALS_FW_SIDE FW_SIDE
static void als_send_report(customCfwContext*c,uint8_t reason){(void)c;if(reason==0)queries++;}
static void als_passive_stop(customCfwContext*c,uint8_t reason){(void)c;if(reason==3)als_stops++;}
'''+start+'''
// Extraction ends immediately before native hook installation/open/report.
als_starts++;return start_result;
}
'''+control+'''
void setup(int lens,int present,int start_error,int config_error){memset(&ctx,0,sizeof(ctx));side=lens;have=present;start_result=start_error;config_result=config_error;
starts=stops=configs=interval_value=change_value=als_starts=queries=als_stops=0;}
uint32_t field(unsigned i){uint32_t v;memcpy(&v,(uint8_t*)&ctx+4*i,4);return v;}
int reference(const uint8_t*src,uint32_t srclen){if(!src || srclen<1)return -1;uint8_t mode=src[0]&127u;
'''+compass+alsbranch+'\nreturn -1;\n}\n'
(HERE/'reference.c').write_text(shim);cmd=['clang','-dynamiclib','-std=c11','-Wall','-Wextra','-Werror','-O2',str(HERE/'reference.c'),'-o',str(HERE/'reference.dylib')];subprocess.run(cmd,check=True)
lib=ctypes.CDLL(str(HERE/'reference.dylib'));lib.reference.argtypes=[ctypes.POINTER(ctypes.c_ubyte),ctypes.c_uint32];lib.field.restype=ctypes.c_uint32
checks=0
def check(raw,lens=1,present=1,start_error=0,config_error=0):
 global checks
 lib.setup(lens,present,start_error,config_error);buf=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw);rc=lib.reference(buf,len(raw));mode=raw[0]&127 if raw else -1;op=raw[1] if len(raw)>1 else -1
 state=[0]*5;calls=dict(starts=0,stops=0,configs=0,interval_value=0,change_value=0,als_starts=0,queries=0,als_stops=0);expected=-1
 if mode==10 and len(raw)>=2 and present:
  if op==0:calls['stops']=int(lens==1);expected=0
  elif op==1 or (op==2 and len(raw)>=6):
   expected=0;state[0]=1
   if lens==1:
    calls['starts']=1;expected=start_error
    if expected==0 and op==2:
     calls.update(configs=1,interval_value=min(2000,max(50,int.from_bytes(raw[2:4],'little'))),change_value=int.from_bytes(raw[4:6],'little'));expected=config_error
     if expected:calls['stops']=1
    if expected:state[0]=0
 if mode==16 and len(raw)>=2 and present:
  if lens!=1:expected=0
  elif op==0:expected=0;calls['queries']=1
  elif op==2:expected=0;calls['als_stops']=1
  elif op==1:
   flags=raw[2] if len(raw)>=3 else 0
   interval=int.from_bytes(raw[3:5],'little') if len(raw)>=5 else 500
   delta=int.from_bytes(raw[5:7],'little') if len(raw)>=7 else 1
   heartbeat=int.from_bytes(raw[7:9],'little') if len(raw)>=9 else 5000
   state=[0,flags,min(5000,max(100,interval)),delta,heartbeat];calls['als_starts']=1;expected=start_error
 assert rc==expected,(raw.hex(),rc,expected)
 assert [lib.field(i) for i in range(5)]==state,(raw.hex(),state)
 for k,value in calls.items():assert ctypes.c_uint32.in_dll(lib,k).value==value,(raw.hex(),k,value)
 checks+=1;return dict(result=rc,context=state,calls=calls)
fixtures=[]
def fixture(name,kind,values,raw):
 result=check(raw);assert result['result']==0
 fixtures.append(dict(name=name,kind=kind,values=values,hex=raw.hex(),reference=result))
fixture('compass-stop','compassStop',[],b'\x0a\0');fixture('compass-default','compassDefault',[],b'\x0a\1')
for interval,delta in [(0,0),(49,65535),(50,5),(1000,5),(2000,256),(2001,360),(65535,65535)]:fixture('compass-%s-%s'%(interval,delta),'compassConfig',[interval,delta],b'\x0a\2'+struct.pack('<HH',interval,delta))
fixture('als-query','alsQuery',[],b'\x10\0');fixture('als-stop','alsStop',[],b'\x10\2')
for interval,delta,heartbeat,lease in [(500,1,5000,0),(500,1,5000,1),(0,0,0,0),(99,65535,65535,1),(100,1,1,0),(5000,256,5000,1),(5001,0,0,1),(65535,65535,65535,0)]:fixture('als-%s-%s-%s-%s'%(interval,delta,heartbeat,lease),'alsStart',[interval,delta,heartbeat,lease],b'\x10\1'+bytes([lease])+struct.pack('<HHH',interval,delta,heartbeat))
for f in fixtures:
 raw=bytes.fromhex(f['hex'])
 for high in [0,128]:
  packet=bytes([raw[0]|high])+raw[1:]
  for lens in [1,2]:
   for present in [0,1]:
    check(packet,lens,present);check(packet+b'ignored',lens,present)
    for n in range(len(packet)):check(packet[:n],lens,present)
# All unknown ops, optional ALS partial pairs and raw flags; no field masking.
for mode in [10,138,16,144]:
 for op in range(256):
  check(bytes([mode,op]));check(bytes([mode,op]),lens=2)
for flags in range(256):
 raw=bytes([16,1,flags])+struct.pack('<HHH',65535,256,0)
 for n in range(2,10):check(raw[:n])
for start_error,config_error in [(4,0),(0,5),(0,0)]:
 for raw in [b'\x0a\1',b'\x0a\2'+struct.pack('<HH',0,65535),b'\x10\1']:
  check(raw,start_error=start_error,config_error=config_error)
report=dict(upstream_commit=pins['commit'],source_sha256=digests,extraction_sha256={n:hashlib.sha256(s.encode()).hexdigest() for n,s in [('compass_branch',compass),('als_dispatch_branch',alsbranch),('als_control',control),('als_start_parameter_prefix',start)]},checks=checks,fixtures=fixtures,build_command=cmd,boundary='Original compass dispatcher and ALS control plus unchanged ALS clamp/store prefix. Native context, sensor callbacks, reports, hook installation/open and lease lifecycle mocked/excluded. No Memo native support inferred.')
(HERE/'reference.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['// SPDX-License-Identifier: MIT','// Independently struct.pack encoded and checked by pinned original C control branches.','// Evidence: analysis/sensor-swift-20261102/reference.json','enum SensorReferenceVectors {','    static let cases: [(name: String, kind: String, values: [Int], wire: String)] = [']
for f in fixtures:lines.append(f'        ("{f["name"]}", "{f["kind"]}", {f["values"]}, "{f["hex"]}"),')
lines+=['    ]','}',''];(ROOT/'swift/MemoMindKit/Tests/MemoMindCoreTests/SensorReferenceVectors.swift').write_text('\n'.join(lines));print(checks,'pinned original sensor control checks passed')
