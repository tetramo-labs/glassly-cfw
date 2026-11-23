import unittest
import zlib

from decode_memomind import OtaStream, encode_chunk, encode_ota, encode_control


class OtaCodecTests(unittest.TestCase):
    # Captured frame 1678, full e2 request with sequence 3 and 18-byte file ID.
    CHECK_IMAGE = bytes.fromhex("70076ec0e20013034d4502011001002159cf0000000007c720bd33")

    def test_captured_handshake_roundtrip(self):
        image_id = bytes.fromhex("4d4502011001002159cf0000000007c720bd")
        self.assertEqual(encode_ota(0xe2, 3, image_id), self.CHECK_IMAGE)

    def test_captured_pre_ota_notification(self):
        self.assertEqual(encode_control(0x15, 1, 0x1c, bytes.fromhex("0800000101")),
                         bytes.fromhex("fa00000e15011c08000001010144"))

    def test_arbitrary_transport_split(self):
        for split in range(1, len(self.CHECK_IMAGE)):
            parser = OtaStream()
            self.assertEqual(parser.feed(self.CHECK_IMAGE[:split]), [])
            self.assertEqual(parser.feed(self.CHECK_IMAGE[split:]), [self.CHECK_IMAGE])
            self.assertEqual(parser.buffer, b"")

    def test_coalesced_messages(self):
        parser = OtaStream()
        self.assertEqual(parser.feed(self.CHECK_IMAGE * 2), [self.CHECK_IMAGE] * 2)

    def test_bad_footer_rejected(self):
        with self.assertRaises(ValueError):
            OtaStream().feed(self.CHECK_IMAGE[:-1] + b"\x00")

    def test_unknown_prefix_rejected(self):
        with self.assertRaises(ValueError):
            OtaStream().feed(b"garbage" + self.CHECK_IMAGE)

    def test_chunk_crc_and_offset_encoding(self):
        frame = encode_chunk(7, 0x123456, b"123456789")
        self.assertEqual(frame[8:12], b"\x00\x12\x34\x56")
        self.assertEqual(frame[-5:-1], bytes.fromhex("cbf43926"))
        self.assertEqual(zlib.crc32(frame[12:-5]), 0xcbf43926)

    def test_oversized_chunk_rejected(self):
        with self.assertRaises(ValueError):
            encode_chunk(1, 0, b"x" * 631)


if __name__ == "__main__":
    unittest.main()
