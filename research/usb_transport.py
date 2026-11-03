"""macOS IOUSBHost/Bulk-Only transport, adapted from the Gamebrick project.
All backup commands pass through backup_controller.Transport first.
"""
import ctypes, os, signal, struct, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent

class LinkError(RuntimeError):
    pass

class NativeLink:
    """macOS: Bulk-Only Transport over the IOUSBHost helper."""
    def __init__(self, native):
        self.native = native; self.tag = 0; self.opened = False
        self.last_command = None
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
        self.tag += 1
        size = len(out) if out is not None else n
        cbw = struct.pack('<4sIIBBB16s', b'USBC', self.tag, size, 0x80 if n else 0, 0, len(cdb), bytes(cdb).ljust(16, b'\0'))
        self.last_command = dict(cdb=bytes(cdb).hex(), cbw=cbw.hex(), tag=self.tag,
                                 direction='out' if out is not None else 'in', size=size,
                                 stage='command', complete=False)
        self.transfer(1, cbw)
        data = b''
        self.last_command['stage'] = 'data'
        if out is not None:
            self.transfer(1, out)
        elif n:
            data = self.transfer(0x81, n)
        self.last_command['stage'] = 'status'
        csw = self.transfer(0x81, 13)
        signature, tag, residue, status = struct.unpack('<4sIIB', csw)
        self.last_command.update(csw=csw.hex(), signature=signature.hex(),
                                 returned_tag=tag, residue=residue, status=status)
        if (signature, tag, residue, status) != (b'USBS', self.tag, 0, 0):
            raise LinkError(f'Failed USB command status: cdb={bytes(cdb).hex()} '
                            f'csw={csw.hex()} signature={signature!r} '
                            f'tag={tag}/{self.tag} residue={residue}/{size} status={status}')
        self.last_command.update(stage='complete', complete=True)
        return data
