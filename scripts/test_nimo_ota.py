import io
import json
import lzma
import os
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nimo_ota  # noqa: E402

FIRMWARE = Path(__file__).resolve().parents[1] / "captures" / "firmware"
IMAGES = {
    "ota-0.1.0.15-20260724160441-bd9806-mentros.bin": (
        "8eb058b4fd5bc467f33e3c257a7a744fb48484227854a8a2d09210ce7f173612", 4),
    "ota-0.1.1.1-20260827164351-537cf1-dirty-dynamic-v1.bin": (
        "5e23c574e3dfd8c27172f4f9a33475e6efd0d33e7230bfcce8f4fe8ca59fe433", 6),
}


def pack(raw):
    return nimo_ota.pack_stream(raw)


def component(body, load, flags=0x100):
    header = struct.pack("<8I", nimo_ota.IMAGE_MAGIC, len(body), flags, load,
                         zlib.crc32(body) & 0xffffffff, 0, 0, 0)
    return header + body


def synthetic(count):
    """A minimal container with `count` components and a 16-row partition map."""
    rows = []
    comps = []
    flash = 0x10000
    for i in range(count):
        body = bytes([i + 1]) * (64 + 16 * i)
        raw = component(body, 0x04000020 + flash)
        alloc = 0x1000
        rows.append((0x20 + i, flash, 0x04000020 + flash, len(body), alloc))
        comps.append((raw, flash, flash + alloc))
        flash += alloc
    while len(rows) < 16:
        rows.append((0xc0, flash, 0, 0, 0x1000))
        flash += 0x1000
    metadata = struct.pack("<6I", 0, 16, 0, 0, 0, 0)
    for row in rows:
        metadata += struct.pack("<5I", *row)
    packed_meta = pack(metadata)
    header = bytearray(b"\x00\x00\x02\x01\x10\x01" + bytes(12))
    header += struct.pack("<I", nimo_ota.INNER_MAGIC)
    header += struct.pack("<4I", 1, 0x1f, 0xffffffff, len(metadata))
    header += struct.pack("<I", len(packed_meta))
    header += struct.pack("<II", 2, 0)
    packed = [packed_meta]
    for raw, start, end in comps:
        p = pack(raw)
        packed.append(p)
        header += struct.pack("<IIII", len(raw), len(p), start, end)
    header += struct.pack("<I", zlib.crc32(header[0x22:]) & 0xffffffff)
    streams = b"".join(packed)
    data = bytearray(header + streams + struct.pack("<I", zlib.crc32(streams) & 0xffffffff))
    struct.pack_into(">I", data, 6, len(data) - 18)
    struct.pack_into(">I", data, 14, zlib.crc32(data[18:]) & 0xffffffff)
    return bytes(data)


class SyntheticContainerTests(unittest.TestCase):
    def test_component_count_is_derived(self):
        for count in (1, 4, 6, 9):
            report, streams = nimo_ota.unpack_ota(synthetic(count))
            self.assertEqual(report["component_count"], count)
            self.assertEqual(len(streams), count + 1)
            self.assertEqual(report["stream_start"], 0x32 + 16 * count + 4)

    def test_unchanged_repack_is_identical(self):
        data = synthetic(4)
        self.assertEqual(nimo_ota.repack(data, {}), data)

    def test_same_length_body_replacement_updates_every_checksum(self):
        data = synthetic(3)
        _, streams = nimo_ota.unpack_ota(data)
        body = bytes(len(streams[2]["raw"]) - 32)
        result = nimo_ota.repack(data, {2: body})
        report, rebuilt = nimo_ota.unpack_ota(result)
        self.assertEqual(rebuilt[2]["raw"][32:], body)
        self.assertEqual(rebuilt[1]["packed"], streams[1]["packed"])
        self.assertEqual(rebuilt[3]["packed"], streams[3]["packed"])
        self.assertEqual(report["component_count"], 3)

    def test_rejects_wrong_length_replacement(self):
        with self.assertRaises(ValueError):
            nimo_ota.repack(synthetic(2), {1: b"short"})

    def test_rejects_corruption(self):
        data = bytearray(synthetic(2))
        data[-10] ^= 0xff
        with self.assertRaises((ValueError, lzma.LZMAError)):
            nimo_ota.unpack_ota(bytes(data))
        data = bytearray(synthetic(2))
        data[0x40] ^= 0x01  # a component table row
        with self.assertRaises(ValueError):
            nimo_ota.unpack_ota(bytes(data))


class VendorImageTests(unittest.TestCase):
    def test_vendor_images_parse_and_repack_identically(self):
        seen = 0
        for name, (digest, count) in IMAGES.items():
            path = FIRMWARE / name
            if not path.exists():
                continue
            seen += 1
            data = path.read_bytes()
            self.assertEqual(nimo_ota.sha(data), digest)
            report, streams = nimo_ota.unpack_ota(data)
            self.assertEqual(report["component_count"], count)
            self.assertEqual(report["metadata_header_words"][1], 16)
            self.assertEqual(nimo_ota.repack(data, {}), data)
            app = [s for s in streams[1:] if s["info"]["partition_type"] == 0x20]
            self.assertEqual(len(app), 1)
            self.assertEqual(app[0]["raw"][32:40], bytes.fromhex("a14273b002309302"))
        if seen == 0:
            self.skipTest("vendor images are not present under captures/firmware")


if __name__ == "__main__":
    unittest.main()
