import struct
import unittest

from flash_controller import (InstallLink, Writer, load_inputs, make_plan, SIZE,
                              SECTOR, PAGE, SECTORS, read_range, PREVIOUS, changed_sectors)
from backup_controller import Transport
from usb_transport import LinkError


class MemoryLink(InstallLink):
    def __init__(self, memory):
        super().__init__(None)
        self.memory = bytearray(memory)
        self.flash_read_size = SIZE
        self.calls = []
        self.bad_status = None
        self.ignore_erase = False
        self.corrupt_write = False

    def transfer(self, ep, value):
        if ep == 1 and len(value) == 31:
            _, self.current_tag, self.size, _, _, _, self.cdb = struct.unpack('<4sIIBBB16s', value)
            self.calls.append(self.cdb)
            self.op = int.from_bytes(self.cdb[:2], 'big')
            self.address = int.from_bytes(self.cdb[2:6], 'big')
            if self.op == 0xfb01 and not self.ignore_erase:
                self.memory[self.address:self.address+SECTOR] = b'\xff'*SECTOR
            return b''
        if ep == 1:
            for i, b in enumerate(value):
                self.memory[self.address+i] &= b
            if self.corrupt_write:
                self.memory[self.address] ^= 1
            return b''
        if value == 13:
            fields = dict(signature=b'USBS', tag=self.current_tag, residue=self.size, status=0)
            fields.update(self.bad_status or {})
            return struct.pack('<4sIIB', *fields.values())
        if self.op == 0xfd05:
            return bytes(self.memory[self.address:self.address+value])
        return self.cdb[:2]+bytes(value-2)


class FlashTests(unittest.TestCase):
    def reader(self, link):
        reader = Transport(link)
        reader.loader = b'test fixture: loader already verified'
        reader.size = SIZE
        return reader

    def setup_writer(self):
        before = bytes([0x55])*SIZE
        after = bytearray(before)
        after[0x4000:0x5000] = bytes(range(256))*16
        link = MemoryLink(before)
        events = []
        writer = Writer(link, self.reader(link), before, bytes(after), events.append)
        return link, writer, events, bytes(after)

    def test_full_sector_write_verifies_and_preserves_surroundings(self):
        link, writer, events, after = self.setup_writer()
        writer.sector(0x4000)
        self.assertEqual(link.memory, after)
        self.assertEqual(sum(c[:2] == b'\xfb\x01' for c in link.calls), 1)
        self.assertEqual(sum(c[:2] == b'\xfb\x04' for c in link.calls), 16)
        self.assertEqual(events[-1]['event'], 'sector-verified')
        self.assertEqual(link.flash_read_size, SIZE)
        self.assertIsNone(link.pending_write)
        with self.assertRaisesRegex(RuntimeError, 'repeated sector'):
            writer.sector(0x4000)

    def test_wrong_preimage_stops_before_erase(self):
        link, writer, _, _ = self.setup_writer()
        link.memory[0x4000] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'changed since preflight'):
            writer.sector(0x4000)
        self.assertFalse(any(c[:1] == b'\xfb' for c in link.calls))

    def test_erase_failure_never_programs(self):
        link, writer, _, _ = self.setup_writer()
        link.ignore_erase = True
        with self.assertRaisesRegex(RuntimeError, 'did not erase'):
            writer.sector(0x4000)
        self.assertFalse(any(c[:2] == b'\xfb\x04' for c in link.calls))

    def test_program_mismatch_stops_after_first_page(self):
        link, writer, _, _ = self.setup_writer()
        link.corrupt_write = True
        with self.assertRaisesRegex(RuntimeError, 'Program readback mismatch'):
            writer.sector(0x4000)
        self.assertEqual(sum(c[:2] == b'\xfb\x04' for c in link.calls), 1)

    def test_invalid_status_never_accepted(self):
        for bad in ({'status': 1}, {'residue': 0}, {'residue': 255}, {'tag': 99}, {'signature': b'nope'}):
            link, _, _, _ = self.setup_writer()
            link.bad_status = bad
            with self.assertRaises(LinkError):
                read_range(self.reader(link), 0, PAGE)
            self.assertFalse(link.last_command['complete'])

    def test_forbidden_commands_cannot_reach_usb(self):
        link, _, _, _ = self.setup_writer()
        for op in (0xfb00, 0xfb02, 0xfc03, 0xfc0c, 0xfc0d, 0xfc12):
            with self.assertRaises(LinkError):
                link.execute(op.to_bytes(2, 'big')+b'\xff'*14, n=16)
        for address in (0, 0x2000, 0x3001, 0x57000, 0xff000):
            cdb = b'\xfb\x01'+struct.pack('>I', address)+b'\xff'*10
            link.pending_write = (cdb, None, 16)
            with self.assertRaises(LinkError):
                link.execute(cdb, n=16)
        self.assertEqual(link.calls, [])

    def test_unarmed_write_and_backup_transport_reject_mutation(self):
        link, _, _, _ = self.setup_writer()
        cdb = b'\xfb\x01'+struct.pack('>I', 0x4000)+b'\xff'*10
        with self.assertRaises(LinkError):
            link.execute(cdb, n=16)
        reader = Transport(link)
        reader.loader = b'test'
        with self.assertRaisesRegex(RuntimeError, 'Forbidden command'):
            reader.execute(cdb, n=16)
        self.assertEqual(link.calls, [])

    @unittest.skipUnless(PREVIOUS.exists(), 'Historical unit fixtures unavailable')
    def test_real_plan_preserves_fresh_settings_and_rejects_changed_app(self):
        original, candidate = load_inputs()
        live = bytearray(original)
        live[0xf5000] ^= 1
        desired = make_plan(original, candidate, bytes(live))
        self.assertEqual(desired[0xf5000], live[0xf5000])
        self.assertEqual(desired[0xff000:], original[0xff000:])
        self.assertEqual(SECTORS[-1], 0x3000)
        live[0x3140] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'differs from original'):
            make_plan(original, candidate, bytes(live))

    @unittest.skipUnless(PREVIOUS.exists(), 'Historical unit fixtures unavailable')
    def test_incremental_upgrade_from_verified_install(self):
        original, candidate = load_inputs()
        previous = PREVIOUS.read_bytes()
        desired = make_plan(original, candidate, previous)
        self.assertEqual(desired, candidate)
        sectors = changed_sectors(previous, desired)
        self.assertEqual(sectors[-1], 0x3000)
        self.assertLess(len(sectors), len(SECTORS))
        damaged = bytearray(previous)
        damaged[0x4000] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'differs from original'):
            make_plan(original, candidate, damaged)
        damaged = bytearray(desired)
        damaged[0xff000] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'outside allowed'):
            changed_sectors(previous, damaged)


if __name__ == '__main__':
    unittest.main()
