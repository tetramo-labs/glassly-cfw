"""Seal verified OTA/boot/smoke evidence after the user's visual confirmation."""
if not __debug__: raise RuntimeError('Assertions required')
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'analysis/diagnostics-native-20261102'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p): return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,value):
    with p.open('x') as f:f.write(json.dumps(value,indent=2)+'\n')

pins=read(BASE/'candidate-pins.json');ota=read(BASE/'trace-verification.json')
boot=read(BASE/'preflight-verification.json');smoke=read(BASE/'smoke-verification.json')
visual=read(BASE/'visual-confirmation.json');offline=read(BASE/'offline-checkpoint.json')
assert ota['entire_ota_reconstructed'] and ota['reconstructed_sha256']==pins['image_sha256']
assert boot['complete'] and boot['app_header_full256_matches'] and boot['topology_and_badmap_match_backup']
assert smoke['complete'] and visual['confirmed'] is True
assert offline['all_required_offline_suites_passed']
assert sha(ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin')==pins['image_sha256']
assert sha(ROOT/'runtime/build/diagnostic-commands-001/graphics.bin')==pins['runtime_sha256']
current=read(ROOT/'analysis/regression-20261102-05/source-sha256-final.json')
assert all(sha(ROOT/n)==h for n,h in current.items())

# Canonical status documents have advanced since the offline checkpoint.
# Keep the original bytes available at explicit archived paths.
archives={
 'README.md':BASE/'README-at-offline-checkpoint.txt',
 'analysis/parity-status.json':BASE/'parity-status-at-offline-checkpoint.json',
 'analysis/storage-integration-plan.json':BASE/'storage-plan-at-offline-checkpoint.json',
 'tests/g2_compat/COMMAND_PARITY.md':BASE/'COMMAND_PARITY-at-offline-checkpoint.txt',
}
archive=archives['tests/g2_compat/COMMAND_PARITY.md']
with archive.open('xb') as f:f.write((ROOT/'tests/g2_compat/COMMAND_PARITY.md').read_bytes())
old_manifest=read(ROOT/'analysis/evidence/diagnostics-offline-20261102.json')
for row in old_manifest['files']:
    assert sha(archives.get(row['path'],ROOT/row['path']))==row['sha256'],row['path']

captures=[ROOT/'captures'/n for n in (
 'swift-mac-diagnostics-flash-20261102-01',
 'swift-mac-diagnostics-preflight-20261102-01',
 'swift-mac-diagnostics-smoke-20261102-01',
 'swift-mac-diagnostics-cleanup-20261102-01',
 'swift-mac-diagnostics-smoke-20261102-02')]
for folder in captures:
    files=[pin(p) for p in sorted(folder.rglob('*')) if p.is_file()]
    save(folder/'capture-manifest.json',{'format':'memomind-native-mac-capture-manifest-v1','files':files})
now=datetime.now(timezone.utc).isoformat()
report={
 'format':'memomind-native-diagnostics-hardware-v1','utc':now,
 'installed':True,'boot_verified':True,'current_installed_release':'diagnostic-commands-001',
 'candidate':pins,'added_command_mode':7,'extended_cleanup_mode':11,
 'transfer_verification':str((BASE/'trace-verification.json').relative_to(ROOT)),
 'preflight_verification':str((BASE/'preflight-verification.json').relative_to(ROOT)),
 'smoke_verification':str((BASE/'smoke-verification.json').relative_to(ROOT)),
 'visual_confirmation':str((BASE/'visual-confirmation.json').relative_to(ROOT)),
 'visual_confirmed':True,'cleared':True,'input_observer_inactive':True,
 'capture_manifests':[str((p/'capture-manifest.json').relative_to(ROOT)) for p in captures],
 'offline_checkpoint':str((BASE/'offline-checkpoint.json').relative_to(ROOT)),
 'required_stages':117,'python_tests':224,'swift_tests':100,
 'regression_execution_scope':offline['regression_execution_scope'],
 'trace_verifier_synthetic_cases':42,'canary_repeated':False,
 'first_smoke_attempt':'Stopped before pattern on incorrect helper initial-epoch assumption; preserved as incomplete. Cleanup acknowledged. V2 accepts native clock seeding and retains relative epoch checks.',
 'initial_epoch_evidence':'analysis/diagnostics-initial-epoch-20261102/report.json',
 'full_command_parity':False,'full_g2_parity':False,
 'remaining_required_suite_entries':offline['remaining_required_suite_entries'],
 'parity_scope':offline['parity_scope'],
 'limitations':read(ROOT/'analysis/diagnostic-commands-001/report.json')['limitations']+[
  'Application TX/RX traces, not independent HCI/radio capture.',
  'User visibility confirmation is not hardware pixel readback or measured refresh/performance equivalence.',
  'Physical single-button event acceptance and compass/raw IMU/ALS adapters remain unfinished.',
  'Header match verifies boot identity, not a full application flash readback.',
 ],
}
save(BASE/'report.json',report)
for name in ('analysis/parity-status.json','analysis/storage-integration-plan.json'):
    p=ROOT/name;d=read(p)
    d['diagnostic_candidate'].update(hardware_smoke_verified=True,visible_output_confirmed=True,
        hardware_state='Installed and boot verified; frame/control/cleanup checks passed; DIAG and overlay visually confirmed; cleared',
        hardware_report=str((BASE/'report.json').relative_to(ROOT)))
    if 'verified' in d:d['verified'].append('Mode7 diagnostics and extended mode11 cleanup installed/boot verified: frame skip/reorder/duplicate/resync, worker refusal counter, button-observer stop and cache-epoch chain checked live; DIAG plus overlay confirmed visible; cleanup acknowledged.')
    d['updated_utc']=now;p.write_text(json.dumps(d,indent=2)+'\n')
p=ROOT/'README.md';s=p.read_text().replace('[diagnostics boot checkpoint](analysis/diagnostics-native-20261102/boot-checkpoint.json)','[diagnostics hardware evidence](analysis/diagnostics-native-20261102/report.json)')
s=s.replace('Offline regression is complete; the diagnostics smoke and visual acceptance are pending.','Offline regression and live diagnostics/cleanup checks passed; the user confirmed\nDIAG and the separate overlay, then cleanup was acknowledged.')
p.write_text(s)
p=ROOT/'tests/g2_compat/COMMAND_PARITY.md';s=p.read_text().replace('with offline validation only so far','now boot verified and exercised live')
s=s.replace('Implemented in the offline `--diagnostic-commands` candidate:', 'Implemented in the installed `--diagnostic-commands` release:')
s=s.replace('Hardware acceptance pending.|','Native Swift checks passed; DIAG/overlay visibility confirmed and cleanup acknowledged.|')
s=s.replace('the offline diagnostics candidate accepts11/8b','the installed diagnostics release accepts11/8b')
s=s.replace('hardware acceptance is pending. Its separate overlay leaves raster copying and','the live state/cleanup checks and user visibility confirmation pass. Its separate overlay leaves raster copying and')
p.write_text(s)
files={ROOT/n for n in current}
for folder in [BASE,ROOT/'analysis/diagnostic-commands-001',ROOT/'analysis/diagnostics-initial-epoch-20261102',*captures]:
    files.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
files.update(ROOT/n for n in archives)
files.update({ROOT/'analysis/evidence/diagnostics-offline-20261102.json',ROOT/'tests/g2_compat/README.md'})
save(ROOT/'analysis/evidence/diagnostics-hardware-20261102.json',{
 'format':'memomind-evidence-supplement-v1','utc':now,
 'scope':'Native diagnostics OTA/boot/state/cleanup, user-confirmed overlay and preserved failed first helper attempt',
 'offline_checkpoint':pin(ROOT/'analysis/evidence/diagnostics-offline-20261102.json'),
 'offline_canonical_archives':{name:pin(path) for name,path in archives.items()},
 'files':[pin(p) for p in sorted(files)]})
print(json.dumps({'hardware_report':str(BASE/'report.json'),'pinned_files':len(files),'captures':len(captures)}))
