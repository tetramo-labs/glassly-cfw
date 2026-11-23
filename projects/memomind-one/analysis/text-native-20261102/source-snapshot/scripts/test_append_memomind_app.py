"""Offline fixture tests; constructed images remain in memory."""
import hashlib
from pathlib import Path
import struct
import unittest
import zlib

from append_memomind_app import ALLOWED_SOURCES, append_app
from memomind_ota import repack, sha, unpack_ota

ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "captures/firmware/ota-1.0.3.127-jhv3_release.bin"
TEXT = ROOT / "captures/firmware/ota-1.0.3.127-glassly-text.bin"


@unittest.skipUnless(STOCK.exists() and TEXT.exists(), "Both captured and verified OTA fixtures required")
class AppAppendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = [STOCK.read_bytes(), TEXT.read_bytes()]
        for source in cls.sources:
            if sha(source) not in ALLOWED_SOURCES:
                raise ValueError("Fixture differs from pinned source")

    def build(self, payload, source=None, **kwargs):
        source = self.sources[0] if source is None else source
        return append_app(source, payload, expected_source_sha256=sha(source), **kwargs)

    def test_both_source_profiles_preserve_every_original_body_byte(self):
        payload = b"\x01\x00" * 8 + b"GLASSLY-OFFLINE-APPEND\0"
        for source in self.sources:
            with self.subTest(source=sha(source)):
                output, audit = self.build(payload, source, alignment=4096)
                _, old = unpack_ota(source)
                _, new = unpack_ota(output)
                body = old[3]["raw"][32:]
                start = audit["append"]["payload_body_start"]
                self.assertEqual(new[3]["raw"][32:32+len(body)], body)
                self.assertEqual(new[3]["raw"][32+len(body):32+start], bytes(start-len(body)))
                self.assertEqual(new[3]["raw"][32+start:], payload)
                self.assertEqual(audit["mapping"]["payload_xip_start"] % 4096, 0)
                self.assertEqual(audit["mapping"]["payload_flash_start"] + 0x4000000,
                                 audit["mapping"]["payload_xip_start"])
                self.assertFalse(audit["mapping"]["elf_load_map_established"])
                self.assertEqual(audit["append"]["payload_sha256"], sha(payload))
                for i in (1, 2, 4, 5, 6):
                    self.assertEqual(old[i]["raw"], new[i]["raw"])
                    self.assertEqual(old[i]["packed"], new[i]["packed"])
                self.assertEqual(old[3]["raw"][:4], new[3]["raw"][:4])
                self.assertEqual(old[3]["raw"][8:16], new[3]["raw"][8:16])
                self.assertEqual(old[3]["raw"][20:32], new[3]["raw"][20:32])
                self.assertEqual(old[0]["raw"][:76], new[0]["raw"][:76])
                self.assertEqual(old[0]["raw"][80:], new[0]["raw"][80:])
                self.assertEqual(struct.unpack_from("<I", new[0]["raw"], 76)[0],
                                 len(new[3]["raw"])-32)
                # Independently reproduce the native bit-count/table/stream bounds.
                count = struct.unpack_from("<I", output, 26)[0].bit_count()
                self.assertEqual(count, 7)
                table_size = count * 16
                self.assertEqual(zlib.crc32(output[34:34+table_size]),
                                 struct.unpack_from("<I", output, 34+table_size)[0])
                packed_total = sum(struct.unpack_from("<I", output, 38+i*16)[0]
                                   for i in range(count))
                self.assertEqual(16+table_size+4+packed_total+4, len(output)-18)
                self.assertEqual(zlib.crc32(output[150:-4]), struct.unpack_from("<I", output, len(output)-4)[0])
                self.assertEqual(zlib.crc32(output[18:]), struct.unpack_from(">I", output, 14)[0])

    def test_empty_append_and_existing_repack_remain_exact_noops(self):
        for source in self.sources:
            output, audit = self.build(b"", source, alignment=4096)
            self.assertEqual(output, source)
            self.assertTrue(audit["byte_identical_noop"])
            self.assertEqual(audit["append"]["padding_bytes"], 0)
            self.assertEqual(repack(source, {}), source)

    def test_existing_same_length_repack_composes_after_append(self):
        output, audit = self.build(b"APPEND-COMPOSITION\0", self.sources[1], alignment=16)
        _, before = unpack_ota(output)
        body = bytearray(before[3]["raw"][32:])
        # Purely synthetic in-memory edit; it is not an executable hook.
        body[0] ^= 1
        final = repack(output, {3: bytes(body)})
        _, after = unpack_ota(final)
        self.assertEqual(after[3]["raw"][32:], body)
        self.assertEqual(after[3]["raw"][33:], before[3]["raw"][33:])
        self.assertEqual(after[0]["packed"], before[0]["packed"])
        self.assertEqual(after[3]["raw"][32+audit["append"]["payload_body_start"]:],
                         b"APPEND-COMPOSITION\0")

    def test_app_exact_end_and_one_byte_overflow(self):
        _, streams = unpack_ota(self.sources[0])
        spare = 0x200000-len(streams[3]["raw"])
        output, audit = self.build(bytes(spare))
        self.assertEqual(audit["bounds"]["app_free_bytes"], 0)
        self.assertEqual(audit["mapping"]["payload_flash_end_exclusive"], 0x3eb000)
        self.assertEqual(audit["mapping"]["payload_xip_end_exclusive"], 0x043eb000)
        self.assertEqual(unpack_ota(output)[1][3]["info"]["unpacked_size"], 0x200000)
        with self.assertRaisesRegex(ValueError, "application allocation"):
            self.build(bytes(spare+1))
        with self.assertRaisesRegex(ValueError, "application allocation"):
            self.build(bytes(spare), alignment=4096)

    def test_incompressible_tail_can_fail_staging_even_when_app_fits(self):
        _, streams = unpack_ota(self.sources[0])
        spare = 0x200000-len(streams[3]["raw"])
        payload = b"".join(hashlib.sha256(i.to_bytes(4, "little")).digest()
                           for i in range((spare+31)//32))[:spare]
        self.assertEqual(len(payload)+len(streams[3]["raw"]), 0x200000)
        with self.assertRaisesRegex(ValueError, "staging allocation"):
            self.build(payload)

    def test_exact_source_and_output_hashes_required(self):
        with self.assertRaisesRegex(ValueError, "Source SHA-256 mismatch"):
            append_app(self.sources[0], b"test", expected_source_sha256="0"*64)
        changed = self.sources[0]+b"\0"
        with self.assertRaisesRegex(ValueError, "not a pinned"):
            append_app(changed, b"test", expected_source_sha256=sha(changed))
        with self.assertRaisesRegex(ValueError, "Output SHA-256 mismatch"):
            self.build(b"test", expected_output_sha256="0"*64)
        output, _ = self.build(b"test")
        self.assertEqual(self.build(b"test", expected_output_sha256=sha(output))[0], output)

    def test_invalid_alignment_and_payload_type(self):
        for alignment in (0, -1, 3, 8192, True, 4.0):
            with self.subTest(alignment=alignment), self.assertRaisesRegex(ValueError, "Alignment"):
                self.build(b"test", alignment=alignment)
        with self.assertRaisesRegex(ValueError, "Payload must be bytes"):
            self.build("text")


if __name__ == "__main__":
    unittest.main()
