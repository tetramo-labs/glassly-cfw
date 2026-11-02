import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from inspect_btsnoop import EPOCH_DELTA, inspect


class CaptureIntegrityTests(unittest.TestCase):
    def check_capture(self, body):
        data = b"btsnoop\0" + struct.pack(">II", 1, 1002) + body
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.btsnoop"
            path.write_bytes(data)
            result = inspect(path)
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["whole_session_coverage"], "unproven")
        return result

    def record(self, data, original=None, drops=0):
        return struct.pack(">IIIIQ", original if original is not None else len(data),
                           len(data), 0, drops, EPOCH_DELTA) + data

    def test_valid_acl_retains_handle_and_does_not_claim_complete_ota(self):
        # H4 ACL, handle 0x123/PB=2, four-byte L2CAP payload.
        result = self.check_capture(self.record(bytes.fromhex("022321040000000400")))
        self.assertTrue(result["record_integrity_ok"])
        self.assertEqual(result["acl_handles"], {"0x123": 1})

    def test_filtered_payload_fails_integrity(self):
        result = self.check_capture(self.record(bytes.fromhex("0223210400"), original=9))
        self.assertFalse(result["record_integrity_ok"])
        self.assertEqual(result["truncated_records"], 1)

    def test_copy_ending_mid_packet_fails_integrity(self):
        body = self.record(bytes.fromhex("022321040000000400"))[:-2]
        result = self.check_capture(body)
        self.assertFalse(result["record_integrity_ok"])
        self.assertEqual(result["issues"][0]["error"], "incomplete record payload")

    def test_drop_count_rejected(self):
        result = self.check_capture(self.record(bytes.fromhex("040e00"), drops=1))
        self.assertFalse(result["record_integrity_ok"])

    def test_acl_length_mismatch_rejected(self):
        result = self.check_capture(self.record(bytes.fromhex("022321050000000400")))
        self.assertFalse(result["record_integrity_ok"])

    def test_empty_capture_not_ready(self):
        self.assertFalse(self.check_capture(b"")["record_integrity_ok"])


if __name__ == "__main__":
    unittest.main()
