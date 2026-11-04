"""Exercise strict BOT status handling and diagnostic retention without USB."""
import struct
import unittest
from usb_transport import NativeLink, LinkError

CDB = bytes.fromhex('fb06000120000200001234ffffffffff')

class ScriptedLink(NativeLink):
    def __init__(self, signature=b'USBS', tag=1, residue=0, status=0):
        super().__init__(None)
        self.csw = struct.pack('<4sIIB', signature, tag, residue, status)
        self.transfers = []
    def transfer(self, ep, value):
        self.transfers.append((ep, value))
        return self.csw if ep == 0x81 else b''

class DiagnosticsTests(unittest.TestCase):
    def test_each_status_mismatch_is_rejected_and_retained(self):
        for kw in ({'signature': b'bad!'}, {'tag': 2}, {'residue': 512}, {'status': 1}, {'status': 2}):
            with self.subTest(**kw):
                link = ScriptedLink(**kw)
                with self.assertRaisesRegex(LinkError, 'cdb=.*csw=.*residue=.*status='):
                    link.execute(CDB, out=bytes(512))
                d = link.last_command
                self.assertEqual(d['cdb'], CDB.hex())
                self.assertEqual(d['csw'], link.csw.hex())
                self.assertFalse(d['complete'])
                self.assertEqual(d['stage'], 'status')
                self.assertEqual(len(link.transfers), 3)
    def test_success_keeps_exact_data_out_framing(self):
        link = ScriptedLink()
        self.assertEqual(link.execute(CDB, out=bytes(512)), b'')
        cbw = struct.unpack('<4sIIBBB16s', link.transfers[0][1])
        self.assertEqual(cbw, (b'USBC', 1, 512, 0, 0, 16, CDB))
        self.assertTrue(link.last_command['complete'])
    def test_transfer_error_records_phase(self):
        link = ScriptedLink()
        def fail(ep, value):
            if ep == 0x81:
                raise LinkError('transfer failed')
            return b''
        link.transfer = fail
        with self.assertRaisesRegex(LinkError, 'transfer failed'):
            link.execute(CDB, out=bytes(512))
        self.assertEqual(link.last_command['stage'], 'status')
        self.assertNotIn('csw', link.last_command)
        self.assertFalse(link.last_command['complete'])

    def test_rejected_data_is_retained_without_accepting_status(self):
        link = ScriptedLink(residue=512)
        block = bytes(range(256)) * 2
        def transfer(ep, value):
            if ep == 0x81:
                return block if value == 512 else link.csw
            return b''
        link.transfer = transfer
        with self.assertRaises(LinkError):
            link.execute(bytes.fromhex('fd07000120000200ffffffffffffffff'), n=512)
        self.assertEqual(link.last_data, block)
        self.assertFalse(link.last_command['complete'])
        with self.assertRaises(LinkError):
            link.execute(CDB, out=bytes(512))
        self.assertIsNone(link.last_data)

if __name__ == '__main__':
    unittest.main()
