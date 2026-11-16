import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from glassly_flasher.devices import rokid
from glassly_flasher.devices.base import FlashError
from glassly_flasher.devices.rokid import adb as adb_link

FINGERPRINT = 'Rokid/rv101/rv101:12/1.22.009/20260710:user/release-keys'


class FakeGlasses:
    def __init__(self, brand='Rokid', glassly=False, home='com.rokid.os.sprite.launcher', locked=False):
        self.props = {'ro.product.manufacturer': brand, 'ro.product.brand': brand, 'ro.product.model': 'RV101',
                      'ro.product.device': 'rv101', 'ro.build.fingerprint': FINGERPRINT,
                      'ro.build.version.release': '12', 'ro.build.version.sdk': '31', 'ro.serialno': 'RG0012996',
                      'persist.vendor.adb': 'false' if locked else 'true'}
        self.glassly = glassly
        self.home = [home]
        self.disabled = {'com.rokid.factorytest'}
        self.commands = []

    def __call__(self, command, **_):
        args = command[1:]
        if args[:1] == ['-s']:
            args = args[2:]
        self.commands.append(args)
        out = ''
        if args == ['version']:
            out = 'Android Debug Bridge version 1.0.41\nVersion 37.0.1\n'
        elif args == ['devices', '-l']:
            out = 'List of devices attached\nRG0012996 device usb:1-1 product:rv101 model:RV101\n'
        elif args[:1] == ['install']:
            self.glassly = True
            out = 'Performing Streamed Install\nSuccess\n'
        elif args[:1] == ['uninstall']:
            self.glassly = False
            out = 'Success\n'
        elif args[:1] == ['shell']:
            out = self.shell(args[1])
        return subprocess.CompletedProcess(command, 0, out, '')

    def shell(self, line):
        parts = line.split()
        if parts[0] == 'getprop':
            return self.props.get(parts[1], '') + '\n' if len(parts) > 1 else '[ro.serialno]: [RG0012996]\n'
        if line.startswith('setprop persist.vendor.adb'):
            self.props['persist.vendor.adb'] = parts[-1]
        if line == f'pm list packages {rokid.PACKAGE}':
            return f'package:{rokid.PACKAGE}\n' if self.glassly else ''
        if line == 'pm list packages -d':
            return ''.join(f'package:{p}\n' for p in sorted(self.disabled))
        if line.startswith('pm disable-user'):
            self.disabled.add(parts[-1])
        if line.startswith('pm enable'):
            self.disabled.discard(parts[-1])
        if line == f'cmd role get-role-holders {rokid.HOME_ROLE}':
            return '\n'.join(self.home) + '\n'
        if line.startswith('cmd role add-role-holder'):
            self.home = [parts[-1]]
        if line.startswith('cmd role remove-role-holder') and parts[-1] in self.home:
            self.home.remove(parts[-1])
        return ''


class Reporter:
    def __init__(self):
        self.lines = []

    def log(self, text):
        self.lines.append(text)

    def status(self, text):
        self.lines.append(text)

    def progress(self, done, total):
        pass

    def check_cancel(self):
        pass


class RokidTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.output = root / 'session'
        self.output.mkdir()
        patches = [
            mock.patch.object(rokid.paths, 'backups_dir', return_value=root / 'backups'),
            mock.patch.object(adb_link, 'find', return_value='/fake/adb'),
            mock.patch.object(rokid.time, 'sleep'),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.folder.cleanup)

    def run_with(self, glasses, mode, developer=False, takeover=None):
        real = adb_link.Adb

        def make_adb(path):
            return real(path, runner=glasses)
        with mock.patch.object(rokid.adb_link, 'Adb', side_effect=make_adb), \
                mock.patch.object(rokid, 'DEVELOPER', developer), \
                mock.patch.object(rokid, 'TAKEOVER_VERIFIED', takeover or {}):
            return rokid.run(mode, self.output, Reporter())

    def writes(self, glasses):
        risky = ('install', 'uninstall')
        shell_writes = ('setprop', 'pm disable-user', 'pm enable', 'cmd role add', 'cmd role remove', 'pm uninstall')
        return [c for c in glasses.commands if c[0] in risky or (c[0] == 'shell' and c[1].startswith(shell_writes))]

    def test_backup_writes_nothing_and_records_stock(self):
        glasses = FakeGlasses()
        summary = self.run_with(glasses, 'backup')
        self.assertEqual(summary['fingerprint'], FINGERPRINT)
        self.assertEqual(self.writes(glasses), [])
        self.assertTrue((self.output / 'probe' / 'bluetooth.txt').exists())
        record = json.loads(rokid.stock_record_path('RG0012996').read_text())
        self.assertEqual(record['home_holders'], ['com.rokid.os.sprite.launcher'])

    def test_other_android_devices_are_left_alone(self):
        glasses = FakeGlasses(brand='google')
        with mock.patch.object(rokid, 'WAIT_SECONDS', 0):
            with self.assertRaisesRegex(FlashError, 'No Rokid glasses'):
                self.run_with(glasses, 'backup')
        self.assertEqual(self.writes(glasses), [])

    def test_install_is_refused_on_an_unverified_build(self):
        glasses = FakeGlasses()
        with self.assertRaisesRegex(FlashError, 'Nothing was written'):
            self.run_with(glasses, 'install')
        self.assertEqual(self.writes(glasses), [])

    def test_developer_install_keeps_the_rokid_launcher_without_a_verified_takeover(self):
        glasses = FakeGlasses(locked=True)
        summary = self.run_with(glasses, 'install', developer=True)
        self.assertTrue(glasses.glassly)
        self.assertFalse(summary['home'])
        self.assertEqual(glasses.home, ['com.rokid.os.sprite.launcher'])
        self.assertEqual(glasses.props['persist.vendor.adb'], 'true')
        self.assertIn(['install', '-r', '-g', str(self.output / 'glassly-rokid-0.1.0-dev.apk')], glasses.commands)

    def test_verified_takeover_then_restore_puts_the_recorded_state_back(self):
        glasses = FakeGlasses()
        plan = {FINGERPRINT: {'disable': ['com.rokid.os.sprite.launcher', 'com.rokid.sysconfig']}}
        summary = self.run_with(glasses, 'install', developer=True, takeover=plan)
        self.assertTrue(summary['home'])
        self.assertEqual(glasses.home, [rokid.PACKAGE])
        self.assertIn('com.rokid.sysconfig', glasses.disabled)
        self.run_with(glasses, 'restore')
        self.assertFalse(glasses.glassly)
        self.assertEqual(glasses.home, ['com.rokid.os.sprite.launcher'])
        self.assertEqual(glasses.disabled, {'com.rokid.factorytest'})

    def test_locked_debugging_is_reported(self):
        link = adb_link.Adb('/fake/adb', runner=lambda c, **_: subprocess.CompletedProcess(c, 0, 'RKD-- not allow cmd', ''))
        with self.assertRaisesRegex(FlashError, 'locked debugging'):
            link.shell('pm list packages')

    def test_devices_parses_states_and_properties(self):
        out = 'List of devices attached\nRG1 device usb:1 model:RV101\n192.168.1.4:5555 unauthorized\n'
        link = adb_link.Adb('/fake/adb', runner=lambda c, **_: subprocess.CompletedProcess(c, 0, out, ''))
        self.assertEqual(link.devices(), [('RG1', 'device', {'usb': '1', 'model': 'RV101'}),
                                          ('192.168.1.4:5555', 'unauthorized', {})])


if __name__ == '__main__':
    unittest.main()
