import unittest
from pathlib import Path
from build_memomind_reset_undo_trim import construct,RUNTIME_SHA
from build_memomind_dashboard_ram import GATES
from build_memomind_graphics import BODY_BASE,ENTRY
from memomind_ota import sha,unpack_ota
ROOT=Path(__file__).resolve().parents[1]
class ResetUndoConstructionTests(unittest.TestCase):
    def test_reproduction_gates_runtime_and_unchanged_components(self):
        source=(ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
        blob=(ROOT/'runtime/build/reset-undo-trim-003/graphics.bin').read_bytes()
        data,manifest,proof=construct(source,blob)
        self.assertEqual(data,(ROOT/'captures/firmware/reset-undo-trim-001/firmware.bin').read_bytes())
        _,streams=unpack_ota(data);_,old=unpack_ota(source);body=streams[3]['raw'][32:]
        self.assertEqual(sha(body[ENTRY-BODY_BASE:ENTRY-BODY_BASE+len(blob)]),RUNTIME_SHA)
        for address,_,after,_ in GATES:self.assertEqual(body[address-BODY_BASE:address-BODY_BASE+4],bytes.fromhex(after))
        for i in (1,2,4,5,6):self.assertEqual(streams[i]['packed'],old[i]['packed'])
        self.assertEqual(manifest['output_sha256'],sha(data));self.assertEqual(proof['output_bytes'],len(data))
    def test_changed_source_or_runtime_refused(self):
        source=(ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes();blob=(ROOT/'runtime/build/reset-undo-trim-003/graphics.bin').read_bytes()
        for source_,blob_ in [(source,blob[:-1]),(source,bytes([blob[0]^1])+blob[1:]),(source[:-1],blob)]:
            with self.assertRaises(ValueError):construct(source_,blob_)
if __name__=='__main__':unittest.main()
