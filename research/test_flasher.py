"""Offline checks for the one-shot flasher against the unit2 artifacts. No USB access."""
import contextlib, io, os, unittest
os.environ.setdefault('GB_DEVICE', 'unit2')
from pathlib import Path
from gamebrick_flasher import CUSTOM_APP_SHA, classify, custom_application, oem_application, oem_archive, plan
from flash_layout import APPLICATIONS, LAYOUTS, Layout, userif_record_size
from flash_gamebrick import program_with_plan
from stock_update import digest, OEM_SHA
from test_custom_image import NOR
ROOT = Path(__file__).resolve().parent

class FlasherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = (ROOT/'device-backup-20261028-192851/flash-pass1.bin').read_bytes()
        cls.stock = (ROOT/'stock-update-prepared/unit2/stock-app-device-layout.bin').read_bytes()
        cls.custom = (ROOT/'custom-prepared/unit2/custom-device-layout.bin').read_bytes()
        cls.oem = oem_application(oem_archive(ROOT/'stock-update.zip', log=lambda *_: None))

    def test_official_application_and_patch_are_pinned(self):
        self.assertEqual(digest(self.oem), OEM_SHA)
        self.assertEqual(oem_application(), self.oem, 'the committed official application is the archive\'s')
        patched = custom_application(self.oem)
        self.assertEqual(digest(patched), CUSTOM_APP_SHA)
        self.assertEqual(custom_application(), patched, 'the committed Glassly application is the patched build')
        self.assertEqual(patched, (ROOT/'custom-prepared/unit2/app.bin').read_bytes(), 'same bytes as the reviewed per-unit build')
        with self.assertRaises(RuntimeError):
            custom_application(b'\0' + self.oem[1:])

    def test_layouts_and_applications_classify_every_known_state(self):
        self.assertEqual(classify(self.factory), 'factory')
        self.assertEqual(classify(self.stock), 'stock')
        self.assertEqual(classify(self.custom), 'custom')
        self.assertEqual(classify((ROOT/'custom-flash-unit2-20261028-193401/target.bin').read_bytes()), 'custom')
        self.assertEqual(classify((ROOT/'device-backup-20261022-233350/flash-pass1.bin').read_bytes()), 'factory', 'unit1 shares the layout')
        drifted = bytearray(self.factory); drifted[0x7a123] ^= 0xFF; drifted[0x7f000] = 0x12
        self.assertEqual(classify(bytes(drifted)), 'factory', 'live storage does not change the classification')
        for address in (0, 0x2140, 0x79fff):
            bad = bytearray(self.factory); bad[address] ^= 1
            self.assertEqual(classify(bytes(bad)), 'unknown')
        self.assertEqual(len(LAYOUTS), 2)
        self.assertEqual(len(APPLICATIONS), 5)

    def test_plans_from_every_state_reach_the_reviewed_images(self):
        rebuilt = plan(self.factory, self.oem, 'install', custom_application(self.oem), flash_id=0xcd7113)
        from_factory = plan(self.factory, self.oem, 'install', flash_id=0xcd7113)
        self.assertEqual(rebuilt['target'], from_factory['target'], 'committed and rebuilt applications agree')
        self.assertEqual(from_factory['state'], 'factory')
        self.assertEqual(from_factory['target'], self.custom, 'factory straight to the reviewed unit2 custom image')
        self.assertEqual(from_factory['stock'], self.stock)
        self.assertEqual(len(from_factory['changed_sectors']), 50)
        from_stock = plan(self.stock, self.oem, 'install', flash_id=0xcd7113)
        self.assertEqual(from_stock['target'], self.custom)
        self.assertEqual([hex(a) for a in from_stock['changed_sectors']], ['0x2000','0x6000','0x7000','0xd000','0x11000','0x12000','0x32000','0x33000'])
        from_custom = plan(self.custom, self.oem, 'install', flash_id=0xcd7113)
        self.assertEqual(from_custom['changed_sectors'], [])
        back = plan(self.custom, self.oem, 'restore', flash_id=0xcd7113)
        self.assertEqual(back['target'], self.stock)
        self.assertEqual(plan(self.factory, self.oem, 'restore', flash_id=0xcd7113)['target'], self.stock)
        # Live storage rides along untouched.
        drifted = bytearray(self.factory); drifted[0x7a123] ^= 0xFF
        live = plan(bytes(drifted), self.oem, 'install', flash_id=0xcd7113)
        self.assertEqual(live['target'][0x7a000:], bytes(drifted)[0x7a000:])
        self.assertEqual(live['target'][:0x7a000], self.custom[:0x7a000])
        for state in ('withdrawn', 'unknown'):
            image = bytearray((ROOT/'custom-prepared/custom-device-layout-withdrawn-20261025.bin').read_bytes() if state == 'withdrawn' else self.factory)
            if state == 'unknown': image[0x2140] ^= 1
            with self.assertRaisesRegex(RuntimeError, 'Unrecognised'):
                plan(bytes(image), self.oem, 'install', flash_id=0xcd7113)

    def test_programs_factory_to_custom_and_back_with_full_verification(self):
        oem = self.oem
        device = NOR(self.factory, range(0, 0x80000, 4096))
        saved = {}
        with contextlib.redirect_stdout(io.StringIO()):
            report = program_with_plan(device, lambda current: (current, plan(current, oem, 'install', flash_id=0xcd7113)['target']), saved.__setitem__)
        self.assertTrue(report['full_readback_verified'])
        self.assertEqual(bytes(device.data), self.custom)
        self.assertEqual(saved['flash-pass1.bin'], self.factory)
        self.assertEqual(device.erased[-1], 0x2000, 'the header sector is committed last')
        self.assertFalse(device.writes_enabled)
        with contextlib.redirect_stdout(io.StringIO()):
            again = program_with_plan(device, lambda current: (current, plan(current, oem, 'install', flash_id=0xcd7113)['target']), saved.__setitem__)
        self.assertEqual(again['writes'], 0)
        with contextlib.redirect_stdout(io.StringIO()):
            program_with_plan(device, lambda current: (current, plan(current, oem, 'restore', flash_id=0xcd7113)['target']), saved.__setitem__)
        self.assertEqual(bytes(device.data), self.stock)

    def test_unstable_or_unknown_flash_never_enables_writes(self):
        oem = self.oem
        class Unstable(NOR):
            reads = 0
            def read(self, a, n):
                self.reads += 1
                if self.reads == 2: self.data[0x7a000] ^= 1
                return super().read(a, n)
        shaky = Unstable(self.factory, range(0, 0x80000, 4096))
        with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
            program_with_plan(shaky, lambda current: (current, plan(current, oem, 'install', flash_id=0xcd7113)['target']), lambda n, d: None)
        self.assertFalse(shaky.erased)
        bad = bytearray(self.factory); bad[0x40000] ^= 1
        unknown = NOR(bytes(bad), range(0, 0x80000, 4096))
        with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
            program_with_plan(unknown, lambda current: (current, plan(current, oem, 'install', flash_id=0xcd7113)['target']), lambda n, d: None)
        self.assertFalse(unknown.erased)

TESTER = ROOT/'device-backup-20261113-tester/flash-pass1.bin'


@unittest.skipUnless(TESTER.exists(), 'tester backup unavailable')
class IineLayoutTests(unittest.TestCase):
    """A user's unit on IINE's current layout with the Sep 2025 factory build."""
    @classmethod
    def setUpClass(cls):
        cls.image = TESTER.read_bytes(); cls.oem = oem_application()
        # The real dump keeps its Sep-format settings; the plan mechanics are exercised on a copy with erased settings.
        blank = bytearray(cls.image); blank[0x7d000:0x7f000] = b'\xff' * 0x2000; cls.blank = bytes(blank)
        cls.factory_a = (ROOT/'device-backup-20261028-192851/flash-pass1.bin').read_bytes()

    def test_tester_unit_is_recognised(self):
        self.assertEqual(classify(self.image), 'factory-2025-09')
        layout = Layout(self.image)
        self.assertEqual((layout.base, layout.limit, layout.key), (0x2000, 0x34000, 0x190d))
        self.assertEqual(layout.storage, [(0x34000, 0x7b000), (0x7b000, 0x7c000), (0x7c000, 0x7d000), (0x7d000, 0x7f000), (0x7f000, 0x80000)])

    def test_plans_keep_everything_outside_the_application_area(self):
        install = plan(self.blank, self.oem, 'install', allow_unverified=True)
        self.assertEqual(install['state'], 'factory-2025-09')
        target = install['target']
        self.assertEqual(classify(target), 'custom')
        self.assertEqual(Layout(target).application(), custom_application())
        self.assertEqual(target[:0x2000], self.blank[:0x2000])
        self.assertEqual(target[0x34000:], self.blank[0x34000:])
        self.assertTrue(install['changed_sectors'] and all(0x2000 <= a < 0x34000 for a in install['changed_sectors']))
        self.assertEqual(plan(target, self.oem, 'install', allow_unverified=True)['changed_sectors'], [])
        restore = plan(target, self.oem, 'restore', allow_unverified=True)
        self.assertEqual(classify(restore['target']), 'stock')
        self.assertEqual(Layout(restore['target']).application(), self.oem)
        self.assertEqual(restore['target'], install['stock'])
        self.assertEqual(restore['target'][0x34000:], self.blank[0x34000:])

    def test_settings_record_format_refuses_the_application_that_bricked_the_tester(self):
        self.assertEqual(userif_record_size(Layout(self.image)), 0x38)
        self.assertEqual(userif_record_size(Layout(self.factory_a)), 0x40)
        self.assertEqual(userif_record_size(Layout(self.blank)), 'blank')
        for mode in ('install', 'restore'):
            with self.assertRaisesRegex(RuntimeError, 'different settings layout.*record size 0x38.*expects 0x40'):
                plan(self.image, self.oem, mode, flash_id=0xcd7013, allow_unverified=True)
        flashed = plan(self.blank, self.oem, 'install', allow_unverified=True)['target']
        with_old_settings = flashed[:0x7d000] + self.image[0x7d000:0x7f000] + flashed[0x7f000:]
        back = plan(with_old_settings, self.oem, 'restore-backup', backup=self.image)
        self.assertEqual(back['target_state'], 'factory-2025-09')
        self.assertEqual(back['target'], self.image, 'the Sep application goes back over its own settings')
        mixed = self.factory_a[:0x7d000] + self.image[0x7d000:0x7f000] + self.factory_a[0x7f000:]
        with self.assertRaisesRegex(RuntimeError, 'different settings layout'):
            plan(mixed, self.oem, 'install', flash_id=0xcd7113)

    def test_install_and_restore_are_refused_on_this_layout_until_boot_is_understood(self):
        for mode in ('install', 'restore'):
            with self.assertRaisesRegex(RuntimeError, 'not been flashed and seen booting'):
                plan(self.image, self.oem, mode, flash_id=0xcd7013)
        with self.assertRaisesRegex(RuntimeError, 'not been flashed and seen booting'):
            plan(self.factory_a, self.oem, 'install', flash_id=0xcd7013)
        self.assertEqual(plan(self.factory_a, self.oem, 'install', flash_id=0xcd7113)['target_state'], 'custom')
        self.assertEqual(plan(self.image, self.oem, 'restore-backup', backup=self.image)['changed_sectors'], [])

    def test_programs_the_iine_layout_with_full_verification(self):
        oem = self.oem
        device = NOR(self.blank, range(0, 0x80000, 4096))
        with contextlib.redirect_stdout(io.StringIO()):
            report = program_with_plan(device, lambda current: (current, plan(current, oem, 'install', allow_unverified=True)['target']), lambda n, d: None)
        self.assertTrue(report['full_readback_verified'])
        self.assertEqual(classify(bytes(device.data)), 'custom')
        self.assertEqual(bytes(device.data[0x34000:]), self.blank[0x34000:])
        self.assertEqual(device.erased[-1], 0x2000, 'the header sector is committed last')
        self.assertLessEqual(max(device.erased) + 4096, 0x34000)
        with contextlib.redirect_stdout(io.StringIO()):
            program_with_plan(device, lambda current: (current, plan(current, oem, 'restore', allow_unverified=True)['target']), lambda n, d: None)
        self.assertEqual(classify(bytes(device.data)), 'stock')
        self.assertEqual(bytes(device.data[0x34000:]), self.blank[0x34000:])

    def test_restore_backup_puts_the_factory_application_back(self):
        oem = self.oem
        device = NOR(self.blank, range(0, 0x80000, 4096))
        with contextlib.redirect_stdout(io.StringIO()):
            program_with_plan(device, lambda current: (current, plan(current, oem, 'install', allow_unverified=True)['target']), lambda n, d: None)
        self.assertEqual(classify(bytes(device.data)), 'custom')
        flashed = bytes(device.data)
        back = plan(flashed, oem, 'restore-backup', backup=self.blank)
        self.assertEqual(back['target_state'], 'factory-2025-09')
        self.assertEqual(Layout(back['target']).application(), Layout(self.blank).application())
        self.assertEqual(back['target'][0x34000:], flashed[0x34000:])
        with contextlib.redirect_stdout(io.StringIO()):
            program_with_plan(device, lambda current: (current, plan(current, oem, 'restore-backup', backup=self.blank)['target']), lambda n, d: None)
        self.assertEqual(classify(bytes(device.data)), 'factory-2025-09')
        self.assertEqual(bytes(device.data), self.blank, 'storage was untouched, so the exact original returns')
        with self.assertRaisesRegex(RuntimeError, 'not a known image'):
            plan(flashed, oem, 'restore-backup', backup=bytes(0x80000))
        with self.assertRaisesRegex(RuntimeError, 'not a known image'):
            plan(flashed, oem, 'restore-backup', backup=(ROOT/'device-backup-20261022-233350/flash-pass1.bin').read_bytes())


if __name__ == '__main__': unittest.main()
