import json
from pathlib import Path
import struct
import tempfile
import unittest

from backup_controller import Transport, digest, validate_prepared_backup
from test_backup import FakeLink, IDENTITY, LOADER
from test_rom_residue import RomLink
from usb_transport import LinkError


class JumpResidueLink(RomLink):
    def expected_residue(self, cdb, out, n):
        expected = super().expected_residue(cdb, out, n)
        # Reproduce the historical zero-residue policy that captured this evidence.
        return 0 if cdb[:2] == b'\xfb\x08' else expected
    def transfer(self, ep, value):
        data = super().transfer(ep, value)
        if ep == 0x81 and value == 13 and self.cdb[:2] == b'\xfb\x08':
            return struct.pack('<4sIIB', b'USBS', self.current_tag, 16, 0)
        return data


class ReadLoadedTests(unittest.TestCase):
    def test_prepared_evidence_requires_all_commands_and_hashes(self):
        link = JumpResidueLink()
        link.tag = 1  # Recorded INQUIRY was command 1.
        meta = dict(operation='backup', complete=False, flash_modified=False,
                    usb_location='0x2100000', inquiry=IDENTITY.hex())
        with self.assertRaises(LinkError):
            Transport(link).prepare(IDENTITY, LOADER, meta.update)
        meta['last_usb_command'] = link.last_command
        meta['rejected_data'] = dict(sha256=digest(link.last_data))
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/'inquiry.bin').write_bytes(IDENTITY)
            (folder/'rejected-data-incomplete.bin').write_bytes(link.last_data)
            def save():
                (folder/'metadata.json').write_text(json.dumps(meta))
            save()
            result = validate_prepared_backup(folder, 0x2100000, LOADER)
            self.assertTrue(result['ram_transcript_verified'])
            with self.assertRaises(RuntimeError):
                validate_prepared_backup(folder, 0x100000, LOADER)
            original = meta['ram_commands'][1]['data_sha256']
            meta['ram_commands'][1]['data_sha256'] = '0'*64
            save()
            with self.assertRaisesRegex(RuntimeError, 'RAM hash mismatch'):
                validate_prepared_backup(folder, 0x2100000, LOADER)
            meta['ram_commands'][1]['data_sha256'] = original
            meta['ram_commands'].pop()
            save()
            with self.assertRaisesRegex(RuntimeError, 'complete RAM transcript'):
                validate_prepared_backup(folder, 0x2100000, LOADER)

    def test_read_loaded_cannot_upload_jump_or_modify_flash(self):
        link = FakeLink()
        transport = Transport(link)
        transport.loader = LOADER
        transport.read_only = True
        for op in (0xfb06, 0xfd07, 0xfb08, 0xfb01, 0xfb04, 0xfc09):
            with self.assertRaises(RuntimeError):
                transport.command(op)
        self.assertEqual(link.calls, [])
        self.assertEqual(transport.flash_identity()['size'], 524288)
        self.assertEqual([c[:2].hex() for c in link.calls], ['fc0a', 'fc0b', 'fc14'])


if __name__ == '__main__':
    unittest.main()
