import struct
import tempfile
import unittest
from pathlib import Path
from backup_controller import Transport, INQUIRY, ROOT, capture

LOADER = (ROOT/'deps/br23loader.bin').read_bytes()
IDENTITY = bytes.fromhex('0080020220000000425232332020202055424f4f54312e303020202020202020312e3030')


class FakeLink:
    def __init__(self):
        self.calls = []
        self.memory = bytearray(11264)
        self.bad_ram = False
        self.bad_id = False
        self.short = False

    def execute(self, cdb, out=None, n=0):
        self.calls.append(bytes(cdb))
        op = int.from_bytes(cdb[:2], 'big')
        addr = int.from_bytes(cdb[2:6], 'big')
        if cdb == INQUIRY:
            return IDENTITY
        if op == 0xfb06:
            self.memory[addr-0x12000:addr-0x12000+len(out)] = out
            return b''
        if op == 0xfd07:
            data = bytes(self.memory[addr-0x12000:addr-0x12000+n])
            return bytes(n) if self.bad_ram else data
        if op == 0xfd05:
            return bytes(range(255 if self.short else 256))
        values = {0xfc0a: bytes.fromhex('03001371cd00'), 0xfc0b: bytes.fromhex('00cd72' if self.bad_id else '00cd71'), 0xfc14: bytes.fromhex('00008000')}
        return (op.to_bytes(2, 'big')+values.get(op, b'')).ljust(16, b'\0')


class BackupTests(unittest.TestCase):
    def test_unknown_identity_never_uploads(self):
        link = FakeLink()
        with self.assertRaisesRegex(RuntimeError, 'Unsupported bootloader'):
            Transport(link).prepare(IDENTITY.replace(b'BR23', b'BR25'), LOADER)
        self.assertEqual(link.calls, [])

    def test_gamebrick_identity_rejected(self):
        link = FakeLink()
        with self.assertRaisesRegex(RuntimeError, 'Unsupported bootloader'):
            Transport(link).prepare(IDENTITY.replace(b'BR23', b'BD19'), LOADER)
        self.assertEqual(link.calls, [])

    def test_wrong_loader_never_uploads(self):
        link = FakeLink()
        with self.assertRaisesRegex(RuntimeError, 'Loader hash mismatch'):
            Transport(link).prepare(IDENTITY, bytes(len(LOADER)))
        self.assertEqual(link.calls, [])

    def test_identity_gate(self):
        link = FakeLink()
        t = Transport(link)
        with self.assertRaises(RuntimeError):
            t.reply(0xfc0a)
        self.assertEqual(link.calls, [])

    def test_ram_mismatch_never_executes(self):
        link = FakeLink()
        link.bad_ram = True
        with self.assertRaisesRegex(RuntimeError, 'RAM readback mismatch'):
            Transport(link).prepare(IDENTITY, LOADER)
        self.assertNotIn(0xfb08, [int.from_bytes(x[:2], 'big') for x in link.calls])

    def test_early_jump_rejected(self):
        link = FakeLink()
        t = Transport(link)
        t.loader = LOADER
        with self.assertRaisesRegex(RuntimeError, 'not fully verified'):
            t.reply(0xfb08, bytes.fromhex('000120000001'))
        self.assertEqual(link.calls, [])

    def test_flash_identity_mismatch(self):
        link = FakeLink()
        link.bad_id = True
        t = Transport(link)
        with self.assertRaisesRegex(RuntimeError, 'identity replies disagree'):
            t.prepare(IDENTITY, LOADER)
        self.assertIsNone(t.size)

    def test_never_programs_flash_or_fuses(self):
        link = FakeLink()
        t = Transport(link)
        t.prepare(IDENTITY, LOADER)
        before = len(link.calls)
        for op in (0xfb01, 0xfb02, 0xfb03, 0xfb04, 0xfc09, 0xfc15, 0xfc16, 0xffff):
            with self.subTest(op=op), self.assertRaises(RuntimeError):
                t.command(op)
        self.assertEqual(len(link.calls), before)

    def test_capacity_and_read_bounds(self):
        t = Transport(FakeLink())
        self.assertEqual(t.prepare(IDENTITY, LOADER)['size'], 524288)
        for addr, length in [(0x80000, 256), (1, 256), (0, 512)]:
            with self.subTest(addr=addr, length=length), self.assertRaises(RuntimeError):
                t.command(0xfd05, struct.pack('>IH', addr, length), n=length)

    def test_short_read_rejected(self):
        link = FakeLink()
        t = Transport(link)
        t.prepare(IDENTITY, LOADER)
        link.short = True
        with self.assertRaisesRegex(RuntimeError, 'Short reply'):
            t.command(0xfd05, struct.pack('>IH', 0, 256), n=256)

    def test_two_matching_reads_saved_readonly(self):
        t = Transport(FakeLink())
        t.prepare(IDENTITY, LOADER)
        t.size = 512
        with tempfile.TemporaryDirectory() as temp:
            result = capture(t, Path(temp))
            self.assertTrue(result['passes_match'])
            for name in ('flash-pass1.bin', 'flash-pass2.bin'):
                p = Path(temp)/name
                self.assertEqual(p.stat().st_mode & 0o222, 0)
                self.assertEqual(p.read_bytes(), bytes(range(256))*2)

    def test_unstable_reads_rejected_and_retained(self):
        class Unstable:
            size = 256
            calls = 0
            def command(self, *a, **kw):
                self.calls += 1
                return bytes(range(256)) if self.calls == 1 else bytes(reversed(range(256)))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'Full reads differ'):
                capture(Unstable(), Path(temp))
            self.assertEqual(len(list(Path(temp).glob('flash-pass*.bin'))), 2)


if __name__ == '__main__':
    unittest.main()
