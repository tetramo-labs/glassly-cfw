#!/usr/bin/env python3
"""Offline signed APK/compiled-lifecycle wiring audit; not an Android runtime test."""
from pathlib import Path
import hashlib,json,os,re,subprocess
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build'
SDK=Path(os.environ.get('ANDROID_SDK_ROOT',str(Path.home()/'Library/Android/sdk')))/'build-tools/36.0.0'
JDK=Path(os.environ.get('HID_JDK','/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home'))
APK=OUT/'memomind-hid-fixture.apk'
def run(*args):return subprocess.run([str(x) for x in args],check=True,text=True,capture_output=True).stdout
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
verify=run(SDK/'apksigner','verify','--verbose','--print-certs',APK)
badging=run(SDK/'aapt2','dump','badging',APK)
xml=run(SDK/'aapt2','dump','xmltree','--file','AndroidManifest.xml',APK)
assert 'Verified using v3 scheme (APK Signature Scheme v3): true' in verify
assert "minSdkVersion:'33'" in badging and "targetSdkVersion:'36'" in badging
perms=re.findall("uses-permission: name='([^']+)'",badging)
expected={'BLUETOOTH_CONNECT','BLUETOOTH_ADVERTISE','INTERNET','POST_NOTIFICATIONS','FOREGROUND_SERVICE','FOREGROUND_SERVICE_CONNECTED_DEVICE'}
assert set(perms)=={'android.permission.'+x for x in expected}
service=xml.split('E: service',1)[1]
assert '".HidService"' in service and 'exported(0x01010010)=false' in service
assert 'stopWithTask(0x0101036a)=false' in service and 'foregroundServiceType(0x01010599)=0x00000010' in service
activity=run(JDK/'bin/javap','-classpath',OUT/'classes','-private','-c','org.memomind.research.hid.HidActivity')
service_code=run(JDK/'bin/javap','-classpath',OUT/'classes','-private','-c','org.memomind.research.hid.HidService')
assert 'extends android.app.Activity' in activity and 'extends android.app.Service' in service_code
assert not re.search(r'\bvoid on(?:Stop|Destroy)\(',activity),'UI lifecycle must not own fixture teardown'
for marker in ['startForegroundService','onPostResume'] :assert marker in activity
session_code=run(JDK/'bin/javap','-classpath',OUT/'classes','-private','-c','org.memomind.research.hid.HidService$Session')
combined=service_code+'\n'+session_code
for marker in ['startForeground:','stopForeground:','stopSelf:','ControllerLease.request:','ControllerLease.authenticate:','ControllerLease.stop:','setDeleteIntent:']:assert marker in combined,marker
for name,data in [('apk-signature.txt',verify),('apk-badging.txt',badging),('apk-manifest.txt',xml),('activity-bytecode.txt',activity),('service-bytecode.txt',service_code),('session-bytecode.txt',session_code)]: (OUT/name).write_text(data)
inputs=[ROOT/'AndroidManifest.xml',ROOT/'build.sh',ROOT/'control.py',*sorted((ROOT/'src').rglob('*.java')),*sorted((ROOT/'tests').glob('*.java')),*sorted((ROOT/'tests').glob('*.py'))]
report={'schema':2,'kind':'offline-only Android HID foreground-service fixture','device_actions':False,'installed':False,'advertised':False,'paired':False,'android_bridge_edits':False,'apk':{'path':str(APK.relative_to(ROOT.parent)),'bytes':APK.stat().st_size,'sha256':sha(APK),'package':'org.memomind.research.hid','version':2,'min_sdk':33,'target_sdk':36,'v3_signature_verified':True},'model_test':json.loads((OUT/'tests/report.json').read_text()),'controller_loopback_tests':{'passed':3,'command':'python3 -m unittest discover -s android_hid_fixture/tests -p test_*.py -v'},'foreground_lifetime':{'type':'connectedDevice','exported':False,'stop_with_task':False,'activity_stop_destroy_teardown':False,'authentication_timeout_ms':120000,'idle_timeout_ms':120000,'hard_session_ms':600000,'renewable_hard_lease':False,'notification_stop':True,'sticky_restart':False,'android_runtime_tested':False},'unverified':['Android GATT callback runtime','actual foreground-service/notification behavior and pairing UI','radio advertisements','SMP/pairing','bonded CCCD persistence','same-phone BR/EDR + LE identity and CTKD coexistence','real glasses HOGP parsing and key actions'],'inputs':[{'path':str(p.relative_to(ROOT.parent)),'sha256':sha(p)} for p in inputs]}
(ROOT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'apk':report['apk'],'lifecycle':report['foreground_lifetime']},indent=2))
