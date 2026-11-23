import binascii
import struct
import unittest

from backup_controller import Transport
from test_backup import IDENTITY, LOADER
from usb_transport import LinkError, NativeLink, ROM_RAM_POLICY, LOADER_QUERY_POLICY


class RomLink(NativeLink):
    def __init__(self):
        super().__init__(None)
        self.calls = []
        self.memory = bytearray(len(LOADER))
        self.bad_ram = False
        self.bad_status = None
        self.cdb = None

    def transfer(self, ep, value):
        if ep == 1 and len(value) == 31:
            _, self.current_tag, self.size, self.flags, _, _, self.cdb = struct.unpack('<4sIIBBB16s', value)
            self.calls.append(self.cdb)
            return b''
        op = int.from_bytes(self.cdb[:2], 'big')
        offset = int.from_bytes(self.cdb[2:6], 'big') - 0x12000
        if ep == 1:
            self.memory[offset:offset+len(value)] = value
            return b''
        if value == 13:
            residue = 512 if op in (0xfb06, 0xfd07) else 16 if op in (0xfb08, 0xfc0a, 0xfc0b, 0xfc14) else 256 if op == 0xfd05 else 0
            fields = dict(signature=b'USBS', tag=self.current_tag, residue=residue, status=0)
            fields.update(self.bad_status or {})
            return struct.pack('<4sIIB', *fields.values())
        if op == 0xfd07:
            return bytes(512) if self.bad_ram else bytes(self.memory[offset:offset+value])
        if op == 0xfd05:
            return bytes(range(256))
        values = {0xfc0a: bytes.fromhex('030014608500'), 0xfc0b: bytes.fromhex('00856000'),
                  0xfc14: bytes.fromhex('00008000')}
        return (self.cdb[:2]+values.get(op, b'')).ljust(value, b'\0')


def write_cdb():
    return (bytes.fromhex('fb0600012000020000') +
            binascii.crc_hqx(LOADER[:512], 0).to_bytes(2, 'little') + b'\xff'*5)


class RomResidueTests(unittest.TestCase):
    def test_full_pinned_upload_readback_and_strict_post_loader(self):
        link = RomLink()
        records = []
        Transport(link).prepare(IDENTITY, LOADER, records.append)
        self.assertIsNone(link.rom_loader)
        self.assertEqual(records[0]['rom_ram_residue_policy'], ROM_RAM_POLICY)
        self.assertEqual(len(records[1]['ram_commands']), 44)
        self.assertTrue(records[1]['ram_readback_verified'])
        self.assertTrue(all(c['expected_residue'] == c['residue'] == 512
                            for c in records[1]['ram_commands']))
        self.assertEqual(link.last_command['residue_policy'], LOADER_QUERY_POLICY)
        self.assertEqual(len(records[-2]['flash_identity_commands']), 3)
        self.assertEqual(link.expected_residue(bytes.fromhex('fd05000000000100')+b'\xff'*8, None, 256), 256)

    def test_flash_profile_requires_measured_identity_and_verified_session(self):
        link = RomLink()
        with self.assertRaises(LinkError):
            link.enable_br23_flash_reads(0x100000)
        Transport(link).prepare(IDENTITY, LOADER)
        for size in (0, 0x80000, 0x200000):
            with self.assertRaises(LinkError):
                link.enable_br23_flash_reads(size)
        link.loader_query_replies[0xfc0b] = b'\xfc\x0b'+bytes(14)
        with self.assertRaises(LinkError):
            link.enable_br23_flash_reads(0x100000)

    def test_flash_read_bounds_and_status(self):
        link = RomLink()
        transport = Transport(link)
        transport.prepare(IDENTITY, LOADER)
        self.assertEqual(transport.command(0xfd05, struct.pack('>IH', 0, 256), n=256), bytes(range(256)))
        count = len(link.calls)
        for address, n in ((1,256), (0x100000,256), (0,512)):
            with self.assertRaises(LinkError):
                link.execute(b'\xfd\x05'+struct.pack('>IH',address,n)+b'\xff'*8,n=n)
        self.assertEqual(len(link.calls), count)
        for bad in ({'residue':0}, {'residue':255}, {'residue':257}, {'status':1}, {'tag':99}):
            link.bad_status = bad
            with self.assertRaises(LinkError):
                transport.command(0xfd05, struct.pack('>IH', 0, 256), n=256)

    def test_loader_query_profile_remains_strict(self):
        for bad in ({'residue':0}, {'residue':1}, {'residue':15}, {'residue':17},
                    {'status':1}, {'tag':99}, {'signature':b'bad!'}):
            link = RomLink()
            Transport(link).prepare(IDENTITY, LOADER)
            link.bad_status = bad
            with self.assertRaises(LinkError):
                link.execute(b'\xfc\x0a'+b'\xff'*14, n=16)
        link = RomLink()
        Transport(link).prepare(IDENTITY, LOADER)
        count = len(link.calls)
        for cdb, out, n in ((b'\xfc\x0a'+bytes(14), None, 16),
                            (b'\xfc\x0b'+b'\xff'*14, None, 15),
                            (b'\xfc\x14'+b'\xff'*14, bytes(16), 0)):
            with self.assertRaises(LinkError):
                link.execute(cdb, out, n)
        self.assertEqual(len(link.calls), count)

    def test_bad_loader_reply_stops_before_next_query(self):
        class BadReply(RomLink):
            def transfer(self, ep, value):
                data = super().transfer(ep, value)
                if self.cdb[:2] == b'\xfc\x0a' and ep == 0x81 and value == 16:
                    return b'bad!' + data[4:]
                return data
        link = BadReply()
        with self.assertRaisesRegex(LinkError, 'acknowledgement mismatch'):
            Transport(link).prepare(IDENTITY, LOADER)
        self.assertEqual(link.calls[-1][:2], b'\xfc\x0a')

    def test_identity_and_blob_gate(self):
        for identity, loader in ((IDENTITY.replace(b'BR23', b'BD19'), LOADER),
                                 (IDENTITY[:-1]+b'1', LOADER), (IDENTITY, bytes(len(LOADER)))):
            link = RomLink()
            with self.assertRaises(LinkError):
                link.enable_br23_rom_ram(identity, loader)
            self.assertIsNone(link.rom_loader)
            self.assertEqual(link.calls, [])

    def test_arbitrary_residue_status_tag_signature_still_fail(self):
        for bad in ({'residue':0}, {'residue':1}, {'residue':511}, {'residue':513},
                    {'status':1}, {'status':2}, {'tag':99}, {'signature':b'bad!'}):
            with self.subTest(bad=bad):
                link = RomLink()
                link.bad_status = bad
                link.enable_br23_rom_ram(IDENTITY, LOADER)
                with self.assertRaises(LinkError):
                    link.execute(write_cdb(), out=LOADER[:512])
                self.assertFalse(link.last_command['complete'])

    def test_ram_mismatch_never_reaches_jump(self):
        link = RomLink()
        link.bad_ram = True
        with self.assertRaisesRegex(RuntimeError, 'RAM readback mismatch'):
            Transport(link).prepare(IDENTITY, LOADER)
        self.assertEqual([c[:2].hex() for c in link.calls], ['fb06', 'fd07'])

    def test_full_residue_not_accepted_for_other_commands_or_default_transport(self):
        link = RomLink()
        with self.assertRaises(LinkError):
            link.execute(write_cdb(), out=LOADER[:512])
        link = RomLink()
        link.enable_br23_rom_ram(IDENTITY, LOADER)
        link.bad_status = {'residue':16}
        for op in (0xfc0a, 0xfc0b, 0xfc14, 0xfd05):
            with self.assertRaises(LinkError):
                link.execute(op.to_bytes(2,'big') + b'\xff'*14, n=16)

    def test_jump_requires_all_blocks_and_exact_arguments(self):
        link = RomLink()
        link.enable_br23_rom_ram(IDENTITY, LOADER)
        jump = bytes.fromhex('fb08000120000001') + b'\xff'*8
        with self.assertRaises(LinkError):
            link.execute(jump, n=16)
        self.assertEqual(link.calls, [])
        link.rom_verified = set(range(0, 11264, 512))
        with self.assertRaises(LinkError):
            link.execute(jump[:7] + b'\x07' + jump[8:], n=16)
        self.assertEqual(link.calls, [])
        link.execute(jump, n=16)
        self.assertEqual(link.last_command['expected_residue'], 16)
        self.assertIsNone(link.rom_loader)

    def test_jump_bad_ack_or_status_never_reaches_flash_queries(self):
        class BadJump(RomLink):
            def transfer(self, ep, value):
                data = super().transfer(ep, value)
                if self.cdb[:2] == b'\xfb\x08' and ep == 0x81 and value == 16:
                    return b'bad!' + data[4:]
                return data
        link = BadJump()
        with self.assertRaisesRegex(LinkError, 'acknowledgement mismatch'):
            Transport(link).prepare(IDENTITY, LOADER)
        self.assertEqual(link.calls[-1][:2], b'\xfb\x08')
        self.assertNotIn(b'\xfc\x0a', [c[:2] for c in link.calls])

    def test_unpinned_ram_or_malformed_bounds_never_sent(self):
        for cdb, out, n in ((write_cdb(), bytes(512), 0),
                            (write_cdb()[:5]+b'\x01'+write_cdb()[6:], LOADER[:512], 0),
                            (bytes.fromhex('fd0700014c000200')+b'\xff'*8, None, 512),
                            (bytes.fromhex('fd07000120000100')+b'\xff'*8, None, 256)):
            link = RomLink()
            link.enable_br23_rom_ram(IDENTITY, LOADER)
            with self.assertRaises(LinkError):
                link.execute(cdb, out=out, n=n)
            self.assertEqual(link.calls, [])


if __name__ == '__main__':
    unittest.main()
