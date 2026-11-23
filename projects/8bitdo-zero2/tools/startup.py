"""Reconstruct pinned Zero 2 v1.08 Yichip initialized data, without execution.

Derived from the Thumb scatter loader at 0x01018364, unpacker 0x010183ca,
and zero initializer 0x01023342. This is not a generic ARM scatter parser.
"""
import struct

BASE = 0x01018000


def unpack_data(source, output_size):
    """Decode literal/zero/backreference runs; return bytes and input consumed."""
    if output_size < 0 or output_size > 0x10000:
        raise ValueError('Invalid initialized-data size')
    pos, out = 0, bytearray()

    def take():
        nonlocal pos
        if pos >= len(source):
            raise ValueError('Truncated initialized-data stream')
        value = source[pos]
        pos += 1
        return value

    def emit(value):
        if len(out) >= output_size:
            raise ValueError('Initialized-data run exceeds destination')
        out.append(value)

    while len(out) < output_size:
        code = take()
        literal = (code & 7) or take()
        length = (code >> 4) or take()
        if literal == 0:
            raise ValueError('Zero literal count would underflow stock loop')
        for _ in range(literal - 1):
            emit(take())
        if code & 8:
            distance = take()
            if distance == 0 or distance > len(out):
                raise ValueError('Backreference outside initialized output')
            for _ in range(length + 2):
                emit(out[-distance])
        else:
            for _ in range(length):
                emit(0)
    return bytes(out), pos


def reconstruct(data):
    """Return scatter records and reconstructed RAM regions for this exact layout."""
    if len(data) < 0x11c04:
        raise ValueError('Truncated Yichip section')
    records = [dict(zip(('source', 'destination', 'size', 'initializer'),
                       struct.unpack_from('<4I', data, off)))
               for off in (0x1182c, 0x1183c)]
    expected = [
        dict(source=0x0102984c, destination=0x20000, size=0x78c, initializer=0x010183ca),
        dict(source=0x01029c04, destination=0x2078c, size=0x238c, initializer=0x01023342),
    ]
    if records != expected:
        raise ValueError('Unsupported scatter layout; audit before using')
    initialized, consumed = unpack_data(data[0x1184c:0x11c04], 0x78c)
    return records, {0x20000: initialized, 0x2078c: bytes(0x238c)}, consumed
