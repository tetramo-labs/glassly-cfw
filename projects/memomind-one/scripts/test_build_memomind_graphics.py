"""Fixed graphics container profile tests; all constructed OTAs stay in memory."""
import copy
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import build_memomind_graphics as g
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"captures/firmware/ota-1.0.3.127-glassly-text.bin"


def synthetic_blob(size=80):
    # Container fixture only, not an executable graphics runtime.
    blob = bytearray(b"\x01\x00"*(size//2))
    if size >= 68:
        blob[64:68] = g.DISPLACED_LOAD
    return bytes(blob)


def signed(value, bits):
    return value-(1 << bits) if value & (1 << (bits-1)) else value


@unittest.skipUnless(SOURCE.exists(), "Exact verified text OTA required")
class GraphicsConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.blob = SOURCE.read_bytes(), synthetic_blob()
        cls.output, cls.manifest, cls.proof = g.construct_graphics(cls.source, cls.blob)
        _, cls.original_streams = unpack_ota(cls.source)

    def test_exact_two_edits_append_and_unchanged_streams(self):
        _, final = unpack_ota(self.output)
        before = self.original_streams[3]["raw"][32:]
        after = final[3]["raw"][32:]
        expected = bytearray(before)
        for hook in self.manifest["hooks"]:
            off = hook["body_offset"]
            self.assertEqual(before[off:off+8], bytes.fromhex(hook["before"]))
            expected[off:off+8] = bytes.fromhex(hook["after"])
            following = bytes.fromhex(hook["following_witness"])
            self.assertEqual(after[off+8:off+8+len(following)], following)
        self.assertEqual(after[:len(before)], expected)
        self.assertEqual(after[len(before):], bytes(8)+self.blob)
        self.assertEqual(after[0x17d710:0x17d710+23], b"Glassly firmware ready\0")
        for i in (1, 2, 4, 5, 6):
            self.assertEqual(final[i]["raw"], self.original_streams[i]["raw"])
            self.assertEqual(final[i]["packed"], self.original_streams[i]["packed"])
        meta_before, meta_after = self.original_streams[0]["raw"], final[0]["raw"]
        self.assertEqual(meta_before[:76], meta_after[:76])
        self.assertEqual(meta_before[80:], meta_after[80:])
        self.assertEqual(struct.unpack_from("<I", meta_after, 76)[0], len(after))

    def test_pc_relative_pair_decodes_registers_destination_and_signed_halves(self):
        cases = [(g.DISPLAY_CALL, g.DISPLAY_GATE), (0x100000, 0x1007fe),
                 (0x100000, 0x100800), (0x100000, 0x0ff800),
                 (0x100000, 0x0ff7fe), (0x100002, 0x100002),
                 (0x80000000, 0), (0, 0x7ffffffe)]
        for pc, target in cases:
            with self.subTest(pc=hex(pc), target=hex(target)):
                auipc, jalr = struct.unpack("<II", g.pc_relative_call(pc, target))
                self.assertEqual(auipc & 0xfff, (1 << 7) | 0x17)
                self.assertEqual(jalr & 0xfffff, (1 << 15) | (1 << 7) | 0x67)
                high, low = signed(auipc & 0xfffff000, 32), signed(jalr >> 20, 12)
                destination = ((pc+high+low) & 0xffffffff) & ~1
                self.assertEqual(destination, target)
        self.assertEqual(g.DISPLAY_CALL+8, g.CONTINUATION)
        for pc, target in [(1, 4), (4, 3), (-2, 4), (0, 0x80000000), (0x80000002, 0)]:
            with self.assertRaises(ValueError):
                g.pc_relative_call(pc, target)

    def test_original_jal_and_initializer_decode_to_proven_stock_targets(self):
        insn = struct.unpack_from("<I", g.DISPLAY_BEFORE, 4)[0]
        self.assertEqual(insn & 0xfff, (1 << 7) | 0x6f)
        immediate = (((insn >> 31) & 1) << 20 | ((insn >> 21) & 0x3ff) << 1 |
                     ((insn >> 20) & 1) << 11 | ((insn >> 12) & 0xff) << 12)
        self.assertEqual(g.DISPLAY_CALL+4+signed(immediate, 21), g.STOCK_DISPLAY)
        for target, encoded in [(g.STOCK_HANDLER, g.INIT_BEFORE),
                                (g.ENTRY, bytes.fromhex(self.manifest["hooks"][0]["after"]))]:
            lui, addi = struct.unpack("<II", encoded)
            self.assertEqual(lui & 0xfff, (15 << 7) | 0x37)
            self.assertEqual(addi & 0xfffff, (15 << 15) | (15 << 7) | 0x13)
            self.assertEqual((lui & 0xfffff000)+signed(addi >> 20, 12), target)

    def test_both_hook_and_following_witness_mismatches_rejected(self):
        body = self.original_streams[3]["raw"][32:]
        for address, extra in [(g.INITIALIZER, 0), (g.INITIALIZER, 8),
                               (g.DISPLAY_CALL, 0), (g.DISPLAY_CALL, 4), (g.DISPLAY_CALL, 8)]:
            modified = bytearray(body)
            modified[address-g.BODY_BASE+extra] ^= 1
            with self.subTest(address=hex(address), extra=extra), self.assertRaisesRegex(ValueError, "witness"):
                g._guard_witnesses(modified)

    def test_overlap_and_range_guards_reject(self):
        g._guard_nonoverlap(20, [(0, 8), (8, 16)])
        for ranges in [[(0, 8), (7, 15)], [(0, 8), (0, 8)], [(-1, 7)], [(18, 26)], [(5, 5)]]:
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                g._guard_nonoverlap(20, ranges)

    def test_blob_length_gate_entry_and_source_hash_rejections(self):
        with self.assertRaisesRegex(ValueError, "exact visually verified"):
            g.construct_graphics(self.source[:-1], self.blob)
        for blob in [b"", bytes(15), bytes(17), bytes(65552), bytes(16), bytes(64), bytes(80)]:
            with self.subTest(size=len(blob)), self.assertRaises(ValueError):
                g.construct_graphics(self.source, blob)
        output, manifest, proof = g.construct_graphics(self.source, synthetic_blob(65536))
        self.assertEqual(manifest["blob_bytes"], 65536)
        self.assertLessEqual(len(output)-18, g.STAGING_CAPACITY)
        self.assertEqual(proof["final_bounds"]["app_headroom"], 258400)

    def test_final_staging_and_app_bounds_enforced_after_recompression(self):
        g._guard_final_bounds(g.STAGING_CAPACITY+18, g.APP_ALLOCATION)
        with self.assertRaisesRegex(ValueError, "staging"):
            g._guard_final_bounds(g.STAGING_CAPACITY+19, g.APP_ALLOCATION)
        with self.assertRaisesRegex(ValueError, "application"):
            g._guard_final_bounds(1000, g.APP_ALLOCATION+1)
        with patch.object(g, "repack", return_value=bytes(g.STAGING_CAPACITY+19)):
            with self.assertRaisesRegex(ValueError, "staging"):
                g.construct_graphics(self.source, self.blob)

    def test_exact_reconstruction_and_manifest_hash_witness_abi_tampering(self):
        self.assertEqual(g.verify_graphics(self.source, self.blob, self.manifest)[0], self.output)
        for key in self.manifest:
            bad = copy.deepcopy(self.manifest); bad[key] = None
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "manifest"):
                g.verify_graphics(self.source, self.blob, bad)
        for which in (0, 1):
            for key in ("before", "after", "body_offset", "address", "target", "following_witness"):
                bad = copy.deepcopy(self.manifest); bad["hooks"][which][key] = "arbitrary"
                with self.subTest(hook=which, key=key), self.assertRaisesRegex(ValueError, "manifest"):
                    g.verify_graphics(self.source, self.blob, bad)
        changed_blob = bytearray(self.blob); changed_blob[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "manifest"):
            g.verify_graphics(self.source, bytes(changed_blob), self.manifest)
        bad = copy.deepcopy(self.manifest); bad["entry_address"] = float(g.ENTRY)
        with self.assertRaisesRegex(ValueError, "manifest"):
            g.verify_graphics(self.source, self.blob, bad)


if __name__ == "__main__":
    unittest.main()
