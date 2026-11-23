"""Seal completed mode8 hardware evidence and update mutable status documents."""
from pathlib import Path
import json,hashlib,datetime,re
if not __debug__:raise RuntimeError('Assertions required')
root=Path('analysis/bundle-native-20261102')
def read(p):return json.loads(Path(p).read_text())
def save(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n')
def pin(p):
 p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
assert read(root/'trace-verification.json')['entire_ota_reconstructed']
assert read(root/'preflight-verification.json')['complete']
smoke=read(root/'smoke-verification.json');assert smoke['complete'] and smoke['cleared']
visual=read(root/'visual-confirmation.json');assert visual['bundle_pattern_visible']
regpath='analysis/regression-20261102-02/report.json';reg=read(regpath)
assert reg['all_required_offline_suites_passed'] and not reg['sources_changed_during_run']
source=read('analysis/regression-20261102-02/source-sha256-final.json');assert all(pin(k)['sha256']==v for k,v in source.items())
python=read('analysis/regression-20261102-02/firmware_transport.json');assert python['all_required_tests_passed'] and not python['skipped']
log=Path('analysis/regression-20261102-02/native_swift.stdout').read_text()+Path('analysis/regression-20261102-02/native_swift.stderr').read_text()
counts=[int(x) for x in re.findall(r'Executed (\d+) tests?, with 0 failures',log)];assert counts
swift=max(counts);stages=sum(x.get('parity_required',True) for x in reg['results']);pycount=python['tests_run']
assert stages==94 and swift==79
pins=read(root/'candidate-pins.json');assert read(root/'ios-core.json')['returncode']==0
captures=sorted(Path('captures').glob('swift-mac-bundle-*-20261102-*'))
for c in captures:
 manifest=c/'capture-manifest.json'
 if not manifest.exists():save(manifest,{'format':'memomind-native-mac-capture-manifest-v1','files':[pin(p) for p in sorted(c.rglob('*')) if p.is_file()]})
 for f in read(manifest)['files']:assert pin(f['path'])==f
report={'format':'memomind-native-command-bundle-hardware-v1','utc':now,'state':'Mode8 installed and boot verified; bundled B8/checkerboard pattern visually confirmed; final cache reply and ordered settled notifications verified; invalid bundles rejected; display cleared','candidate':pin('captures/firmware/bundle-commands-001/firmware.bin'),'runtime':pin('runtime/build/bundle-commands-001/graphics.bin'),'current_installed_release':'bundle-commands-001','installed':True,'boot_verified':True,'added_command_mode':8,'bundle_modes':[3,6,9,19,20,36,37,38,39,40,41],'maximum_segments':255,'mode15_supported':False,'hardware_commands_executed':True,'visible_bundle_confirmed':True,'transfer_verification':str(root/'trace-verification.json'),'preflight_verification':str(root/'preflight-verification.json'),'smoke_verification':str(root/'smoke-verification.json'),'visual_confirmation':str(root/'visual-confirmation.json'),'capture_manifests':[str(c/'capture-manifest.json') for c in captures],'offline_runtime_report':'analysis/bundle-commands-001/report.json','swift_encoder_report':'analysis/bundle-swift-20261102/report.json','independent_review':'analysis/bundle-review-20261102/implementation-review.json','aggregate':regpath,'required_stages_passed':stages,'python_tests_passed':pycount,'swift_tests_passed':swift,'ios15_core_typecheck_passed':True,'regression_source_files_rechecked':len(source),'source_drift':False,'excluded_features':['Bluetooth keyboard/HOGP accessory support'],'full_command_parity':False,'full_g2_parity':False,'next_command_modes':[15],'canary_repeated':False,'semantics':['One full-batch prepare; sequential supported children; one final explicit presentation on success.','Only final cache scratch is returned; earlier child replies are not independently retained.','Earlier mutations persist if a later child fails; final explicit presentation is suppressed.','Collector holds up to510 uint16 tags (1020 bytes), covering proven256 callbacks for255 segments plus initial pending tag.','Ordered native response then settled send calls; actual short smoke received all expected9 notifications in order.'],'limits':['Mode15 remains unsupported, including as a bundle child.','Native8192-byte ingress and64KiB cache remain; full capacity is pending.','No rollback or physical invisibility guarantee on late failure: LVGL shares the mutable raster.','Single-presentation call count proved in host/RV32 tests, not by physical panel instrumentation.','Native notification sends remain best effort; maximal batches can delay display work.','No hardware pixel readback, physical exact-pixel comparison or continuous retention proof.','Application trace, not independent HCI/radio capture; fragment ACK order is enforced by live Swift Session, not separately checked by smoke verifier.','Remaining commands, native performance and storage integration are unfinished.']}
assert not (root/'report.json').exists();save(root/'report.json',report)
status='Modes6/3/9/8 installed and boot verified. Visible bundled drawing, finalcache reply, orderedsettled notifications and malformedbundle rejection verified. Next mode15; full command/capacity parity remains incomplete.'
for path in ['analysis/parity-status.json','analysis/storage-integration-plan.json']:
 d=read(path);d['command_priority']['first_stage_status']=status;d['command_priority']['completed_visible_modes']=[6,3,9,8];d['command_priority']['next']=[15]
 d.pop('current_device_boot_verification_pending',None)
 d['bundle_candidate']={'installed':True,'firmware':'captures/firmware/bundle-commands-001','runtime':'runtime/build/bundle-commands-001','hardware_report':str(root/'report.json'),'ota_transfer_verified':True,'post_reboot_verified':True,'hardware_smoke_verified':True,'visible_output_confirmed':True,'mode15_supported':False}
 d['rect_copy_candidate']['installed']=False;d['rect_copy_candidate']['superseded_by']='bundle-commands-001 (retains mode9)'
 if 'updated_utc' in d:d['updated_utc']=now
 if 'latest_offline_regression' in d:
  d['latest_offline_regression'].update(report=regpath,stages=stages,python_tests=pycount,swift_tests=swift)
  d['current_device_image_sha256']=pins['image_sha256'];d['current_device_runtime_sha256']=pins['runtime_sha256'];d['current_device_build']='runtime/build/bundle-commands-001'
  d['native_swift_port']['swift_tests_passed']=swift;d['native_swift_port']['latest_command_hardware_report']=str(root/'report.json')
  d['verified'].append('Mode8 installed/boot verified: sequential bundles, finalcache reply, orderedsettled notifications, malformed rejection and native Swift B8/checkerboard bundle visually confirmed; explicit clear acknowledged.')
 else:d['implemented']['regression']=regpath
 save(path,d)
p=Path('README.md');s=p.read_text();s=s.replace('All 84 required offline stages pass, including 221 Python tests, 63 Swift tests',f'All {stages} required offline stages pass, including {pycount} Python tests, {swift} Swift tests').replace('and 63 Swift tests pass.',f'and {swift} Swift tests pass.')
a=s.index('The installed command-parity firmware retains');b=s.index('\n## Evidence and tools',a)
s=s[:a]+f'''The installed command-parity firmware supports mode6 RLE frames, mode3 rectangle
deltas, mode9 overlap copy, and mode8 bundles of supported drawing/cache commands.
Native Swift encoders drive these commands directly from the Mac. The latest OTA
and boot header are verified; the user confirmed the B8/checkerboard bundle pattern.
The hardware smoke also verified final cache replies, ordered settled notifications,
malformed-bundle rejection, and explicit clear. All{stages} required stages pass
({pycount} Python and{swift} Swift tests). Mode15 text, full capacities and remaining
commands are still pending; Bluetooth keyboard support is excluded.
See [command map](tests/g2_compat/COMMAND_PARITY.md) and
[bundle hardware evidence](analysis/bundle-native-20261102/report.json).
'''+s[b:];p.write_text(s)
p=Path('tests/g2_compat/COMMAND_PARITY.md');s=p.read_text();s=s.replace('The mode3/6 release is installed and boot verified.', 'Modes3/6 have live verification and remain in the current firmware.');s=s.replace('Missing executor. Cache preparation understands bundles but does not execute them. Original presentation is atomic, not whole-bundle rollback.','Implemented behind `--command-bundles`: sequential supported children, one final explicit present, final cache scratch, bounded ordered settled collection. Mode15 child unsupported until its adapter exists. Late errors preserve earlier changes; shared pixels can be read by incidental LVGL refresh. Native Swift smoke and visible B8/checkerboard confirmed.')
s=s.replace('modes8 and15 remain next.','mode8 is also installed and visibly confirmed; mode15 remains next.')
s+='\n[Mode8 evidence](../../analysis/bundle-native-20261102/report.json) includes the\nfinal-cache/notification hardware checks and independent trace verification.\n';p.write_text(s)
p=Path('swift/MemoMindKit/README.md');s=p.read_text();s=s.replace('`rect-copy-001` with mode9. All require','`rect-copy-001` with mode9, and `bundle-commands-001` with mode8. All require')
s+='\n`RasterCommands.bundle(_:)` packs up to255 supported commands into the current\n8192-byte native limit; it validates envelopes, not all child semantics. A later\nchild failure does not roll back prior effects. `GMSession` offers an optional\nthrowing `responseFilter` to route same-event notifications separately; callers\nmust also validate unsolicited messages and explicitly drain notifications.\nThe mode8 image is boot verified and its B8/checkerboard bundle was visibly\nconfirmed. [Hardware evidence](../../analysis/bundle-native-20261102/report.json).\n';p.write_text(s)
files=set(p for p in root.rglob('*') if p.is_file())
for base in [*captures,Path('analysis/bundle-commands-001'),Path('analysis/bundle-review-20261102'),Path('analysis/bundle-extension-budget-20261102'),Path('analysis/bundle-swift-20261102'),Path('captures/firmware/bundle-commands-001'),Path('runtime/build/bundle-commands-001')]:files.update(p for p in base.rglob('*') if p.is_file())
files.update(Path(p) for p in ['README.md','swift/MemoMindKit/README.md','tests/g2_compat/COMMAND_PARITY.md','analysis/parity-status.json','analysis/storage-integration-plan.json',regpath,'analysis/regression-20261102-02/source-sha256-final.json','tests/run_tests.py'])
manifest=Path('analysis/evidence/bundle-hardware-20261102.json');assert not manifest.exists()
save(manifest,{'format':'memomind-evidence-supplement-v1','utc':now,'scope':'Mode8 implementation/reviews/tests, native Swift encoder/filter/catalog, Mac OTA/boot, finalcache and orderednotifications, visible bundled drawing and clear.','previous_supplement_preserved':pin('analysis/evidence/rect-copy-hardware-20261102.json'),'capture_pins_verified':True,'files':[pin(p) for p in sorted(files)]})
assert all(pin(f['path'])==f for f in read(manifest)['files'])
print(json.dumps({'report':str(root/'report.json'),'evidence':str(manifest),'pinned_files':len(files),'capture_manifests_verified':len(captures),'stages':stages,'python_tests':pycount,'swift_tests':swift}))
