"""macOS IOUSBHost/Bulk-Only transport, adapted from the Gamebrick project.
All backup commands pass through backup_controller.Transport first.
"""
import binascii, ctypes, hashlib, os, signal, struct, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
BR23_INQUIRY = bytes.fromhex('0080020220000000425232332020202055424f4f54312e303020202020202020312e3030')
BR23_LOADER_SHA = '7384429e33ee1f340fbffe46aa928a0099c163e1374a40f6f9f27468a6f16ddf'
ROM_RAM_POLICY = 'br23-uboot100-pinned-ram-full-residue-v1'
ROM_JUMP_POLICY = 'br23-uboot100-verified-jump-full-residue-v1'
LOADER_QUERY_POLICY = 'br23-verified-loader-identity-query-full-residue-v1'
FLASH_READ_POLICY = 'br23-856014-bounded-flash-full-residue-v1'

class LinkError(RuntimeError):
    pass

class NativeLink:
    """macOS: Bulk-Only Transport over the IOUSBHost helper."""
    def __init__(self, native):
        self.native = native; self.tag = 0; self.opened = False
        self.last_command = None
        self.last_data = None
        self.rom_loader = None
        self.rom_verified = set()
        self.loader_queries_enabled = False
        self.loader_query_replies = {}
        self.flash_read_size = None
    def enable_br23_rom_ram(self, inquiry, loader):
        # Exact locally observed identity and pinned blob. See docs/evidence/br23-residue.json.
        if (inquiry != BR23_INQUIRY or len(loader) != 11264 or
                hashlib.sha256(loader).hexdigest() != BR23_LOADER_SHA):
            raise LinkError('BR23 ROM residue profile identity/loader mismatch')
        self.rom_loader = bytes(loader)
        self.rom_verified = set()
        self.loader_queries_enabled = False
        self.loader_query_replies = {}
        self.flash_read_size = None
    def enable_br23_flash_reads(self, size):
        self.flash_read_size = None
        replies = self.loader_query_replies
        if not (self.loader_queries_enabled and set(replies) == {0xfc0a, 0xfc0b, 0xfc14}):
            raise LinkError('Verified loader identity queries required before flash reads')
        online, fid, buf = (replies[op][2:] for op in (0xfc0a, 0xfc0b, 0xfc14))
        # Scope the observed full-residue quirk to this measured flash identity.
        if not (online[0] == 3 and int.from_bytes(online[2:6], 'little') == 0x856014 and
                fid[:3] == bytes.fromhex('008560') and
                int.from_bytes(buf[:4], 'big') == 0x8000 and size == 0x100000):
            raise LinkError('Unsupported BR23 flash read residue profile identity')
        self.flash_read_size = size
    def expected_residue(self, cdb, out, n):
        if self.flash_read_size is not None and cdb[:2] == b'\xfd\x05':
            address = int.from_bytes(cdb[2:6], 'big')
            if not (len(cdb) == 16 and out is None and n == 256 and address % 256 == 0 and
                    address + n <= self.flash_read_size and cdb[6:] == b'\x01\x00'+b'\xff'*8):
                raise LinkError('Invalid BR23 flash read bounds/framing')
            return 256
        if self.loader_queries_enabled and cdb[:2] in (b'\xfc\x0a', b'\xfc\x0b', b'\xfc\x14'):
            if not (len(cdb) == 16 and cdb[2:] == b'\xff'*14 and out is None and n == 16):
                raise LinkError('Invalid BR23 loader identity query')
            return 16
        if self.rom_loader is None:
            return 0
        op = int.from_bytes(cdb[:2], 'big')
        if op == 0xfb08:
            if not (cdb == bytes.fromhex('fb08000120000001') + b'\xff'*8 and
                    out is None and n == 16 and self.rom_verified == set(range(0, 11264, 512))):
                raise LinkError('BR23 jump requires the exact fully verified loader')
            # Observed tag-46 FB08 response has status zero and residue 16.
            # Retire the ROM policy before any post-jump loader commands.
            self.rom_loader = None
            self.rom_verified = set()
            return 16
        if op not in (0xfb06, 0xfd07):
            return 0
        address = int.from_bytes(cdb[2:6], 'big')
        offset = address - 0x12000
        if not (len(cdb) == 16 and 0 <= offset <= 11264 - 512 and offset % 512 == 0 and
                cdb[6:8] == b'\x02\x00'):
            raise LinkError('Invalid BR23 ROM RAM command')
        if op == 0xfb06:
            block = self.rom_loader[offset:offset + 512]
            if not (out == block and n == 0 and cdb[8:] == b'\0' +
                    binascii.crc_hqx(block, 0).to_bytes(2, 'little') + b'\xff' * 5):
                raise LinkError('Only pinned BR23 loader writes are covered')
            self.rom_verified.discard(offset)
        elif not (out is None and n == 512 and cdb[8:] == b'\xff' * 8):
            raise LinkError('Invalid BR23 ROM RAM read')
        # This ROM leaves the requested count in CSW for the evidenced FB06/FD07
        # path. Require exactly 512, not an arbitrary nonzero residue. Transport
        # must still compare every RAM block byte-for-byte before any execution.
        return 512
    @classmethod
    def load(cls):
        native = ctypes.CDLL(str(ROOT/'native-usb.dylib'))
        native.gb_error.restype = ctypes.c_char_p
        native.gb_transfer.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        return cls(native)
    def try_open(self):
        code = self.native.gb_open()
        if code == 0: self.opened = True; return True
        if code == -2: return False
        raise LinkError(self.native.gb_error().decode())
    def close(self):
        if self.opened: self.native.gb_close(); self.opened = False
    def transfer(self, ep, data_or_size):
        if ep == 1: data = bytes(data_or_size); buf = ctypes.create_string_buffer(data); size = len(data)
        else: size = data_or_size; buf = ctypes.create_string_buffer(size)
        count = self.native.gb_transfer(ep, buf, size, 10000)
        if count < 0: raise LinkError(self.native.gb_error().decode())
        if count != size: raise LinkError(f'Short USB transfer: {count}/{size}')
        return buf.raw[:count]
    def execute(self, cdb, out=None, n=0):
        residue_expected = self.expected_residue(bytes(cdb), out, n)
        self.tag += 1
        self.last_data = None
        size = len(out) if out is not None else n
        cbw = struct.pack('<4sIIBBB16s', b'USBC', self.tag, size, 0x80 if n else 0, 0, len(cdb), bytes(cdb).ljust(16, b'\0'))
        self.last_command = dict(cdb=bytes(cdb).hex(), cbw=cbw.hex(), tag=self.tag,
                                 direction='out' if out is not None else 'in', size=size,
                                 stage='command', complete=False, expected_residue=residue_expected,
                                 residue_policy=(ROM_RAM_POLICY if residue_expected == 512 else
                                                 FLASH_READ_POLICY if residue_expected == 256 else
                                                 ROM_JUMP_POLICY if residue_expected == 16 and bytes(cdb[:2]) == b'\xfb\x08' else
                                                 LOADER_QUERY_POLICY if residue_expected == 16 else 'standard-zero'))
        self.transfer(1, cbw)
        data = b''
        self.last_command['stage'] = 'data'
        if out is not None:
            self.transfer(1, out)
        elif n:
            data = self.transfer(0x81, n)
            # Preserve full data-in evidence even if the subsequent CSW is invalid.
            # This is not an accepted reply and must never bypass status validation.
            self.last_data = data
        self.last_command['stage'] = 'status'
        csw = self.transfer(0x81, 13)
        signature, tag, residue, status = struct.unpack('<4sIIB', csw)
        self.last_command.update(csw=csw.hex(), signature=signature.hex(),
                                 returned_tag=tag, residue=residue, status=status)
        if (signature, tag, residue, status) != (b'USBS', self.tag, residue_expected, 0):
            raise LinkError(f'Failed USB command status: cdb={bytes(cdb).hex()} '
                            f'csw={csw.hex()} signature={signature!r} '
                            f'tag={tag}/{self.tag} residue={residue}/{size} expected_residue={residue_expected} status={status}')
        if residue_expected == 512 and bytes(cdb[:2]) == b'\xfd\x07':
            offset = int.from_bytes(cdb[2:6], 'big') - 0x12000
            if data != self.rom_loader[offset:offset+512]:
                raise LinkError('RAM readback mismatch; stopping')
            self.rom_verified.add(offset)
        if residue_expected == 16:
            if data[:2] != bytes(cdb[:2]):
                raise LinkError('BR23 acknowledgement mismatch')
            if bytes(cdb[:2]) == b'\xfb\x08':
                # Enabled only after exact identity, all 22 RAM readbacks and
                # the successful pinned jump. FC0A's full residue was observed
                # on this unit; FC0B/FC14 use the same fixed-size query framing.
                # Flash reads require their own measured-identity/bounds gate.
                self.loader_queries_enabled = True
            elif self.loader_queries_enabled and int.from_bytes(cdb[:2], 'big') in (0xfc0a, 0xfc0b, 0xfc14):
                self.flash_read_size = None
                self.loader_query_replies[int.from_bytes(cdb[:2], 'big')] = data
        self.last_command.update(stage='complete', complete=True)
        return data


class PyUsbLink(NativeLink):
    """Windows/Linux raw BOT via libusb; shares every status/residue gate with macOS.

    The target is an explicit bus:address pair from list_usb_targets(). No reset,
    automatic mode switch, or SCSI disk scanning is performed.
    """
    def __init__(self, target):
        super().__init__(None)
        self.target = target
        self.device = None
        self.interface = None
        self.detached = False

    def try_open(self):
        import usb.core
        import usb.util
        devices = [d for d in usb.core.find(find_all=True, idVendor=0x4c4a, idProduct=0x2342)
                   if (d.bus, d.address) == self.target]
        if not devices:
            return False
        if len(devices) != 1:
            raise LinkError('Ambiguous USB target')
        self.device = devices[0]
        try:
            config = self.device.get_active_configuration()
            interfaces = [i for i in config if i.bAlternateSetting == 0 and
                          {(e.bEndpointAddress, e.bmAttributes & 3) for e in i} == {(1, 2), (0x81, 2)}]
            if config.bConfigurationValue != 1 or len(interfaces) != 1:
                raise LinkError('Unsupported BR23 USB configuration/endpoints')
            self.interface = interfaces[0].bInterfaceNumber
            if sys.platform.startswith('linux') and self.device.is_kernel_driver_active(self.interface):
                self.device.detach_kernel_driver(self.interface)
                self.detached = True
            usb.util.claim_interface(self.device, self.interface)
            self.opened = True
            return True
        except BaseException:
            self.close()
            raise

    def transfer(self, ep, data_or_size):
        if not self.opened or ep not in (1, 0x81):
            raise LinkError('USB interface not open or invalid endpoint')
        if ep == 1:
            data = bytes(data_or_size)
            count = self.device.write(ep, data, timeout=10000)
            if count != len(data):
                raise LinkError(f'Short USB transfer: {count}/{len(data)}')
            return data
        result = bytes(self.device.read(ep, data_or_size, timeout=10000))
        if len(result) != data_or_size:
            raise LinkError(f'Short USB transfer: {len(result)}/{data_or_size}')
        return result

    def close(self):
        import usb.util
        if self.device is not None:
            try:
                if self.opened:
                    usb.util.release_interface(self.device, self.interface)
            finally:
                try:
                    if self.detached:
                        self.device.attach_kernel_driver(self.interface)
                finally:
                    usb.util.dispose_resources(self.device)
                    self.opened = False
                    self.detached = False
                    self.device = None


def list_usb_targets():
    import usb.core
    return [dict(bus=d.bus, address=d.address, vid='4c4a', pid='2342')
            for d in usb.core.find(find_all=True, idVendor=0x4c4a, idProduct=0x2342)]
