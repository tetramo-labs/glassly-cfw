import contextlib, io, unittest
from flash_stock import Transport

BD19 = b'\0' * 8 + b'BD19    ' + b'UBOOT1.00       ' + b'1.00'


class LoaderLink:
    """Answers like the BD19 ROM and RAM loader, reporting the given flash ID."""
    def __init__(self, flash_id):
        self.flash_id = flash_id; self.read_id = (flash_id >> 8).to_bytes(3, 'big'); self.ram = bytearray(23040); self.ops = []
    def execute(self, cdb, out=None, n=0):
        op = int.from_bytes(cdb[:2], 'big'); addr = int.from_bytes(cdb[2:6], 'big'); self.ops.append(op)
        if cdb[:1] == b'\x12': return BD19
        if op == 0xfb06: self.ram[addr-0x2000:addr-0x2000+len(out)] = out; return b''
        if op == 0xfd07: return bytes(self.ram[addr-0x2000:addr-0x2000+n])
        replies = {0xfc0a: bytes([3, 0]) + self.flash_id.to_bytes(4, 'little'),
                   0xfc0b: self.read_id, 0xfc14: bytes.fromhex('00000100')}
        return (cdb[:2] + replies.get(op, b'')).ljust(n, b'\0')


class FlashIdentityTests(unittest.TestCase):
    def initialize(self, flash_id):
        link = LoaderLink(flash_id)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            try:
                Transport(link, []).initialize()
            finally:
                self.output = out.getvalue()
        return link

    def test_both_known_flash_parts_are_accepted_and_reported(self):
        for flash_id in (0xcd7113, 0xcd7013):
            self.initialize(flash_id)
            self.assertIn(f'flash ID {flash_id:#08x}', self.output)

    def test_disagreeing_read_id_is_refused(self):
        link = LoaderLink(0xcd7013)
        link.read_id = bytes.fromhex('00cd71')
        with self.assertRaisesRegex(RuntimeError, 'Flash ID responses disagree'):
            with contextlib.redirect_stdout(io.StringIO()):
                Transport(link, []).initialize()

    def test_other_flash_is_refused_with_its_identity(self):
        with self.assertRaisesRegex(RuntimeError, r'flash ID 0x0b4013.*read-ID 000b40.*Nothing was written'):
            self.initialize(0x0b4013)
        self.assertIn('Loader reports device type 0x03, flash ID 0x0b4013', self.output)


if __name__ == '__main__':
    unittest.main()
