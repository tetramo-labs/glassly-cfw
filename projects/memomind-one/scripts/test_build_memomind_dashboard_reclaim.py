"""Closed renderer ownership, exact OTA reconstruction and admission guards."""
import copy
from pathlib import Path
import unittest

import build_memomind_dashboard_reclaim as c
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]


class DashboardIslands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
        cls.body = unpack_ota(cls.source)[1][3]['raw'][32:]

    def test_full_region_guards_and_fixed_payload_bounds(self):
        baseline, edits = c.apply_renderer_islands(self.body)
        self.assertEqual(sum(e['rx_capacity'] for e in edits), 2746)
        for row in edits:
            entry, size = row['entry'], row['rx_capacity']
            payload = bytes.fromhex('0100') * (size//2)
            body, _ = c.apply_renderer_islands(self.body, {entry: payload})
            self.assertEqual(body[row['rx_start']-c.BODY_BASE:row['rx_end']-c.BODY_BASE], payload)
            self.assertEqual(body[entry-c.BODY_BASE:row['rx_start']-c.BODY_BASE], bytes.fromhex(row['gate']))
            for bad in (bytes(size+2), b'x', bytearray(2)):
                with self.assertRaises(ValueError): c.apply_renderer_islands(self.body, {entry: bad})
            # Witnesses cover both entry and the last retired instruction.
            for address in (entry, row['end']-1):
                changed = bytearray(self.body); changed[address-c.BODY_BASE] ^= 1
                with self.assertRaises(ValueError): c.apply_renderer_islands(changed)
        for wrong in ({0: b''}, {'0x042708e2': b''}, []):
            with self.assertRaises(ValueError): c.apply_renderer_islands(self.body, wrong)
        a, z = c.RENDERERS[0][0]-c.BODY_BASE, c.RENDERERS[-1][1]-c.BODY_BASE
        self.assertEqual(baseline[:a], self.body[:a]); self.assertEqual(baseline[z:], self.body[z:])

    def test_exact_repack_and_manifest_cannot_enable_live_or_widen(self):
        output, manifest, proof = c.construct_dashboard_reclaim(self.source)
        self.assertFalse(manifest['live_flashing_enabled'])
        self.assertFalse(manifest['hardware_validated'])
        self.assertTrue(proof['launcher_descriptor_and_callback_table_unchanged'])
        self.assertEqual(c.verify_dashboard_reclaim(self.source, manifest)[0], output)
        for key, value in [('live_flashing_enabled', True), ('rx_capacity', 100000)]:
            bad = copy.deepcopy(manifest); bad[key] = value
            with self.assertRaises(ValueError): c.verify_dashboard_reclaim(self.source, bad)
        with self.assertRaises(ValueError): c.construct_dashboard_reclaim(self.source[:-1])


if __name__ == '__main__':
    unittest.main()
