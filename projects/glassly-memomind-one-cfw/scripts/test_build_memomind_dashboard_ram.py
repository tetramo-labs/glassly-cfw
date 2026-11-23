"""Exact source, gate witnesses and unchanged runtime/container boundaries."""
import copy
from pathlib import Path
import unittest
import build_memomind_dashboard_ram as c
from memomind_ota import unpack_ota

ROOT = Path(__file__).resolve().parents[1]


class DashboardRAM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
        cls.body = unpack_ota(cls.source)[1][3]['raw'][32:]

    def test_instruction_and_byte_boundaries(self):
        body, edits = c.apply_ram_gates(self.body)
        allowed = {i for e in edits for i in range(e['body_offset'], e['body_offset']+4)}
        self.assertEqual(len(allowed), 24)
        self.assertEqual(len(body), len(self.body))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(body, self.body))))
        for row in edits:
            self.assertEqual(row['after'], '01458280')
            changed = bytearray(self.body); changed[row['body_offset']] ^= 1
            with self.assertRaises(ValueError): c.apply_ram_gates(changed)
        with self.assertRaises(ValueError): c.apply_ram_gates(self.body[:100])

    def test_exact_reconstruction_and_manifest(self):
        image, manifest, proof = c.construct_dashboard_ram(self.source)
        self.assertEqual(c.verify_dashboard_ram(self.source, manifest)[0], image)
        self.assertTrue(proof['runtime_unchanged'])
        self.assertEqual(manifest['requested_base_allocations_avoided_bytes'], 1440)
        self.assertIsNone(manifest['measured_heap_saving_bytes'])
        for key, value in [('hardware_validated', True), ('cold_boot_required', False)]:
            bad = copy.deepcopy(manifest); bad[key] = value
            with self.assertRaises(ValueError): c.verify_dashboard_ram(self.source, bad)
        with self.assertRaises(ValueError): c.construct_dashboard_ram(self.source[:-1])


if __name__ == '__main__':
    unittest.main()
