from pathlib import Path
import hashlib,json,datetime
root=Path.cwd(); area=Path('analysis/native-mac-hardware-20261101')
def item(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
captures=[]
for name in ['pairing-20261101-01','probe-20261101-03','probe-20261101-04','probe-20261101-05','probe-20261101-06','check-20261101-01','flash-20261101-01','boot-20261101-01']:
 d=Path('captures')/('swift-mac-'+name); manifest=d/'capture-manifest.json'
 files=[item(p) for p in sorted(d.rglob('*')) if p.is_file() and p!=manifest]
 if manifest.exists():
  old=json.loads(manifest.read_text());assert old['files']==files, f'Sealed capture changed: {d}'
 else:write(manifest,{'format':'memomind-native-mac-capture-manifest-v1','files':files})
 captures.append(item(manifest))
report={
 'format':'memomind-native-mac-hardware-v1', 'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'state':'paired; full native OTA transfer and reboot ACK verified; post-reboot connection timed out',
 'device_address':'4C:3C:8F:90:CC:C3',
 'user_factory_reset_reported':True,
 'pairing':{'native_api':'IOBluetoothDevicePair','success':True,'confirmation_or_pin_requested':False,'capture':'captures/swift-mac-pairing-20261101-01','raw_hci_capture':False},
 'transport_change':{'cached_sdp_before_fresh_query':True,'uuid_matched_channel':True,'hardcoded_channel':False,'fresh_query_timeout_fallback':False,'observed':'Fresh SDP completion did not arrive on this Mac after pairing. Cached service record resolved channel 5 and RFCOMM opened successfully.'},
 'probe':'captures/swift-mac-probe-20261101-06/result.json',
 'check':'captures/swift-mac-check-20261101-01/result.json',
 'flash':'captures/swift-mac-flash-20261101-01/result.json',
 'independent_application_trace_verification':'analysis/native-mac-hardware-20261101/trace-verification.json',
 'image':item(Path('captures/firmware/exclusive-store-reader-001/firmware.bin')),
 'full_transfer_verified':True,'blocks':543,'chunks':3800,'reboot_acknowledged':True,
 'post_reboot_verified':False,
 'post_reboot_attempt':{'capture':'captures/swift-mac-boot-20261101-01','failure':'RFCOMM open timed out','application_frames_sent':False},
 'tests':{'swift_passed':32,'offline_transport_passed':23,'release_build_passed':True,'prior_aggregate':'analysis/regression-20261101-05/report.json','prior_aggregate_predates_transport_change':True},
 'full_managed_store_backup':{'verification':'analysis/exclusive-store-backup-verification.json','bytes':3145728,'predates_user_factory_reset':True,'current_post_reset_storage_snapshot':False},
 'firmware_canary_installed':False,'full_g2_parity':False,
 'limitations':['Application TX/RX trace, not an independent HCI/radio observation.','Reboot acknowledgment does not establish successful boot.','The retained full backup predates the user factory reset; fresh topology and storage preflight is needed before canary writes.','Swift firmware construction and mobile transport integration remain separate work.'],
 'capture_manifests':captures,
 'source_and_binary_pins':[item(p) for p in sorted(Path('swift/MemoMindKit/Sources').rglob('*')) if p.is_file()]+[item(Path('swift/MemoMindKit/Package.swift')),item(Path('swift/MemoMindKit/.build/release/memomind'))],
 'verification_pins':[item(area/p) for p in ['verify-trace.py','trace-verification.json','verify-reader.swift','verify-reader','swift-tests.stdout','swift-tests.stderr','build.stdout','build.stderr','transport-offline/run-001/stdout.txt']]
}
write(area/'report.json',report)
p=Path('analysis/parity-status.json');v=json.loads(p.read_text());s=v['native_swift_port'];s.update({'hardware_report':str(area/'report.json'),'mac_paired':True,'direct_mac_transfer_verified':True,'direct_mac_hardware_ota_verified':False,'post_reboot_verified':False,'hardware_blocker':'Native OTA completed and reboot acknowledged; first post-reboot RFCOMM open timed out. Awaiting awake glasses for read-only boot verification.'})
v['exclusive_reader_candidate']['latest_mac_transfer_report']=str(area/'report.json')
v['exclusive_reader_candidate']['backup_predates_user_factory_reset']=True
v['exclusive_reader_candidate']['latest_mac_post_reboot_verified']=False
write(p,v)
print(json.dumps({'report':str(area/'report.json'),'capture_manifests':len(captures),'full_transfer_verified':True,'post_reboot_verified':False}))
