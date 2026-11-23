from pathlib import Path
import json,hashlib,datetime
area=Path('analysis/native-mac-canary-20261101')
def pin(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
for folder in [Path('captures/swift-mac-canary-flash-20261101-01'),Path('captures/swift-mac-canary-preflight-20261101-01')]:
 manifest=folder/'capture-manifest.json';assert not manifest.exists();write(manifest,{'format':'memomind-native-mac-capture-manifest-v1','files':[pin(p) for p in sorted(folder.iterdir()) if p.is_file()]})
r={'format':'memomind-native-mac-canary-hardware-v1','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'full OTA and reboot ACK verified; first post-reboot RFCOMM open timed out; awaiting awake device','firmware_sha256':'79a4158c5d82b97c248d0dd2b7e366df03206393c1c2a7275677b8985d81398a','firmware_bytes':2226788,'transfer_verified':True,'transfer_verification':str(area/'trace-verification.json'),'boot_verified':False,'canary_started':False,'canary_passed':False,'full_g2_parity':False,'current_backup':'analysis/native-mac-backup-20261101/verification.json','backup_bytes':3145728,'backup_matches_pre_reset':True,'regression':'analysis/regression-20261101-06/report.json','offline_stages_passed':66,'python_tests_passed':219,'swift_tests_passed':46,'regression_source_drift':[],'failed_boot_attempt':'captures/swift-mac-canary-preflight-20261101-01','failed_before_application_frames':True,'automatic_retries':0,'next_action':'Wake glasses; read-only exact header/profile/topology/badmap/target+neighbor validation before one fixed op2 request','source_snapshot':str(area/'source-snapshot/manifest.json'),'limitations':['Reboot ACK does not establish successful boot.','No canary write/erase request has been sent.','Native scene/flash ownership, full message ingress and complete G2 parity remain unfinished.']}
write(area/'pending-report.json',r)
p=Path('analysis/parity-status.json');v=json.loads(p.read_text());v['exclusive_reader_candidate'].update({'currently_installed':None,'last_boot_verified_before_canary_ota':True,'current_post_reset_backup':'analysis/native-mac-backup-20261101/verification.json'})
v['fixed_canary_candidate'].update({'installed':None,'ota_transfer_verified':True,'post_reboot_verified':False,'hardware_canary_executed':False,'hardware_report':str(area/'pending-report.json'),'native_swift_client_available':True})
v['native_swift_port'].update({'swift_tests_passed':46,'fixed_canary_client_available':True,'latest_canary_attempt':str(area/'pending-report.json')});write(p,v)
print(json.dumps(r,indent=2))
