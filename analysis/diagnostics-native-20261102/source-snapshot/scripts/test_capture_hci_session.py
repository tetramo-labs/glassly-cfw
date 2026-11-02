import tempfile,unittest
from pathlib import Path
from capture_hci_session import recover_rotated_tail

HEADER=b'btsnoop\0'+bytes.fromhex('00000001000003ea')
class HciRotationTests(unittest.TestCase):
    def test_archive_extends_exact_owned_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'segment';previous=HEADER+b'previous-records';p.write_bytes(previous)
            tail=b'last-record-tail';self.assertEqual(recover_rotated_tail(previous,p,previous+tail),len(tail))
            self.assertEqual(p.read_bytes(),previous+tail)
    def test_equal_archive_has_no_duplicate_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'segment';previous=HEADER+b'previous';p.write_bytes(previous)
            self.assertEqual(recover_rotated_tail(previous,p,previous),0);self.assertEqual(p.read_bytes(),previous)
    def test_second_rotation_short_or_different_archive_never_spliced(self):
        previous=HEADER+b'old-records'
        for archived in (HEADER+b'new-records',previous[:-1],b'',b'not-snoop'+previous):
            with tempfile.TemporaryDirectory() as directory:
                p=Path(directory)/'segment';p.write_bytes(previous)
                with self.assertRaises(ValueError):recover_rotated_tail(previous,p,archived)
                self.assertEqual(p.read_bytes(),previous)
    def test_local_drift_and_bad_prior_header_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'segment';previous=HEADER+b'prior';p.write_bytes(previous+b'drift')
            with self.assertRaises(ValueError):recover_rotated_tail(previous,p,previous+b'tail')
            self.assertEqual(p.read_bytes(),previous+b'drift')
            for previous in (b'',HEADER[:8],b'x'*32):
                p.write_bytes(previous)
                with self.assertRaises(ValueError):recover_rotated_tail(previous,p,previous+b'tail')
                self.assertEqual(p.read_bytes(),previous)

if __name__=='__main__':unittest.main()
