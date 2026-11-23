"""Independent Python replay of a completed native Mac application trace.

TX submissions must each have a successful matching native completion. The
existing Python transaction then regenerates every outgoing application frame
from the reproduced image and consumes captured device replies in order.
This is application trace evidence, not an independent HCI/radio capture.
"""
import json,hashlib,sys
if not __debug__:
    raise RuntimeError('Verification requires Python assertions; optimized execution is refused')
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from decode_memomind import OtaStream
from memomind_flasher import ReplayTransport,StockTransaction
from memomind_transport import gm_frames
capture=ROOT/'captures/swift-mac-text-flash-20261102-02'
source=(capture/'trace.jsonl').read_bytes(); rows=[json.loads(x) for x in source.splitlines()]
native=json.loads((capture/'result.json').read_text())
assert native['state']=='reboot acknowledged' and native['transferredRange']==[18,2229380]
for session in ('control','ota'):
 submissions=[r['hex'] for r in rows if r.get('session')==session and r['event']=='transmitSubmission']
 completions=[r for r in rows if r.get('session')==session and r['event']=='transmitCompletion']
 assert [r['hex'] for r in completions]==submissions and all(r['status']==0 for r in completions)
notify=gm_frames(0x15,1,0x1c,bytes.fromhex('0800000101'))[0]
reply=gm_frames(0x15,1,0x1c,bytes.fromhex('0600000101'))[0]
start=next(i for i,r in enumerate(rows) if r.get('session')=='control' and r['event']=='transmitSubmission' and bytes.fromhex(r['hex'])==notify)
recorded=[]; parsers={0:OtaStream(),1:OtaStream()}
for index,r in enumerate(rows[start:],start):
 if r['event'] not in ('receive','transmitSubmission'):continue
 raw=bytes.fromhex(r['hex']); direction=int(r['event']=='receive')
 if r.get('session')=='control':
  if (direction==0 and raw==notify) or (direction==1 and raw==reply):recorded.append({'frame':index,'direction':direction,'channel':5,'data':raw})
 elif r.get('session')=='ota':
  for frame in parsers[direction].feed(raw):recorded.append({'frame':index,'direction':direction,'channel':6,'data':frame})
assert all(not p.buffer for p in parsers.values())
assert len([r for r in recorded if r['channel']==5])==2
image=(ROOT/'captures/firmware/text-commands-001/firmware.bin').read_bytes()
manifest=json.loads((ROOT/'captures/firmware/text-commands-001/manifest.json').read_text())
transport=ReplayTransport(recorded)
result=StockTransaction(transport,image,native['device'],native['device']['mac'],pace=0,
 stock_source=(ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes(),runtime_manifest=manifest,
 runtime_blob=(ROOT/'runtime/build/text-commands-001/graphics.bin').read_bytes()).run()
assert transport.position==len(recorded)
assert result['blocks']==native['blocks'] and result['chunks']==native['chunks']
headers=[r["data"][8:-1] for r in recorded if r["channel"]==6 and r["direction"]==0 and r["data"][4]==0xe2]
assert headers==[image[:18]]
recovered=bytearray(headers[0]); chunks=0
for r in recorded:
 frame=r['data']
 if r['channel']!=6 or r['direction']!=0:continue
 if frame[4]==0xe2:assert frame[8:-1]==image[:18]
 if frame[4]==0xe5:
  offset=int.from_bytes(frame[8:12],'big'); data=frame[12:-5]
  assert offset==len(recovered);recovered.extend(data);chunks+=1
assert bytes(recovered)==image and chunks==native['chunks']
report={**result,'format':'memomind-native-mac-independent-python-replay-v1',
 'trace_sha256':hashlib.sha256(source).hexdigest(),'captured_records_consumed':len(recorded),
 'outgoing_frames_byte_identical':transport.writes,'incoming_frames_consumed':transport.reads,
 'outgoing_wire_sha256':transport.outgoing_hash.hexdigest(),
 'native_write_submissions_all_completed':True,'entire_ota_reconstructed':True,
 'reconstructed_bytes':len(recovered),'reconstructed_sha256':hashlib.sha256(recovered).hexdigest(),
 'control_link_preserved':True,'replay_control_link_virtual_disconnect_only':True,
 'limitations':['Application TX/RX trace; not a separate HCI/radio observation.','Reboot ACK alone does not prove successful boot.']}
(ROOT/'analysis/text-native-20261102/trace-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
