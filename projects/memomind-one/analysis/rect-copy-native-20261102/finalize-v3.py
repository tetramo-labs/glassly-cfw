"""Publish completed hardware evidence and update current status after all gates."""
from pathlib import Path
import json,hashlib,datetime
if not __debug__:raise RuntimeError('Assertions required')
root=Path('analysis/rect-copy-native-20261102')
def read(p):return json.loads(Path(p).read_text())
def save(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n')
def pin(p):
 p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
assert read(root/'trace-verification.json')['entire_ota_reconstructed']
preflight=read(root/'preflight-verification.json');assert preflight['complete']
smoke=read(root/'smoke-verification.json');assert smoke['complete']
visual=read(root/'visual-confirmation.json');assert visual['copied_pattern_visible']
partial=read(root/'smoke-02-partial-verification.json');assert not partial['complete'] and partial['commands_before_disconnect_verified']
cleanup=read(root/'cleanup-verification.json');assert cleanup['complete'] and cleanup['clear_acknowledged']
reg=read('analysis/regression-20261102-01/report.json');assert reg['all_required_offline_suites_passed'] and not reg['sources_changed_during_run']
source=read('analysis/regression-20261102-01/source-sha256-final.json');assert all(pin(k)['sha256']==v for k,v in source.items())
python=read('analysis/regression-20261102-01/firmware_transport.json')
# Actual runner totals are checked before reporting, not guessed from prior counts.
print('Python report:',python)
import re
log=Path('analysis/regression-20261102-01/native_swift.stdout').read_text()+Path('analysis/regression-20261102-01/native_swift.stderr').read_text()
counts=[int(x) for x in re.findall(r'Executed (\d+) tests?, with 0 failures',log)];assert counts
swift=max(counts);stages=sum(x.get('parity_required',True) for x in reg['results'])
assert stages==84 and swift==63
pycount=python['tests_run'] if 'tests_run' in python else python['testsRun']
captures=sorted(Path('captures').glob('swift-mac-rect-copy-*-20261102-*'))
for c in captures:
 manifest=c/'capture-manifest.json'
 if not manifest.exists():save(manifest,{'format':'memomind-native-mac-capture-manifest-v1','files':[pin(p) for p in sorted(c.rglob('*')) if p.is_file()]})
 for f in read(manifest)['files']:assert pin(f['path'])==f
pins=read(root/'candidate-pins.json')
report={'format':'memomind-native-rect-copy-hardware-v1','utc':now,'state':'Mode9 installed, exact boot header verified, overlap/copy commands acknowledged, copied pattern confirmed visible, malformed requests rejected, session cleared','candidate':pin('captures/firmware/rect-copy-001/firmware.bin'),'runtime':pin('runtime/build/rect-copy-001/graphics.bin'),'current_installed_release':'rect-copy-001','installed':True,'boot_verified':True,'added_command_mode':9,'hardware_commands_executed':True,'visible_copy_confirmed':True,'background_gray4':0,'transfer_verification':str(root/'trace-verification.json'),'preflight_verification':str(root/'preflight-verification.json'),'smoke_verification':str(root/'smoke-verification.json'),'visual_confirmation':str(root/'visual-confirmation.json'),'visual_repeat_verification':str(root/'smoke-02-partial-verification.json'),'repeat_disconnected_after_seconds':partial['seconds_until_disconnect'],'separate_cleanup_verification':str(root/'cleanup-verification.json'),'capture_manifests':[str(c/'capture-manifest.json') for c in captures],'offline_runtime_report':'analysis/rect-copy-001/report.json','swift_encoder_report':'analysis/rect-copy-swift-20261102/report.json','independent_review':'analysis/rect-copy-review-20261102/report.md','smoke_review':'analysis/rect-copy-swift-20261102/smoke-review.json','aggregate':'analysis/regression-20261102-01/report.json','required_stages_passed':stages,'python_tests_passed':pycount,'swift_tests_passed':swift,'ios15_core_typecheck_passed':read(root/'ios-core.json')['returncode']==0,'regression_source_files_rechecked':len(source),'source_drift':False,'excluded_features':['Bluetooth keyboard/HOGP accessory support'],'full_command_parity':False,'full_g2_parity':False,'next_command_modes':[8,15],'canary_repeated':False,'limits':['8192-byte native ingress and64KiB cache remain; native full capacity is pending.','Single display first/left rectangle pair; no stereo claim.','User confirms visible copy; no hardware pixel readback or exact per-pixel physical comparison.','Independent decoded command/snapshot verification does not prove physical overlap pixels or continuous retention.','Application trace, not independent HCI/radio capture.','Native timing/performance, other commands and storage integration remain incomplete.','First90s run completed and cleared; user missed it. Repeat was visibly confirmed but Bluetooth closed after50s; a separate reconnect/header check/clear succeeded. Disconnect cause is unproven.']}
assert not (root/'report.json').exists();save(root/'report.json',report)
status='Modes6/3/9 installed and boot verified. User confirmed RLE keyframe/delta and second copied pattern; overlap/copy ACKs and invalid rejection verified. Next modes8/15.'
for path in ['analysis/parity-status.json','analysis/storage-integration-plan.json']:
 d=read(path);d['command_priority']['first_stage_status']=status;d['command_priority']['completed_visible_modes']=[6,3,9];d['command_priority']['next']=[8,15]
 d.pop('current_device_boot_verification_pending',None)
 d['rect_copy_candidate']={'installed':True,'firmware':'captures/firmware/rect-copy-001','runtime':'runtime/build/rect-copy-001','hardware_report':str(root/'report.json'),'ota_transfer_verified':True,'post_reboot_verified':True,'hardware_smoke_verified':True,'visible_output_confirmed':True}
 d['raster_command_candidate']['installed']=False;d['raster_command_candidate']['superseded_by']='rect-copy-001 (retains modes6/3)'
 if 'updated_utc' in d:d['updated_utc']=now
 if 'latest_offline_regression' in d:
  d['latest_offline_regression'].update(report=report['aggregate'],stages=stages,python_tests=pycount,swift_tests=swift)
  d['current_device_image_sha256']=pins['image_sha256'];d['current_device_runtime_sha256']=pins['runtime_sha256'];d['current_device_build']='runtime/build/rect-copy-001'
  d['native_swift_port']['swift_tests_passed']=swift;d['native_swift_port']['latest_command_hardware_report']=str(root/'report.json')
  d['verified'].append('Mode9 installed/boot verified: overlap-safe rectangle copy, odd coordinates and dimensions; native Swift copy accepted and second RLE/checkerboard group confirmed visible. Invalid requests rejected and session cleared.')
 else:d['implemented']['regression']=report['aggregate']
 save(path,d)
p=Path('README.md');s=p.read_text();s=s.replace('The first command-parity release is installed and boot verified:', 'The installed command-parity firmware retains');s=s.replace('All 75 required offline stages pass, including 220 Python tests, 56 Swift tests','All 84 required offline stages pass, including '+str(pycount)+' Python tests, 63 Swift tests')
s=s.replace('and 56 Swift tests pass.','and 63 Swift tests pass.')
s=s.replace('All75\nrequired stages pass under the keyboard-excluded scope (220 Python and56 Swift\ntests). Modes9/8/15 are next; full command/capacity parity remains incomplete.', 'The subsequent mode9 release adds overlapping rectangle copy with odd-pixel\nboundaries. It is installed and boot verified; the user confirmed a second copied\nRLE/checkerboard group on black. All84 required stages pass ('+str(pycount)+' Python and63 Swift\ntests). Modes8/15 are next; full command/capacity parity remains incomplete.')
s+='\nLatest command release: [mode9 hardware evidence](analysis/rect-copy-native-20261102/report.json).\n';p.write_text(s)
p=Path('tests/g2_compat/COMMAND_PARITY.md');s=p.read_text();s=s.replace('Missing dispatcher/portable copy primitive. Pure bounded RAM operation.','Implemented behind `--rect-copy`: bounds-checked overlapping copy, odd-nibble preservation, first/left pair. Native Swift smoke acknowledged and user confirmed second copied pattern; exact physical pixel comparison/performance remain unverified.')
s=s.replace('The next command slice is mode9 rectangle copy, followed by modes8 and15.','Mode9 is now installed and visibly confirmed; modes8 and15 remain next.\nSee [mode9 hardware evidence](../../analysis/rect-copy-native-20261102/report.json).');p.write_text(s)
p=Path('swift/MemoMindKit/README.md');s=p.read_text();s=s.replace('`raster-commands-001` with optional modes3/6. All require', '`raster-commands-001` with optional modes3/6, and `rect-copy-001` with mode9. All require');s+='\n`RasterCommands.rectangleCopy(source:destination:)` emits mode9 using\n`RasterRectangle` pixel bounds. Positive matching rectangles must fit600×350; odd\ncoordinates/dimensions, overlaps and self-copy are supported. The exact\n`rect-copy-001` catalog image was flashed natively and boot verified, and the user\nconfirmed the second copied pattern. [Hardware evidence](../../analysis/rect-copy-native-20261102/report.json).\n';p.write_text(s)
files=set(p for p in root.rglob('*') if p.is_file())
for base in [*captures,Path('analysis/rect-copy-001'),Path('analysis/rect-copy-review-20261102'),Path('analysis/rect-copy-swift-20261102'),Path('captures/firmware/rect-copy-001'),Path('runtime/build/rect-copy-001')]:files.update(p for p in base.rglob('*') if p.is_file())
files.update(Path(p) for p in ['README.md','swift/MemoMindKit/README.md','tests/g2_compat/COMMAND_PARITY.md','analysis/parity-status.json','analysis/storage-integration-plan.json',report['aggregate'],'analysis/regression-20261102-01/source-sha256-final.json','tests/run_tests.py'])
manifest=Path('analysis/evidence/rect-copy-hardware-20261102.json');assert not manifest.exists()
save(manifest,{'format':'memomind-evidence-supplement-v1','utc':now,'scope':'Mode9 implementation, independent review, native Swift encoder/catalog, native Mac OTA and boot, visible overlap/copy smoke with rejection and clear; original evidence preserved.','previous_supplement_preserved':pin('analysis/evidence/rect-copy-transfer-20261102.json'),'capture_pins_verified':True,'files':[pin(p) for p in sorted(files)]})
assert all(pin(f['path'])==f for f in read(manifest)['files'])
print(json.dumps({'report':str(root/'report.json'),'evidence':str(manifest),'pinned_files':len(files),'capture_manifests_verified':len(captures)}))
