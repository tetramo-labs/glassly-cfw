"""Historical real application transcript plus wire/state fault mutations."""
if not __debug__:raise RuntimeError('Refuse -O')
import copy,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('verify_ota',HERE/'verify-ota.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
ROOT=v.ROOT;capture=ROOT/'captures/swift-mac-diagnostics-flash-20261102-01'
rows=[v.loads(x) for x in (capture/'trace.jsonl').read_bytes().splitlines()];result=v.loads((capture/'result.json').read_bytes());image=(ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
assert v.sha(image)=='a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917'
positive=v.verify(rows,image,result);assert positive['blocks']==545 and positive['chunks']==3812
cases=[dict(name='historical_real_complete_diagnostic',passed=True)]
def selected(r,ev,cmd):return r['event']==ev and r.get('session')=='ota' and bytes.fromhex(r['hex'])[4]==cmd
def mutate_byte(data,ev,cmd,at,value):
 for r in data:
  if selected(r,ev,cmd):
   b=bytearray.fromhex(r['hex']);b[at]=value;r['hex']=b.hex();return
 raise AssertionError('No mutation target')
def negative(name,mutator):
 data=copy.deepcopy(rows);res=copy.deepcopy(result);mutator(data,res)
 try:v.verify(data,image,res)
 except (AssertionError,ValueError,KeyError) as e:cases.append(dict(name=name,passed=True,rejected=str(e)[:160]))
 else:raise AssertionError('Accepted '+name)
negative('bad_block_transport_status',lambda d,r:mutate_byte(d,'receive',0xe5,7,1))
negative('wrong_block_ack_sequence',lambda d,r:mutate_byte(d,'receive',0xe5,8,99))
negative('nonzero_ack_delay',lambda d,r:mutate_byte(d,'receive',0xe5,-2,1))
negative('wrong_first_requested_offset',lambda d,r:mutate_byte(d,'receive',0xe3,13,19))
negative('unsupported_update_result',lambda d,r:mutate_byte(d,'receive',0xe2,9,2))
negative('wrong_reboot_status',lambda d,r:mutate_byte(d,'receive',3,9,1))
negative('bad_ota_footer',lambda d,r:mutate_byte(d,'receive',0xe5,-1,0))
def paired_tx(d,cmd,at):
 index=next(i for i,r in enumerate(d) if selected(r,'transmitSubmission',cmd));old=d[index]['hex'];b=bytearray.fromhex(old);b[at]^=1
 d[index]['hex']=b.hex();next(r for r in d[index+1:] if r['event']=='transmitCompletion' and r.get('session')=='ota' and r['hex']==old)['hex']=b.hex()
negative('chunk_crc_corruption_with_successful_matching_completion',lambda d,r:paired_tx(d,0xe5,-2))
negative('chunk_offset_corruption_with_successful_matching_completion',lambda d,r:paired_tx(d,0xe5,11))
negative('chunk_payload_corruption_with_successful_matching_completion',lambda d,r:paired_tx(d,0xe5,12))
negative('file_header_corruption_with_successful_matching_completion',lambda d,r:paired_tx(d,0xe2,8))
def duplicate_ack(d,r):
 i=next(i for i,x in enumerate(d) if selected(x,'receive',0xe5));d.insert(i+1,copy.deepcopy(d[i]))
negative('duplicate_block_ack',duplicate_ack)
def fail_completion(d,r):next(x for x in d if x['event']=='transmitCompletion')['status']=False
negative('boolean_false_completion_not_status_zero',fail_completion)
def wrong_summary(d,r):
 r['blocks']-=1;d[-1]['result']=copy.deepcopy(r)
negative('reported_block_count_mismatch',wrong_summary)
def no_completion(d,r):d.pop(next(i for i,x in enumerate(d) if x['event']=='transmitCompletion'))
negative('missing_tx_completion',no_completion)
negative('truncated_attempt',lambda d,r:d.__delitem__(slice(-4,None)))
# Native MTU boundaries must not become application frame boundaries.
split=copy.deepcopy(rows)
i=next(i for i,r in enumerate(split) if selected(r,'transmitSubmission',0xe5))
submission=split[i];completion=split[i+1];assert completion['event']=='transmitCompletion' and completion['hex']==submission['hex']
b=bytes.fromhex(submission['hex']);replacement=[]
for part in (b[:19],b[19:]):
 for base in (submission,completion):
  row=copy.deepcopy(base);row['hex']=part.hex();row['bytes']=len(part);replacement.append(row)
# Equal callback timestamps are allowed; preserve monotonically ordered log time.
for row in replacement:row['uptimeSeconds']=submission['uptimeSeconds']
split[i:i+2]=replacement
assert v.verify(split,image,result)['reconstructed_sha256']==v.sha(image)
cases.append(dict(name='split_native_MTU_chunk_submissions',passed=True))
out=HERE/'verifier-selftest-v2.json' ;assert not out.exists();out.write_text(json.dumps(dict(passed=True,cases=len(cases),results=cases,fixture_capture=str(capture.relative_to(ROOT)),fixture_trace_sha256=v.sha((capture/'trace.jsonl').read_bytes()),fixture_image_sha256=v.sha(image),verifier_sha256=v.sha((HERE/'verify-ota.py').read_bytes()),test_source_sha256=v.sha(Path(__file__).read_bytes()),fixture_not_reset_undo_candidate=True,device_actions=False),indent=2)+'\n')
print(json.dumps(dict(passed=True,cases=len(cases))))
