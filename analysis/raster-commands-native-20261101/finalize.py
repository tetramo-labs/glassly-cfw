from pathlib import Path
import json,hashlib,datetime
root=Path('analysis/raster-commands-native-20261101')
def read(p):return json.loads(Path(p).read_text())
def save(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n')
def pin(p):
 p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
smoke=read(root/'smoke-verification.json');assert smoke['complete']
assert read(root/'preflight-verification.json')['complete']
assert read(root/'trace-verification.json')['entire_ota_reconstructed']
assert read(root/'visual-confirmation.json')['full_frame_and_bbox_delta_visible']
source=read('analysis/regression-20261101-07/source-sha256-final.json')
assert all(pin(k)['sha256']==v for k,v in source.items())
captures=[Path('captures')/name for name in ['swift-mac-raster-flash-20261101-02','swift-mac-raster-preflight-20261101-01','swift-mac-raster-preflight-20261101-02','swift-mac-raster-smoke-20261101-01','swift-mac-raster-smoke-20261101-02']]
for c in captures:
 manifest=c/'capture-manifest.json'
 assert not manifest.exists()
 save(manifest,{'format':'memomind-native-mac-capture-manifest-v1','files':[pin(p) for p in sorted(c.rglob('*')) if p.is_file()]})
 for f in read(manifest)['files']:assert pin(f['path'])==f
report={'format':'memomind-native-raster-hardware-v1','utc':now,'state':'Installed and boot verified; full-frame RLE and bbox delta acknowledged and visible to user; malformed commands rejected; session cleared','candidate':pin('captures/firmware/raster-commands-001/firmware.bin'),'runtime':pin('runtime/build/raster-commands-001/graphics.bin'),'current_installed_release':'raster-commands-001','installed':True,'boot_verified':True,'command_modes':[6,3],'hardware_commands_executed':True,'visible_output_confirmed':True,'transfer_verification':str(root/'trace-verification.json'),'preflight_verification':str(root/'preflight-verification.json'),'smoke_verification':str(root/'smoke-verification.json'),'visual_confirmation':str(root/'visual-confirmation.json'),'capture_manifests':[str(c/'capture-manifest.json') for c in captures],'first_smoke_failure':{'capture':'captures/swift-mac-raster-smoke-20261101-01','cause':'Test helper expected ok without presentation:scheduled. Firmware returned its documented scheduled reply. Helper and verifier corrected in v2; original files and capture retained.','keyframe_submitted':True,'delta_submitted':False},'aggregate':'analysis/regression-20261101-07/report.json','required_stages_passed':75,'python_tests_passed':220,'swift_tests_passed':56,'scope_tests_passed':8,'regression_source_files_rechecked':len(source),'source_drift':False,'required_host_scenarios':40,'required_host_assertion_sites':660,'required_bun_cases':11,'excluded_features':['Bluetooth keyboard/HOGP accessory support'],'previous_canary_hardware_passed':'analysis/native-mac-canary-20261101/report.json','canary_repeated_on_raster_image':False,'full_command_parity':False,'full_g2_parity':False,'next_command_modes':[9,8,15],'limits':['Current native ingress8192 bytes and cache64KiB; full capacity remains pending.','Single display, first/left bbox mapping; no stereo claim.','RLE sent over native GM; no outer G2/zlib transport added.','Application TX/RX trace, not separate HCI/radio observation.','User confirmed letters/checkerboard; no hardware pixel readback or pixel-perfect display comparison.','Other commands, native performance, storage integration and physical input acceptance remain unfinished.']}
assert not (root/'report.json').exists();save(root/'report.json',report)
status='Modes6/3 installed and boot verified; native Swift commands acknowledged, malformed commands rejected, user confirmed RLE/checkerboard visible, session cleared. Next modes9/8/15.'
for path in ['analysis/parity-status.json','analysis/storage-integration-plan.json']:
 d=read(path);d['command_priority']['first_stage_status']=status
 d['raster_command_candidate'].update(hardware_report=str(root/'report.json'),hardware_smoke_verified=True,visible_output_confirmed=True)
 if 'updated_utc' in d:d['updated_utc']=now
 if 'verified' in d:d['verified'].append('Native Mac raster OTA reconstructed byte-for-byte; live256-byte header matches. Modes6/3 acknowledged and RLE/checkerboard visibility confirmed by user; malformed inputs rejected and display cleared.')
 save(path,d)
p=Path('README.md');s=p.read_text();old='''The first command-parity candidate adds mode6 RLE keyframes and mode3 rectangle
deltas, with native Swift encoders. All75 required stages pass under the revised
keyboard-excluded scope. Its initial update connection timed out before any data
was sent, so the candidate is not installed yet. See [command map](tests/g2_compat/COMMAND_PARITY.md)
and [candidate status](analysis/raster-commands-native-20261101/pending-report.json).'''
new='''The first command-parity release is installed and boot verified: mode6 RLE
keyframes and mode3 rectangle deltas, with native Swift encoders. The full OTA was
independently reconstructed, and the user confirmed the RLE letters and checkerboard
were visible. Malformed commands were rejected and the session cleared. All75
required stages pass under the keyboard-excluded scope (220 Python and56 Swift
tests). Modes9/8/15 are next; full command/capacity parity remains incomplete.
See [command map](tests/g2_compat/COMMAND_PARITY.md) and
[hardware evidence](analysis/raster-commands-native-20261101/report.json).'''
assert old in s;p.write_text(s.replace(old,new))
p=Path('tests/g2_compat/COMMAND_PARITY.md');s=p.read_text();assert s.count('Hardware verification pending.')==2
s=s.replace('Hardware verification pending.','Native Mac smoke acknowledged; user confirmed RLE letters and checkerboard visible. Pixel-perfect display comparison and performance remain unverified.')
s+='\nThe mode3/6 release is installed and boot verified. The native Swift smoke,\nindependent trace verification and user visibility confirmation are recorded in\n[hardware evidence](../../analysis/raster-commands-native-20261101/report.json).\nThe next command slice is mode9 rectangle copy, followed by modes8 and15.\n';p.write_text(s)
p=Path('swift/MemoMindKit/README.md');s=p.read_text();s+='\nThe `raster-commands-001` release has now been flashed directly from this Mac and\nboot verified. Native Swift mode6/mode3 commands produced the RLE/checkerboard\npattern confirmed by the user; malformed commands were rejected and the display\ncleared. See [hardware evidence](../../analysis/raster-commands-native-20261101/report.json).\n';p.write_text(s)
previous=Path('analysis/evidence/raster-commands-20261101.json')
files=set(p for p in root.rglob('*') if p.is_file())
for c in captures:files.update(p for p in c.rglob('*') if p.is_file())
files.update(Path(p) for p in ['README.md','swift/MemoMindKit/README.md','tests/g2_compat/COMMAND_PARITY.md','analysis/parity-status.json','analysis/storage-integration-plan.json','analysis/regression-20261101-07/report.json','analysis/regression-20261101-07/source-sha256-final.json'])
manifest=Path('analysis/evidence/raster-hardware-20261101.json');assert not manifest.exists()
save(manifest,{'format':'memomind-evidence-supplement-v1','utc':now,'scope':'Native Mac raster OTA, exact postboot header and read-only storage preflight, visible mode6/mode3 hardware smoke, malformed rejection, clear; includes preserved helper-v1 failure and corrected v2.','previous_supplement_preserved':pin(previous),'capture_pins_verified':True,'files':[pin(p) for p in sorted(files)]})
assert all(pin(f['path'])==f for f in read(manifest)['files'])
print(json.dumps({'report':str(root/'report.json'),'evidence':str(manifest),'pinned_files':len(files),'capture_manifests_verified':len(captures)}))
