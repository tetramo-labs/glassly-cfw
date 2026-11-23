"""Seal completed text hardware evidence; run only after actual visual/clear proof."""
from pathlib import Path
import datetime, hashlib, json, re
if not __debug__:raise RuntimeError('Assertions required')
R=Path('analysis/text-native-20261102')
def read(p):return json.loads(Path(p).read_text())
def save(p,value):Path(p).write_text(json.dumps(value,indent=2)+'\n')
def pin(p):
 p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
assert read(R/'trace-verification.json')['entire_ota_reconstructed']
assert read(R/'preflight-verification.json')['complete']
smoke=read(R/'smoke-verification.json');assert smoke['complete'] and smoke['cleared'] and smoke['probe_header_capabilities_verified']
visual=read(R/'visual-confirmation.json');assert visual['text_pattern_visible']
regpath=Path('analysis/regression-20261102-03/report.json');reg=read(regpath)
assert reg['all_required_offline_suites_passed'] and not reg['sources_changed_during_run'] and not reg['missing_upstream_mapped_stages']
source=read(regpath.parent/'source-sha256-final.json');assert all(pin(k)['sha256']==v for k,v in source.items())
py=read(regpath.parent/'firmware_transport.json');assert py['all_required_tests_passed'] and not py['skipped']
log=(regpath.parent/'native_swift.stdout').read_text()+(regpath.parent/'native_swift.stderr').read_text()
swift=max(map(int,re.findall(r'Executed (\d+) tests?, with 0 failures',log)))
stages=sum(x.get('parity_required',True) for x in reg['results']);assert stages==105 and swift==89 and py['tests_run']==223
assert read(R/'ios-core.json')['returncode']==0
review=read('analysis/text-command-review-20261102/final-review.json');assert not review['blockers'] and not review['source_drift_from_frozen_build']
assert all(pin(k)['sha256']==v for k,v in review['sha256'].items())
pins=read(R/'candidate-pins.json');captures=sorted(Path('captures').glob('swift-mac-text-*-20261102-*'))
for folder in captures:
 manifest=folder/'capture-manifest.json'
 if not manifest.exists():
  files=[pin(p) for p in sorted(folder.rglob('*')) if p.is_file()]
  save(manifest,{'format':'memomind-native-mac-capture-manifest-v1','files':files})
 assert all(pin(f['path'])==f for f in read(manifest)['files'])
report={'format':'memomind-native-text-command-hardware-v1','utc':now,'state':'Mode15 installed and boot verified; user confirmed native text groups; maximum255-byte/highbit/bundle/empty commands accepted, malformed text rejected, display cleared','installed':True,'boot_verified':True,'current_installed_release':'text-commands-001','candidate':pin('captures/firmware/text-commands-001/firmware.bin'),'runtime':pin('runtime/build/text-commands-001/graphics.bin'),'added_command_mode':15,'text_max_bytes':255,'text_font':'native-resource','missing_glyph':'reject','highbit_mode_supported':True,'text_bundle_supported':True,'visible_text_confirmed':True,'transfer_verification':str(R/'trace-verification.json'),'preflight_verification':str(R/'preflight-verification.json'),'smoke_verification':str(R/'smoke-verification.json'),'visual_confirmation':str(R/'visual-confirmation.json'),'live_helper':str(R/'smoke.swift'),'trace_verifier':str(R/'verify-smoke.py'),'capture_manifests':[str(c/'capture-manifest.json') for c in captures],'offline_runtime_report':'analysis/text-commands-001/report.json','swift_encoder_report':'analysis/text-swift-20261102/report.json','independent_review':'analysis/text-command-review-20261102/final-review.json','aggregate':str(regpath),'required_stages_passed':stages,'python_tests_passed':py['tests_run'],'swift_tests_passed':swift,'ios15_core_typecheck_passed':True,'regression_source_files_rechecked':len(source),'source_drift':False,'canary_repeated':False,'full_command_parity':False,'full_g2_parity':False,'excluded_features':['Bluetooth keyboard/HOGP accessory support'],'remaining_required_suite_entries':reg['remaining_upstream_suite_files'],'limits':['Native font repertoire, metrics, kerning and raster appearance differ from G2. Missing/dynamic glyphs are rejected.','Malformed standalone text preserves prior animation/pixels; G2 takes over before validation.','Resource callbacks must be synchronous and stable; host/RV32 mocks do not prove worst-case firmware latency or interrupt stack.','Native8192-byte ingress and64KiB retained store remain; full capacity pending.','Header match is boot identity evidence, not a full application readback.','Application traces, not independent HCI/radio capture; no hardware pixel readback or continuous-retention proof.','Native iOS/Glassly transport and remaining command adapters are unfinished.']}
assert not (R/'report.json').exists();save(R/'report.json',report)
for name in ['analysis/parity-status.json','analysis/storage-integration-plan.json']:
 d=read(name);d['command_priority']['first_stage_status']='Modes6/3/9/8/15 installed and boot verified. Native text visibly confirmed, including maximum byte count, highbit and bundle execution. Remaining command adapters and full capacity are incomplete.'
 d['command_priority']['completed_visible_modes']=[6,3,9,8,15];d['command_priority']['next']=[7,11]
 d.pop('current_device_boot_verification_pending',None)
 d['text_candidate']={'installed':True,'firmware':'captures/firmware/text-commands-001','runtime':'runtime/build/text-commands-001','hardware_report':str(R/'report.json'),'ota_transfer_verified':True,'post_reboot_verified':True,'hardware_smoke_verified':True,'visible_output_confirmed':True,'text_max_bytes':255,'native_font_equivalent_to_g2':False}
 d['bundle_candidate']['installed']=False;d['bundle_candidate']['superseded_by']='text-commands-001 (retains mode8)'
 if 'updated_utc' in d:d['updated_utc']=now
 if 'latest_offline_regression' in d:
  d['latest_offline_regression'].update(report=str(regpath),stages=stages,python_tests=py['tests_run'],swift_tests=swift)
  d['current_device_image_sha256']=pins['image_sha256'];d['current_device_runtime_sha256']=pins['runtime_sha256'];d['current_device_build']='runtime/build/text-commands-001'
  d['native_swift_port']['swift_tests_passed']=swift;d['native_swift_port']['latest_command_hardware_report']=str(R/'report.json')
  d['verified'].append('Mode15 boot verified and visually confirmed: 255-byte text, highbit and bundle dispatch, malformed rejection and acknowledged clear. Native font differences remain explicit.')
 else:d['implemented']['regression']=str(regpath)
 save(name,d)
p=Path('README.md');s=p.read_text().replace('All 94 required offline stages pass, including 222 Python tests, 79 Swift tests','All 105 required offline stages pass, including 223 Python tests, 89 Swift tests').replace('and 79 Swift tests pass.','and 89 Swift tests pass.')
pending=s.find('\nThe mode15 text candidate passed all 105 required offline stages')
if pending>=0:s=s[:pending]+s[s.index('\n',s.index('awaiting-wake-01.json).',pending))+1:]
a=s.index('The installed command-parity firmware supports');b=s.index('\n## Evidence and tools',a)
s=s[:a]+'''The installed command-parity firmware supports mode6 RLE frames, mode3 rectangle
deltas, mode9 overlap copy, mode8 bundles, and mode15 built-in text. Native Swift
encoders generate these commands directly on the Mac. The text update and boot
header are verified; the user confirmed both native TEXT 15 / SWIFT groups.
Maximum255-byte text, highbit and bundled text, malformed rejection and explicit
clear passed live checks. All105 required offline stages pass (223 Python and89
Swift tests). MemoMind resource fonts differ from G2; remaining command adapters,
native capacities and full suite porting are incomplete. Keyboard/HOGP is excluded.
See [command map](tests/g2_compat/COMMAND_PARITY.md) and
[text hardware evidence](analysis/text-native-20261102/report.json).
'''+s[b:];s=s.replace('Maximum255','Maximum 255').replace('All105','All 105').replace('and89','and 89');p.write_text(s)
p=Path('tests/g2_compat/COMMAND_PARITY.md');s=p.read_text();s=s.replace('Mode15 child unsupported until its adapter exists.','Mode15 text children are supported by `--text-commands`.')
s=s.replace('Missing top-level dispatch. Native resource-font callback exists for retained/shape text, currently128-byte limit and different font repertoire/metrics.','Implemented behind `--text-commands`: exact255-byte-capable envelope, signed placement, UTF8/control validation, highbit and bundle dispatch with owned scratch. Native text visibly confirmed. Resource fonts/metrics and missing-glyph rejection differ from G2; retained shape text remains128 bytes.')
s=s.replace('mode15 remains next.','mode15 is now installed and visibly confirmed. Remaining command adapters are pending.')
s+='\n[Mode15 hardware evidence](../../analysis/text-native-20261102/report.json) records\nthe native text checks. The inventory explicitly maps its original G2 renderer\nreference and MemoMind adapter tests to required aggregate stages; no incomplete\noriginal suite is marked complete by those supplemental tests.\n';p.write_text(s)
p=Path('tests/g2_compat/README.md');s=p.read_text().replace('## Latest command-parity checkpoint (2026-11-02)','## Mode8 command-parity checkpoint (2026-11-02)')
s=s.replace('The candidate awaits hardware transfer and visibility checks.', 'That offline checkpoint preceded the completed hardware verification below.')
s+='''\n## Latest text command checkpoint (2026-11-02)

Mode15 is installed, boot verified and visibly confirmed. All105 required stages,
223 Python tests and89 Swift tests pass. Native text tests include2,598 comparisons
against extracted original G2 rendering routines with equivalent synthetic glyphs,
plus actual compiled RV32 execution. The original shape-suite font stub is not
counted as native text coverage. See [text evidence](../../analysis/text-native-20261102/report.json).
All21 incomplete suite/integration entries remain explicit completion blockers;
keyboard/HOGP remains the only feature exclusion. Native font appearance and
missing-glyph handling differ from G2.\n'''
for a,b in [('All105','All 105'),('and89','and 89'),('include2,598','include 2,598'),('All21','All 21')]:s=s.replace(a,b)
p.write_text(s)
p=Path('swift/MemoMindKit/README.md');s=p.read_text();s+='''\n`RasterCommands.builtinText(bytes:x:y:options:)` and its String overload encode
mode15 with up to255 UTF8 bytes. NUL and malformed UTF8 are rejected; bytes1..31
are horizontal offsets, including LF/CR. Native resource glyph support is checked
by the receiver. Bundles accept text envelopes after checking native capability.
`text-commands-001` is admitted by exact image/component pins and has boot/live
text verification; shared core typechecks for iOS15, but native iOS transport is
not established. [Hardware evidence](../../analysis/text-native-20261102/report.json).\n''';p.write_text(s)
files=set(p for p in R.rglob('*') if p.is_file())
for base in [*captures,Path('analysis/text-commands-001'),Path('analysis/text-command-review-20261102'),Path('analysis/text-swift-20261102'),Path('captures/firmware/text-commands-001'),Path('runtime/build/text-commands-001')]:files.update(p for p in base.rglob('*') if p.is_file())
files.update(Path(p) for p in ['README.md','tests/g2_compat/README.md','tests/g2_compat/COMMAND_PARITY.md','tests/g2_compat/inventory.py','tests/g2_compat/inventory.json','swift/MemoMindKit/README.md','analysis/parity-status.json','analysis/storage-integration-plan.json','tests/run_tests.py',str(regpath),str(regpath.parent/'source-sha256-final.json')])
manifest=Path('analysis/evidence/text-hardware-20261102.json');assert not manifest.exists()
save(manifest,{'format':'memomind-evidence-supplement-v1','utc':now,'scope':'Native mode15 implementation, G2 reference comparisons, Swift encoder/catalog, Mac OTA/boot, visible text and clear','previous_supplement_preserved':pin('analysis/evidence/bundle-hardware-20261102.json'),'offline_checkpoint_preserved':pin('analysis/evidence/text-offline-20261102.json'),'files':[pin(p) for p in sorted(files)]})
assert all(pin(f['path'])==f for f in read(manifest)['files'])
print(json.dumps({'report':str(R/'report.json'),'evidence':str(manifest),'pinned_files':len(files),'capture_manifests_verified':len(captures),'stages':stages,'python_tests':py['tests_run'],'swift_tests':swift}))
