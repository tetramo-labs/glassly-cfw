from pathlib import Path
import datetime,json,hashlib,sys
r=Path('analysis/reset-undo-trim-20261102')
def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):
 with Path(p).open('x') as f:json.dump(d,f,indent=2);f.write('\n')
boot=len(sys.argv)==2 and sys.argv[1]=='boot'
t=load(r/'transfer-verification.json');assert t['passed']
o=load(r/'offline-checkpoint.json');b=load(r/'baseline-verification.json')
report={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'release':'reset-undo-trim-001','image_sha256':o['image_sha256'],'runtime_sha256':o['runtime_sha256'],'runtime_build':o['runtime_build'],'runtime_bytes':60256,'ota_verified_bytes':2226404,'blocks':544,'chunks':3805,'boot_verified':boot,'state':'Boot verified; matched RAM RESET/PUT sequence and cleanup verified' if boot else 'Complete OTA verified and reboot acknowledged; Bluetooth unavailable for boot/header and matched RAM verification','ota_capture':'captures/swift-mac-reset-undo-flash-20261102-01','transfer_verification':str(r/'transfer-verification.json'),'offline_checkpoint':str(r/'offline-checkpoint.json'),'baseline_verification':str(r/'baseline-verification.json'),'hardware_saving_measured':False,'native_rv32_requested_bytes_released':46756,'full_parity':False,'tests':{'python':235,'swift':107,'original_scene_assertion_sites':424,'new_native_calls':85,'retained_native_calls':3167,'native_gate_cases':7955,'full_aggregate_rerun':False},'limitations':o['limits']}
if boot:
 a=load(r/'after-verification.json');assert a['passed'] and a['release']=='reset-undo-trim-001'
 report.update(after_verification=str(r/'after-verification.json'),after_capture=a['capture'],app_header_sha256=a['app_header_sha256'],hardware_saving_measured=True,cleanup_verified=a['cleanup_verified'],matched_measurements={'before':b['phases'],'after':a['phases'],'before_reset_minus_put_median_bytes':b['reset_minus_put_median_bytes'],'after_reset_minus_put_median_bytes':a['reset_minus_put_median_bytes'],'after_reset_minus_reacquired_median_bytes':a['reset_minus_reacquired_median_bytes'],'difference_of_reset_deltas_bytes':a['reset_minus_put_median_bytes']-b['reset_minus_put_median_bytes']},after_cleanup_free_bytes=a['after_cleanup_free_bytes'])
name='hardware-result.json' if boot else 'transfer-checkpoint.json';save(r/name,report)
archives={}
for file in ['README.md','analysis/parity-status.json','analysis/storage-integration-plan.json']:
 p=Path(file);dest=r/(p.name+('.before-boot.txt' if boot else '.before-transfer.txt'))
 with dest.open('xb') as f:f.write(p.read_bytes())
 archives[file]=str(dest)
for file in ['analysis/parity-status.json','analysis/storage-integration-plan.json']:
 p=Path(file);d=load(p)
 candidate=dict(state=report['state'],release=report['release'],image_sha256=report['image_sha256'],runtime_build=o['runtime_build'],runtime_bytes=60256,installed=True if boot else None,currently_installed=boot,boot_verified=boot,ota_transfer_verified=True,firmware_bytes_sent=2226404,report=str(r/name),offline_checkpoint=str(r/'offline-checkpoint.json'),native_requested_bytes_released=46756,hardware_saving_measured=boot,policy=o['native_policy'],tests=report['tests'])
 if boot:
  candidate['matched_measurements']=report['matched_measurements']
  d.pop('device_pending_boot_verification',None)
  d.update(current_device_image_sha256=o['image_sha256'],current_device_runtime_sha256=o['runtime_sha256'],current_device_release='reset-undo-trim-001',current_device_build=o['runtime_build'],current_device_ota='captures/firmware/reset-undo-trim-001/firmware.bin')
  d['dashboard_ram_candidate']['currently_installed']=False
  d['dashboard_ram_candidate']['superseded_by']='reset-undo-trim-001; dashboard gates retained'
 else:d['device_pending_boot_verification']=dict(release=report['release'],image_sha256=o['image_sha256'],last_boot_verified_release='dashboard-ram-002')
 d['reset_undo_trim_candidate']=candidate
 d['dashboard_ram_candidate']['additional_candidate'].update(implemented=True,report=str(r/name),requires='Hardware check complete' if boot else 'Post-reboot header and matched RAM check',policy='Mandatory undo before native mutation; default upstream fallback/retention unchanged')
 p.write_text(json.dumps(d,indent=2)+'\n')
p=Path('README.md');text=p.read_text();needle='A separate reviewed **96 KiB RX profile**'
if 'The `reset-undo-trim-001` release' in text:
 start=text.index('The `reset-undo-trim-001` release');end=text.index(needle,start);text=text[:start]+text[end:]
if boot:
 gain=report['matched_measurements']['after_reset_minus_put_median_bytes'];return_gain=report['matched_measurements']['after_reset_minus_reacquired_median_bytes']
 paragraph=f'''The `reset-undo-trim-001` release is installed and boot verified. A successful
standalone RESET now releases undo scratch while retaining scene metadata, asset
storage, vector workspace and pixels. In matched on-device measurements, RESET
increased free RAM by **{gain:,.0f} bytes** (median); the following PUT consumed
about {return_gain:,.0f} bytes again. The previous release changed by only 56 bytes.
This improves idle memory after RESET, without reducing peak transaction RAM.
Bundles retain scratch; failed native reacquisition rejects CAPACITY before cache
mutation. The default portable G2 behavior and original assertions remain unchanged.
The runtime is 60,256 bytes within the existing 64 KiB code allocation. All 235
Python and 107 Swift tests passed, alongside native and sanitizer scene regressions.
See the [RESET scratch hardware result](analysis/reset-undo-trim-20261102/hardware-result.json).

'''
 text=text.replace('The installed `dashboard-ram-002` release suppresses','The earlier `dashboard-ram-002` release suppresses')
else:
 paragraph='''The `reset-undo-trim-001` release has completed OTA transfer and acknowledged
reboot; boot/header and matched RAM verification await Bluetooth reconnection.
Its native opt-in policy releases undo scratch after a standalone RESET and
requires rollback storage before a later mutation. Bundles retain scratch;
default G2 assertions and behavior remain unchanged. Native RV32 tests release
46,756 requested bytes for a small transaction. Hardware savings are still pending.
The 60,256-byte runtime fits the existing 64 KiB code allocation; 235 Python and
107 Swift tests passed. See the [transfer checkpoint](analysis/reset-undo-trim-20261102/transfer-checkpoint.json).

'''
assert text.count(needle)==1;text=text.replace(needle,paragraph+needle);p.write_text(text)
files=set()
for base in [r,Path('captures/swift-mac-reset-undo-flash-20261102-01')]:files.update(p for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for base in Path('captures').glob('swift-mac-reset-undo-after-20261102-*'):files.update(p for p in base.rglob('*') if p.is_file())
files.update(Path(p) for p in archives)
save(r/('hardware-evidence.json' if boot else 'transfer-evidence.json'),dict(count=len(files),historical_canonical_snapshots=archives,sha256={str(p):sha(p) for p in sorted(files)}))
print(json.dumps({k:report[k] for k in ('state','boot_verified','hardware_saving_measured')}))
