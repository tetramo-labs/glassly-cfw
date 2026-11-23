import unittest
import binascii
import json
from pathlib import Path
import struct
import tempfile
from diagnose_upload import INQUIRY, READ_FIRST_BLOCK, ReadOnlyProbe, validate_failure
from test_backup import IDENTITY, LOADER
from usb_transport import LinkError


class Link:
    def __init__(self, identity=IDENTITY, fail=False):
        self.identity = identity
        self.fail = fail
        self.calls = []

    def execute(self, cdb, n=0):
        self.calls.append(cdb)
        if self.fail:
            raise LinkError('residue mismatch')
        return self.identity if cdb == INQUIRY else bytes(n)


class ProbeTests(unittest.TestCase):
    def test_failed_capture_gate(self):
        cdb = (bytes.fromhex('fb0600012000020000') +
               binascii.crc_hqx(LOADER[:512], 0).to_bytes(2, 'little') + b'\xff' * 5)
        meta = dict(operation='backup', complete=False, flash_modified=False,
                    usb_location='0x100000', inquiry=IDENTITY.hex(),
                    last_usb_command=dict(cdb=cdb.hex(),
                        cbw=struct.pack('<4sIIBBB16s', b'USBC', 2, 512, 0, 0, 16, cdb).hex(),
                        csw=struct.pack('<4sIIB', b'USBS', 2, 512, 0).hex(),
                        complete=False, stage='status'))
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'inquiry.bin').write_bytes(IDENTITY)
            def save(value):
                (folder / 'metadata.json').write_text(json.dumps(value))
            save(meta)
            validate_failure(folder, 0x100000, LOADER)
            with self.assertRaisesRegex(RuntimeError, 'different USB location'):
                validate_failure(folder, 0x200000, LOADER)
            with self.assertRaisesRegex(RuntimeError, 'Loader hash'):
                validate_failure(folder, 0x100000, bytes(len(LOADER)))
            for key, value in (('complete', True), ('operation', 'identify'), ('flash_modified', True)):
                save(dict(meta, **{key: value}))
                with self.assertRaises(RuntimeError):
                    validate_failure(folder, 0x100000, LOADER)
            save(dict(meta, last_usb_command=dict(meta['last_usb_command'], csw='00' * 13)))
            with self.assertRaisesRegex(RuntimeError, 'reviewed first-block'):
                validate_failure(folder, 0x100000, LOADER)
            save(meta)
            (folder / 'inquiry.bin').write_bytes(bytes(36))
            with self.assertRaisesRegex(RuntimeError, 'Saved inquiry mismatch'):
                validate_failure(folder, 0x100000, LOADER)

    def test_only_identity_then_one_exact_ram_read(self):
        link = Link()
        probe = ReadOnlyProbe(link)
        for cdb, n in ((READ_FIRST_BLOCK, 512), (bytes.fromhex('fb08'), 16)):
            with self.assertRaises(RuntimeError):
                probe.execute(cdb, n=n)
        self.assertEqual(link.calls, [])
        probe.execute(INQUIRY, n=36)
        for cdb, n, out in ((READ_FIRST_BLOCK, 256, None),
                            (READ_FIRST_BLOCK, 512, b'x'),
                            (READ_FIRST_BLOCK[:5] + b'\x01' + READ_FIRST_BLOCK[6:], 512, None)):
            with self.assertRaises(RuntimeError):
                probe.execute(cdb, n=n, out=out)
        probe.execute(READ_FIRST_BLOCK, n=512)
        with self.assertRaises(RuntimeError):
            probe.execute(READ_FIRST_BLOCK, n=512)
        self.assertEqual(link.calls, [INQUIRY, READ_FIRST_BLOCK])

    def test_identity_or_transport_failure_stops_all_commands(self):
        for link in (Link(IDENTITY.replace(b'BR23', b'BD19')), Link(fail=True), Link(b'')):
            probe = ReadOnlyProbe(link)
            with self.assertRaises(RuntimeError):
                probe.execute(INQUIRY, n=36)
            with self.assertRaises(RuntimeError):
                probe.execute(READ_FIRST_BLOCK, n=512)
            self.assertEqual(link.calls, [INQUIRY])


if __name__ == '__main__':
    unittest.main()
