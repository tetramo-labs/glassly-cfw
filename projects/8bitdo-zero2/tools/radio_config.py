"""Decode the configuration format consumed by v1.08's 0x010233b8 loader.

The first block is microcode, subsequent blocks are writes to 0xc0000+addr.
This is static evidence, not proof of the services exposed on a live unit.
"""
import struct
import uuid


def parse_script(data, offset):
    start = offset
    if offset < 0 or offset + 6 > len(data):
        raise ValueError("Truncated radio script")
    if data[offset:offset + 2] != b"\x00\x02":
        raise ValueError("Unknown radio script prefix")
    offset += 2
    records = []
    first = True
    while data[offset:offset + 2] == b"\xaa\x55":
        if offset + 4 > len(data):
            raise ValueError("Truncated radio record")
        size = struct.unpack_from("<H", data, offset + 2)[0]
        header_size = 4 if first else 6
        if not size or offset + header_size + size > len(data):
            raise ValueError("Invalid radio record size")
        address = None if first else 0xc0000 + struct.unpack_from("<H", data, offset + 4)[0]
        records.append(dict(offset=offset, address=address,
                            payload_offset=offset + header_size,
                            payload=data[offset + header_size:offset + header_size + size]))
        first = False
        offset += header_size + size
    if not records:
        raise ValueError("Missing radio microcode")
    return records, offset - start


def parse_attributes(data):
    """Radio format: handle LE16, UUID size u8, UUID, value size u8, value.

    This is NOT BTstack's independent length/flags/handle/UUID table format.
    """
    result, pos, previous = [], 0, 0
    while pos < len(data):
        if data[pos:] == b"\x00\x00":
            return result
        if pos + 3 > len(data):
            raise ValueError("Truncated attribute")
        handle, size = struct.unpack_from("<HB", data, pos)
        if handle <= previous or size not in (2, 16) or pos + 4 + size > len(data):
            raise ValueError("Invalid attribute header")
        previous = handle
        uid = data[pos + 3:pos + 3 + size]
        value_size = data[pos + 3 + size]
        end = pos + 4 + size + value_size
        if end > len(data):
            raise ValueError("Truncated attribute value")
        value = data[pos + 4 + size:end]
        result.append(dict(handle=handle,
                           uuid=f"{int.from_bytes(uid, 'little'):04X}" if size == 2
                                else str(uuid.UUID(bytes=uid[::-1])),
                           value_hex=value.hex(), offset=pos))
        pos = end
    raise ValueError("Missing attribute terminator")
