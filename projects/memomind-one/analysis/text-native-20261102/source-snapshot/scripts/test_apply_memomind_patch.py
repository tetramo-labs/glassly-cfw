import copy
from pathlib import Path
import unittest

from apply_memomind_patch import apply_patch
from memomind_ota import repack, sha, unpack_ota

STOCK = Path(__file__).resolve().parents[1] / "captures/firmware/ota-1.0.3.127-jhv3_release.bin"


@unittest.skipUnless(STOCK.exists(), "Local captured stock fixture is required")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = STOCK.read_bytes()
        _, cls.streams = unpack_ota(cls.source)
        body = cls.streams[3]["raw"][32:]
        # Deliberately meaningless, in-memory byte edit: never emitted or flashed.
        changed = bytes([body[0] ^ 1]) + body[1:]
        cls.expected = repack(cls.source, {3: changed})
        cls.manifest = {"format": "memomind-body-patch-v1", "source_sha256": sha(cls.source),
                        "output_sha256": sha(cls.expected), "edits": [
                            {"component": 3, "body_sha256": sha(body), "offset": 0,
                             "before": body[:1].hex(), "after": changed[:1].hex(),
                             "reason": "In-memory validation fixture; not executable patch"}]}

    def test_reproducible_and_unchanged_components(self):
        result, report = apply_patch(self.source, self.manifest)
        self.assertEqual(result, self.expected)
        self.assertTrue(report["offline_only"])
        _, streams = unpack_ota(result)
        for i in (0, 1, 2, 4, 5, 6):
            self.assertEqual(streams[i]["packed"], self.streams[i]["packed"])

    def test_wrong_source_output_and_body_hashes(self):
        for location in ("source_sha256", "output_sha256", "body_sha256"):
            with self.subTest(location=location):
                patch = copy.deepcopy(self.manifest)
                target = patch["edits"][0] if location == "body_sha256" else patch
                target[location] = "0" * 64
                with self.assertRaises(ValueError):
                    apply_patch(self.source, patch)

    def test_invalid_edits(self):
        for changes in ({"offset": -1}, {"offset": 99999999}, {"offset": True},
                        {"component": 0}, {"component": True}, {"after": "aa00"},
                        {"after": "xx"}, {"reason": ""}, {"before": "ffff"}):
            with self.subTest(changes=changes):
                patch = copy.deepcopy(self.manifest)
                patch["edits"][0].update(changes)
                with self.assertRaises(ValueError):
                    apply_patch(self.source, patch)

    def test_overlap_rejected_even_if_same_bytes(self):
        patch = copy.deepcopy(self.manifest)
        patch["edits"].append(copy.deepcopy(patch["edits"][0]))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            apply_patch(self.source, patch)

    def test_unknown_keys_empty_edits_and_noop_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["unknown"] = True
        empty = copy.deepcopy(self.manifest)
        empty["edits"] = []
        noop = copy.deepcopy(self.manifest)
        noop["edits"][0]["after"] = noop["edits"][0]["before"]
        for patch in (bad, empty, noop):
            with self.assertRaises(ValueError):
                apply_patch(self.source, patch)


if __name__ == "__main__":
    unittest.main()
