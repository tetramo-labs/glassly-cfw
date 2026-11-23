"""Public CLI and per-unit packaging regressions; no USB commands are sent."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from ananke_flasher import applications, plan, decode, ROOT, BASE, AREA_BYTES, crc
from flash_ananke import target_pair, PyUsbInstallLink
from usb_transport import LinkError
from test_flash_controller import MemoryLink


class PublicTransportTests(unittest.TestCase):
    def test_target_is_explicit_decimal_pair(self):
        self.assertEqual(target_pair('1:23'), (1, 23))
        for value in ('', 'all', '1', '-1:3', '1:2:3'):
            with self.assertRaises(Exception): target_pair(value)

    def test_pyusb_installer_uses_same_status_and_allowlist(self):
        # Real common BOT executor with emulated raw endpoint transfers.
        link = PyUsbInstallLink((1, 2))
        memory = MemoryLink(bytes(0x100000))
        link.transfer = memory.transfer
        link.flash_read_size = 0x100000
        cdb = b'\xfd\x05' + struct.pack('>IH', 0, 256) + b'\xff'*8
        self.assertEqual(link.execute(cdb, n=256), bytes(256))
        memory.bad_status = {'status': 1}
        with self.assertRaises(LinkError): link.execute(cdb, n=256)
        with self.assertRaises(LinkError): link.execute(b'\xfb\x00'+b'\xff'*14, n=16)
        with self.assertRaises(LinkError): link.execute(b'\xfb\x01'+bytes(4)+b'\xff'*10, n=16)

    def test_bad_official_file_stops_offline(self):
        with self.assertRaisesRegex(RuntimeError, 'IG05_V0900'):
            applications(ROOT/'firmware/dist/payload.bin')


@unittest.skipUnless((ROOT/'research/IG05_V0900.ufw').exists() and
                     (ROOT/'research/device-backup-20261103-174931/flash-pass1.bin').exists() and
                     importlib.util.find_spec('crcmod'), 'Private OEM/backup fixtures unavailable')
class PublicPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock, cls.custom = applications(ROOT/'research/IG05_V0900.ufw')
        cls.original = (ROOT/'research/device-backup-20261103-174931/flash-pass1.bin').read_bytes()

    def test_reproduces_verified_flash_and_restores(self):
        desired = plan(self.original, self.stock, self.custom, 'install')
        self.assertEqual(hashlib.sha256(desired).hexdigest(), '574f6542ef749741721d8bf040aa0b45eb8837d9357b900865473400027d2c59')
        self.assertEqual(plan(desired, self.stock, self.custom, 'install'), desired)
        restored = plan(desired, self.stock, self.custom, 'restore')
        self.assertEqual(plan(restored, self.stock, self.custom, 'install'), desired)
        self.assertEqual(restored[:BASE], self.original[:BASE])
        self.assertEqual(restored[BASE+AREA_BYTES:], self.original[BASE+AREA_BYTES:])

    def test_preserves_live_settings_and_keys(self):
        live = bytearray(self.original)
        live[0xf3000:] = bytes((i * 13) % 256 for i in range(len(live)-0xf3000))
        desired = plan(bytes(live), self.stock, self.custom, 'install')
        self.assertEqual(desired[BASE+AREA_BYTES:], live[BASE+AREA_BYTES:])
        self.assertEqual(desired[:BASE], live[:BASE])

    def test_rejects_changes_in_map_boot_config_and_app(self):
        for offset in (0, 0x20, 0xc0, 0x20a8, BASE, 0x3140, 0x56de8):
            bad = bytearray(self.original); bad[offset] ^= 1
            with self.assertRaises((ValueError, RuntimeError)):
                plan(bytes(bad), self.stock, self.custom, 'install')
        with self.assertRaises(RuntimeError): plan(self.original[:-1], self.stock, self.custom, 'install')
        with self.assertRaises(RuntimeError): plan(self.original, self.stock, self.custom[:-1]+b'\0', 'install')

class PublicCliTests(unittest.TestCase):
    def test_backup_retains_two_immutable_reads_and_verifiable_metadata(self):
        import json
        import shutil
        import subprocess
        import sys
        import tempfile
        from flash_ananke import main
        from backup_controller import INQUIRY
        from usb_transport import BR23_INQUIRY
        image = bytes(range(256)) * 4096
        link = MemoryLink(image)
        execute = link.execute
        link.execute = lambda cdb, out=None, n=0: BR23_INQUIRY if cdb == INQUIRY else execute(cdb, out, n)
        link.try_open = lambda: True
        link.close = lambda: None
        def prepared(reader, inquiry, loader, record):
            reader.loader = b'prepared-test-loader'
            reader.size = len(image)
            return {}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('flash_ananke.py', 'ananke_flasher.py', 'flash_controller.py', 'usb_transport.py', 'backup_controller.py'):
                shutil.copy(ROOT/'research'/name, root/name)
            (root/'deps').mkdir(); (root/'deps/br23loader.bin').write_bytes(b'test')
            with patch('flash_ananke.ROOT', root), patch('sys.platform', 'linux'), \
                 patch('sys.argv', ['flash_ananke.py', 'backup', '--device', '1:2']), \
                 patch('sys.stdin.isatty', return_value=True), \
                 patch('flash_ananke.os.geteuid', return_value=1, create=True), \
                 patch('flash_ananke.PyUsbInstallLink', return_value=link), \
                 patch('flash_ananke.Transport.prepare', prepared):
                main()
            folder = next(root.glob('flash-attempt-*'))
            meta = json.loads((folder/'metadata.json').read_text())
            self.assertTrue(meta['complete'] and meta['backup_complete'])
            self.assertFalse(meta['flash_write_attempted'])
            self.assertEqual((folder/'before-pass1.bin').read_bytes(), image)
            self.assertEqual((folder/'before-pass2.bin').read_bytes(), image)
            self.assertFalse((folder/'before-pass1.bin').stat().st_mode & 0o222)
            subprocess.run([sys.executable, str(ROOT/'scripts/verify_backup.py'), str(folder)], check=True, capture_output=True)
            self.assertFalse(any(c[:2] in (b'\xfb\x01', b'\xfb\x04') for c in link.calls))
