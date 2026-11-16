"""Rokid Glasses (RG, Android 12): install the Glassly glasses app over adb and set the glasses up around it, or
put them back as they were.

Nothing is reflashed. The glasses run Android, so "installing Glassly" means installing one app
(tetramo-labs/glassly-rokid-cfw) and, on builds where that has been tried, making it the home screen and disabling the
Rokid components that fight it. Every run first records the state it may change; restore replays the first record
this computer took of these glasses before Glassly was installed.
"""
import json
import os
import time

from ... import paths
from ..base import FlashError
from . import adb as adb_link

PACKAGE = 'ai.glassly.rokid'
HOME_ACTIVITY = f'{PACKAGE}/.HomeActivity'
HOME_ROLE = 'android.app.role.HOME'
APK = 'rokid/glassly-rokid-0.1.0-dev.apk'
WAIT_SECONDS = 300
IDENTITY_PROPS = ('ro.product.manufacturer', 'ro.product.brand', 'ro.product.model', 'ro.product.device',
                  'ro.build.fingerprint', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.serialno',
                  'persist.vendor.adb')
PROBE = {
    'packages-system': 'pm list packages -s -f',
    'packages-user': 'pm list packages -3 -f',
    'packages-disabled': 'pm list packages -d',
    'home-role': f'cmd role get-role-holders {HOME_ROLE}',
    'home-candidates': 'cmd package query-activities --brief -a android.intent.action.MAIN '
                       '-c android.intent.category.HOME',
    'activities': 'dumpsys activity activities',
    'bluetooth': 'dumpsys bluetooth_manager',
    'input': 'dumpsys input',
    'display': 'dumpsys display',
    'power': 'dumpsys power',
    'deviceidle': 'dumpsys deviceidle whitelist',
    'accessibility': 'dumpsys accessibility',
    'camera': 'dumpsys media.camera',
    'audio': 'dumpsys audio',
    'getevent': 'getevent -lp',
    'props': 'getprop',
}
# Build fingerprints on which installing this exact APK has been tried on the developer's glasses.
INSTALL_VERIFIED = frozenset()
# Build fingerprint -> the launcher takeover tried on the developer's glasses for that build: the Rokid packages to
# disable before Glassly takes the home role. Empty until phase 3 of the launcher route has run on hardware.
TAKEOVER_VERIFIED = {}
DEVELOPER = os.environ.get('GLASSLY_FLASHER_DEVELOPER') == '1'


def stock_record_path(serial):
    return paths.backups_dir().parent / 'rokid' / f'{serial}-before-glassly.json'


class Session:
    def __init__(self, link, output, reporter):
        self.adb = link
        self.output = output
        self.reporter = reporter

    def save(self, name, document):
        (self.output / name).write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')

    def connect(self, pairing_code=None):
        self.reporter.log(f'Using {self.adb.path}: {" ".join(self.adb.version())}')
        if pairing_code:
            self.pair_wireless(pairing_code)
        self.reporter.status('Waiting for the glasses over adb')
        deadline = time.monotonic() + WAIT_SECONDS
        said = set()
        while True:
            rows = self.adb.devices()
            ready = [serial for serial, state, _ in rows if state == 'device']
            for serial, state, _ in rows:
                if state == 'unauthorized' and serial not in said:
                    said.add(serial)
                    self.reporter.status('Allow USB debugging on the glasses: accept the prompt they show')
                    self.reporter.log(f'{serial} is waiting for this computer to be allowed.')
            rokid = [serial for serial in ready if self.is_rokid(serial)]
            if len(rokid) > 1:
                raise FlashError(f'More than one pair of Rokid glasses is connected ({", ".join(rokid)}). Connect '
                                 'only the pair you are setting up.')
            if rokid:
                self.adb.serial = rokid[0]
                return
            others = [serial for serial in ready if serial not in said]
            for serial in others:
                said.add(serial)
                self.reporter.log(f'{serial} is connected but is not a pair of Rokid glasses; it is left alone.')
            if time.monotonic() > deadline:
                raise FlashError('No Rokid glasses appeared over adb. Turn on USB debugging for them in the Hi Rokid '
                                 'app, connect them with a data cable or pair them over Wireless debugging, and try '
                                 'again.')
            self.reporter.check_cancel()
            time.sleep(2)

    def pair_wireless(self, code):
        self.reporter.status('Looking for the glasses\' Wireless debugging pairing service')
        deadline = time.monotonic() + 60
        while not (services := self.adb.mdns('_adb-tls-pairing._tcp')):
            if time.monotonic() > deadline:
                raise FlashError('The glasses\' pairing service did not show up. On the glasses, open Wireless '
                                 'debugging, choose Pair device with pairing code, and keep that screen open.')
            self.reporter.check_cancel()
            time.sleep(2)
        self.reporter.log(f'Pairing with {services[0]}.')
        self.adb.pair(services[0], code)
        for address in self.adb.mdns('_adb-tls-connect._tcp'):
            try:
                self.adb.connect(address)
                self.reporter.log(f'Connected to {address}.')
            except FlashError as e:
                self.reporter.log(str(e))

    def is_rokid(self, serial):
        previous, self.adb.serial = self.adb.serial, serial
        try:
            brand = (self.adb.getprop('ro.product.brand') + ' ' + self.adb.getprop('ro.product.manufacturer')).lower()
        except FlashError:
            return False
        finally:
            self.adb.serial = previous
        return 'rokid' in brand

    def identity(self):
        props = {name: self.adb.getprop(name) for name in IDENTITY_PROPS}
        if not props['ro.serialno']:
            props['ro.serialno'] = self.adb.serial
        self.reporter.log('Glasses report: ' + ', '.join(f'{name}={props[name] or "-"}' for name in IDENTITY_PROPS[:7]))
        return props

    def snapshot(self, props):
        installed = self.adb.shell(f'pm list packages {PACKAGE}', check=False).strip()
        return {
            'taken': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'props': props,
            'glassly_installed': f'package:{PACKAGE}' in installed.split(),
            'home_holders': [line.strip() for line in self.adb.shell(f'cmd role get-role-holders {HOME_ROLE}',
                                                                      check=False).splitlines() if line.strip()],
            'disabled_packages': sorted(line.split(':', 1)[1].strip() for line in self.adb.shell(
                'pm list packages -d', check=False).splitlines() if line.startswith('package:')),
        }

    def probe(self):
        folder = self.output / 'probe'
        folder.mkdir(exist_ok=True)
        for name, command in PROBE.items():
            self.reporter.check_cancel()
            (folder / f'{name}.txt').write_text(f'$ {command}\n' + self.adb.shell(command, timeout=120, check=False))
        self.reporter.log(f'Read-only probe written to {folder}.')

    def record_stock(self, snapshot):
        path = stock_record_path(snapshot['props']['ro.serialno'])
        if path.exists() or snapshot['glassly_installed']:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + '\n')
        self.reporter.log(f'First record of these glasses before Glassly kept at {path}.')
        return path

    def install(self, props):
        fingerprint = props['ro.build.fingerprint']
        if fingerprint not in INSTALL_VERIFIED and not DEVELOPER:
            raise FlashError(f'Glassly has not been installed on Rokid build {fingerprint} by the developers yet, so '
                             'this flasher will not install it. Nothing was written. Send the backup folder so this '
                             'build can be tried.')
        if fingerprint not in INSTALL_VERIFIED:
            self.reporter.log('GLASSLY_FLASHER_DEVELOPER=1: installing on a build that is not on the verified list.')
        if props['persist.vendor.adb'] == 'false':
            self.reporter.log('Debugging is locked (persist.vendor.adb=false); unlocking it so restore stays possible.')
            self.adb.shell('setprop persist.vendor.adb true')
        apk = self.output / APK.split('/')[-1]
        apk.write_bytes(paths.firmware(APK))
        self.reporter.status('Installing Glassly on the glasses')
        output = self.adb.run('install', '-r', '-g', str(apk), timeout=180)
        if 'Success' not in output:
            raise FlashError(f'The glasses refused the app: {output.strip()}')
        self.adb.shell(f'dumpsys deviceidle whitelist +{PACKAGE}', check=False)
        plan = TAKEOVER_VERIFIED.get(fingerprint)
        if plan is None:
            self.reporter.log('This build has no verified launcher takeover yet: Glassly is installed as an app and '
                              'the Rokid launcher stays the home screen.')
            took_over = False
        else:
            self.take_over(plan)
            took_over = True
        self.adb.shell(f'am start -n {HOME_ACTIVITY}', check=False)
        return took_over

    def take_over(self, plan):
        self.reporter.status('Making Glassly the home screen')
        for package in plan['disable']:
            self.reporter.log(f'Disabling {package}.')
            self.adb.shell(f'pm disable-user --user 0 {package}')
        self.adb.shell(f'cmd role add-role-holder {HOME_ROLE} {PACKAGE}')
        holders = self.adb.shell(f'cmd role get-role-holders {HOME_ROLE}', check=False).split()
        if PACKAGE not in holders:
            raise FlashError(f'The glasses did not make Glassly the home screen (holders: {holders or "none"}). Run '
                             'Restore to put them back.')

    def restore(self, props, current):
        record_path = stock_record_path(props['ro.serialno'])
        stock = json.loads(record_path.read_text()) if record_path.exists() else None
        if stock is None:
            self.reporter.log(f'No record of these glasses before Glassly on this computer ({record_path}); removing '
                              'Glassly and handing the home screen back to the system default.')
        self.adb.shell(f'cmd role remove-role-holder {HOME_ROLE} {PACKAGE}', check=False)
        if stock:
            for holder in stock['home_holders']:
                if holder != PACKAGE:
                    self.adb.shell(f'cmd role add-role-holder {HOME_ROLE} {holder}', check=False)
            reenable = sorted(set(current['disabled_packages']) - set(stock['disabled_packages']))
            for package in reenable:
                self.reporter.log(f'Enabling {package} again.')
                self.adb.shell(f'pm enable {package}', check=False)
        if current['glassly_installed']:
            self.reporter.status('Removing Glassly from the glasses')
            output = self.adb.run('uninstall', PACKAGE, timeout=120, check=False)
            if 'Success' not in output:
                raise FlashError(f'The glasses did not remove Glassly: {output.strip()}')
        else:
            self.reporter.log('Glassly is not installed on these glasses.')


def run(mode, output, reporter, pairing_code=None):
    reporter.check_cancel()
    session = Session(adb_link.Adb(adb_link.find()), output, reporter)
    session.connect(pairing_code)
    props = session.identity()
    before = session.snapshot(props)
    session.save('snapshot-before.json', before)
    session.probe()
    reporter.check_cancel()
    if mode == 'backup':
        session.record_stock(before)
        reporter.log('Nothing was written.')
        return {'serial': props['ro.serialno'], 'fingerprint': props['ro.build.fingerprint'],
                'glassly_installed': before['glassly_installed']}
    if mode == 'install':
        session.record_stock(before)
        took_over = session.install(props)
        session.save('snapshot-after.json', session.snapshot(session.identity()))
        return {'serial': props['ro.serialno'], 'fingerprint': props['ro.build.fingerprint'], 'home': took_over}
    if mode == 'restore':
        session.restore(props, before)
        session.save('snapshot-after.json', session.snapshot(session.identity()))
        return {'serial': props['ro.serialno'], 'fingerprint': props['ro.build.fingerprint']}
    raise FlashError(f'Rokid Glasses do not support {mode}')
