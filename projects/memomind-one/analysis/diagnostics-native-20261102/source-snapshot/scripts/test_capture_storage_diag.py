import unittest
from capture_memomind_storage_diag import acquire
from test_memomind_storage_diag import topology,badmap

class Client:
    def __init__(self):self.calls=[];self.header=bytes(range(256));self.map=badmap()
    def query(self):self.calls.append('query');return {'profile':'fixture'}
    def read(self,*args):assert args==(0,0x1eb000,256);self.calls.append('header');return self.header
    def topology(self):self.calls.append('topology');return {**topology(),'consistent':1}
    def badmap(self):self.calls.append('badmap');return self.map

class CaptureDiagnosticsTests(unittest.TestCase):
    def test_candidate_match_then_explicit_queries(self):
        c=Client();r,h=acquire(c,c.header);self.assertEqual(h,c.header)
        self.assertEqual(c.calls,['query','header','topology','badmap','topology'])
        self.assertEqual(r['effective_tail_usable_sectors'],254)
        self.assertTrue(r['topology_unchanged'] and r['both_samples_consistent'] and r['physical_badmap_record_acquired'])
        self.assertFalse(r['reservation_established']);self.assertEqual(r['flash_mutations'],0)
    def test_bad_header_stops_before_diagnostics(self):
        c=Client()
        with self.assertRaises(ValueError):acquire(c,bytes(256))
        self.assertEqual(c.calls,['query','header'])
        for expected in (b'',bytes(31),bytes(33),bytearray(32)):
            c=Client()
            with self.assertRaises(ValueError):acquire(c,expected)
            self.assertFalse(c.calls)
    def test_native_default_not_claimed_as_persisted(self):
        c=Client();c.map.update(recordState='absent',kvStatus=7,actualLength=0,recordHex='',mapHex='00'*96)
        r,_=acquire(c,c.header[:32]);self.assertFalse(r['physical_badmap_record_acquired'])
        self.assertEqual(r['map_source'],'native-defined-absent-default');self.assertEqual(r['effective_tail_usable_sectors'],256)

if __name__=='__main__':unittest.main()
