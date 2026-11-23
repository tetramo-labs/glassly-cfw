"""Regression checks against the captured stock OTA, never against a device."""
from pathlib import Path
import unittest

from memomind_ota import repack, sha, unpack_ota

FIXTURE = Path(__file__).resolve().parents[1] / "captures/firmware/ota-1.0.3.127-jhv3_release.bin"
EXPECTED = "08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712"


@unittest.skipUnless(FIXTURE.is_file(), "Captured stock OTA is required")
class StockOtaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = FIXTURE.read_bytes()
        if sha(cls.data) != EXPECTED:
            raise ValueError("Unexpected stock fixture; do not silently change the test base")

    def test_all_components_and_partition_membership(self):
        report, streams = unpack_ota(self.data)
        self.assertEqual([len(s["raw"]) for s in streams],
                         [344, 909676, 695512, 1773208, 284300, 3616, 81594])
        self.assertEqual([s["info"]["partition_type"] for s in streams[1:]],
                         [0x30, 0x70, 0x20, 0x90, 0xc2, 0xc5])
        self.assertEqual(report["unaccounted_bytes"], 0)

    def test_unchanged_repack_is_byte_identical(self):
        self.assertEqual(repack(self.data, {}), self.data)

    def test_same_length_body_change_updates_every_checksum(self):
        _, original = unpack_ota(self.data)
        body = bytearray(original[4]["raw"][32:])
        body[0] ^= 1
        changed = repack(self.data, {4: bytes(body)})
        report, decoded = unpack_ota(changed)
        self.assertEqual(decoded[4]["raw"][32:], body)
        for i in (0, 1, 2, 3, 5, 6):
            self.assertEqual(decoded[i]["packed"], original[i]["packed"])
        self.assertEqual(report["checksums"]["component_body_crc32"], "verified-all-six")

    def test_corruption_and_truncation_rejected(self):
        changed = bytearray(self.data)
        changed[0x200] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC32 mismatch"):
            unpack_ota(changed)
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            unpack_ota(self.data[:-1])

    def test_resize_rejected(self):
        with self.assertRaisesRegex(ValueError, "same-length"):
            repack(self.data, {3: b""})


if __name__ == "__main__":
    unittest.main()
