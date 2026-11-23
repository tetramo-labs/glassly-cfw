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
import build_cfw  # noqa: E402
import nimo_ota  # noqa: E402

FIRMWARE = Path(__file__).resolve().parents[1] / "captures" / "firmware"
IMAGES = {
    "ota-0.1.0.15-20260724160441-bd9806-mentros.bin": (
        "8eb058b4fd5bc467f33e3c257a7a744fb48484227854a8a2d09210ce7f173612", 4),
    "ota-0.1.1.1-20260827164351-537cf1-dirty-dynamic-v1.bin": (
        "5e23c574e3dfd8c27172f4f9a33475e6efd0d33e7230bfcce8f4fe8ca59fe433", 6),
    # Rebuilt from the vendor app's 2026-11-09 OTA capture; metadata is row 3.
    "ota-1.1.5.1-20261027111705-8e6f7a-vendor-app.bin": (
        "baa41550d8af80b48a623c0b8bf006664804e83acee6520305bd9f4f341636bf", 6),
}


def pack(raw):
    return nimo_ota.pack_stream(raw)


def component(body, load, flags=0x100):
    header = struct.pack("<8I", nimo_ota.IMAGE_MAGIC, len(body), flags, load,
                         zlib.crc32(body) & 0xffffffff, 0, 0, 0)
    return header + body


def synthetic(count, meta_row=0):
    """A minimal container with `count` components and a 16-row partition map,
    the metadata stream at table row `meta_row`."""
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
    header += struct.pack("<3I", 1, 0x1f, 0xffffffff)
    table = [(metadata, packed_meta, 2, 0)] + [(raw, pack(raw), start, end) for raw, start, end in comps]
    table.insert(meta_row, table.pop(0))
    packed = []
    for raw, p, start, end in table:
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

    def test_metadata_row_may_follow_components(self):
        data = synthetic(4, meta_row=3)
        report, streams = nimo_ota.unpack_ota(data)
        self.assertEqual(report["metadata_row"], 3)
        self.assertTrue(streams[3]["info"]["metadata"])
        self.assertEqual(nimo_ota.repack(data, {}), data)
        body = bytes(len(streams[4]["raw"]) - 32)
        _, rebuilt = nimo_ota.unpack_ota(nimo_ota.repack(data, {4: body}))
        self.assertEqual(rebuilt[4]["raw"][32:], body)
        with self.assertRaises(ValueError):
            nimo_ota.repack(data, {3: bytes(10)})

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

    def test_replace_body_grows_a_component_and_its_partition_row(self):
        for meta_row in (0, 2):
            data = synthetic(3, meta_row=meta_row)
            report, streams = nimo_ota.unpack_ota(data)
            index = 1 if meta_row else 2
            body = streams[index]["raw"][32:] + b"\x13" * 100
            result = nimo_ota.replace_body(data, index, body)
            rebuilt_report, rebuilt = nimo_ota.unpack_ota(result)
            self.assertEqual(rebuilt[index]["raw"][32:], body)
            part = rebuilt[index]["info"]["partition_index"]
            self.assertEqual(rebuilt_report["partitions"][part]["body_size"], len(body))
            others = [i for i in range(len(streams)) if i not in (index, meta_row)]
            for i in others:
                self.assertEqual(rebuilt[i]["packed"], streams[i]["packed"])
            with self.assertRaises(ValueError):
                nimo_ota.replace_body(data, index, bytes(0x2000))

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
            app = [s for s in streams if s["info"].get("partition_type") == 0x20]
            self.assertEqual(len(app), 1)
            self.assertEqual(app[0]["raw"][32:40], bytes.fromhex("a14273b002309302"))
        if seen == 0:
            self.skipTest("vendor images are not present under captures/firmware")


class BuildCfwTests(unittest.TestCase):
    def test_edits_require_the_original_string(self):
        body = b"xxPhone\0yy"
        edit = {"offset": "2", "old": "Phone", "new": "Gla"}
        self.assertEqual(build_cfw.apply_edits(body, [edit]), b"xxGla\0\0\0yy")
        with self.assertRaises(ValueError):
            build_cfw.apply_edits(body, [dict(edit, old="Phon")])
        with self.assertRaises(ValueError):
            build_cfw.apply_edits(body, [dict(edit, new="Glassly")])

    def test_glasslycfw_1_builds_from_the_vendor_images(self):
        expected = {
            "0.1.1.1": ("3c2be1c5a5f306814fa408eae42b3f0b49c0a84bedaa1c86036c5181268b16cf",
                        b"FW-VERSION-v0.1.1.1-20260827164351-GLASSLYCFW/1-Debug\0"),
            "1.1.5.1": (None, b"FW-VERSION-v1.1.5.1-20261027111705-GLASSLYCFW/1\0"),
        }
        built = 0
        for base, (digest, tag) in expected.items():
            manifest = json.loads((Path(__file__).resolve().parent.parent
                                   / f"patches/glasslycfw-1/{base}.json").read_text())
            path = FIRMWARE / manifest["source"]["file"]
            if not path.exists():
                continue
            built += 1
            image, verification = build_cfw.build(path.read_bytes(), manifest)
            if digest:
                self.assertEqual(verification["output_sha256"], digest)
            _, streams = nimo_ota.unpack_ota(image)
            app = [s for s in streams if s["info"].get("partition_type") == 0x20][0]
            self.assertIn(tag, app["raw"])
            self.assertIn(b"Glassly CFW running\0", app["raw"])
        if built == 0:
            self.skipTest("vendor images are not present under captures/firmware")


if __name__ == "__main__":
    unittest.main()
