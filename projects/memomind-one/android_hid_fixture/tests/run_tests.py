#!/usr/bin/env python3
"""Compile the APK's actual ATT model; independently decode HID short items."""
import hashlib,json,os,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
JDK=pathlib.Path(os.environ.get('HID_JDK','/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home'))
out=ROOT/'build/tests';out.mkdir(parents=True,exist_ok=True)
subprocess.run([str(JDK/'bin/javac'),'-d',str(out),str(ROOT/'src/org/memomind/research/hid/HidModel.java'),str(ROOT/'tests/HidModelTest.java'),str(ROOT/'src/org/memomind/research/hid/ControllerLease.java'),str(ROOT/'tests/ControllerLeaseTest.java')],check=True)
r=subprocess.run([str(JDK/'bin/java'),'-cp',str(out),'HidModelTest'],check=True,text=True,capture_output=True)
life=subprocess.run([str(JDK/'bin/java'),'-cp',str(out),'ControllerLeaseTest'],check=True,text=True,capture_output=True)
print(life.stdout,end='');lifecycle_checks=int(life.stdout.strip().split('=')[1])
print(r.stdout,end='');v=dict(line.split('=',1) for line in r.stdout.strip().splitlines())
b=bytes.fromhex(v['report_map']);i=0;size=count=rid=page=0;bits={};collection=0;app=None;usage=None;logical_min=logical_max=None;inputs=[];outputs=[]
while i<len(b):
 prefix=b[i];i+=1;assert prefix!=0xfe,'long items not expected'
 n=[0,1,2,4][prefix&3];assert i+n<=len(b)
 val=int.from_bytes(b[i:i+n],'little');i+=n;typ=(prefix>>2)&3;tag=prefix>>4
 if typ==1:
  if tag==0:page=val
  elif tag==1:logical_min=val
  elif tag==2:logical_max=val
  elif tag==7:size=val
  elif tag==8:rid=val
  elif tag==9:count=val
 elif typ==2 and tag==0:usage=val
 elif typ==0:
  if tag==10:
   if collection==0:app=(page,usage,val)
   collection+=1
  elif tag==12:collection-=1;assert collection>=0
  elif tag in (8,9):
   assert rid==1 and size>0 and count>0
   key=(rid,'input' if tag==8 else 'output');bits[key]=bits.get(key,0)+size*count
   (inputs if tag==8 else outputs).append((page,size,count,val,logical_min,logical_max))
  usage=None
assert collection==0 and app==(1,6,1)
assert bits=={(1,'input'):64,(1,'output'):8}
assert inputs==[(7,1,8,2,0,1),(7,8,1,1,0,1),(7,8,6,0,0,101)],inputs
assert outputs==[(8,1,5,2,0,1),(8,3,1,1,0,1)],outputs
assert v['input_reference']=='0101' and v['output_reference']=='0102'
assert v['hid_info']=='11010002'
report={'kind':'offline-JVM-model-and-independent-HID-parser','java_checks':int(v['checks']),'lifecycle_checks':lifecycle_checks,'report_map_bytes':len(b),'report_map_sha256':hashlib.sha256(b).hexdigest(),'report_id':1,'input_bytes_without_id':8,'output_bytes_without_id':1,'app_usage_page':1,'app_usage':6,'android_callbacks_emulated':False,'device_actions':False}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
