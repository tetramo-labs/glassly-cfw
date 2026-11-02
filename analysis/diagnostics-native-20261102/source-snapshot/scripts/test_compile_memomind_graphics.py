"""Validate strict ELF rejection using the actual RV32 gate fixture build."""
from pathlib import Path
import struct
import unittest

from compile_memomind_graphics import inspect_elf, check_stack_usage, compile_graphics, MAX_BLOB_BYTES

ELF = Path(__file__).resolve().parents[1]/"runtime/build/graphics-gates-003/graphics.elf"


@unittest.skipUnless(ELF.exists(), "Build the actual graphics gate fixture first")
class GraphicsElfChecks(unittest.TestCase):
    def setUp(self):
        self.elf = ELF.read_bytes()

    def test_actual_linked_map_has_only_rx_file_backed_segment(self):
        loads = inspect_elf(self.elf)
        self.assertEqual(len(loads), 1)
        self.assertEqual(loads[0]["virtual_address"], 0x0439bea0)
        self.assertEqual(loads[0]["physical_address"], 0x0439bea0)
        self.assertEqual(loads[0]["file_bytes"], 128)
        self.assertEqual(loads[0]["memory_bytes"], 128)
        self.assertEqual(loads[0]["flags"], "R E")

    def test_architecture_entry_and_float_abi_cannot_be_spoofed(self):
        for offset, fmt, value in [(18, "<H", 40), (24, "<I", 0x0439bee0), (36, "<I", 1)]:
            changed = bytearray(self.elf)
            struct.pack_into(fmt, changed, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                inspect_elf(changed)

    def test_load_segment_write_nobits_and_bounds_rejected(self):
        offset = struct.unpack_from("<I", self.elf, 28)[0]
        for field, value in [(24, 7), (20, 144), (8, 0x0439bec0), (16, 0x8001)]:
            changed = bytearray(self.elf)
            struct.pack_into("<I", changed, offset+field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                inspect_elf(changed)

    def test_writable_nobits_and_relocation_sections_rejected(self):
        offset = struct.unpack_from("<I", self.elf, 32)[0]+40
        for field, value in [(8, 7), (4, 8), (4, 4), (4, 9)]:
            changed = bytearray(self.elf)
            struct.pack_into("<I", changed, offset+field, value)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                inspect_elf(changed)

    def test_only_static_function_frames_at_most_512_bytes(self):
        check_stack_usage(["fixture:1:1:f\t0\tstatic", "fixture:2:1:g\t512\tstatic"])
        for row in ("fixture:1:1:f\t528\tstatic", "fixture:1:1:f\t32\tdynamic,bounded",
                    "fixture:1:1:f\t-1\tstatic", "malformed"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                check_stack_usage([row])

    def test_64k_load_end_boundary_and_one_byte_overflow(self):
        changed = bytearray(self.elf)
        phoff = struct.unpack_from("<I", changed, 28)[0]
        file_offset = struct.unpack_from("<I", changed, phoff+4)[0]
        changed.extend(bytes(file_offset+MAX_BLOB_BYTES+1-len(changed)))
        struct.pack_into("<II", changed, phoff+16, MAX_BLOB_BYTES, MAX_BLOB_BYTES)
        self.assertEqual(inspect_elf(changed)[0]["memory_bytes"], 65536)
        struct.pack_into("<II", changed, phoff+16, MAX_BLOB_BYTES+1, MAX_BLOB_BYTES+1)
        with self.assertRaisesRegex(ValueError, "load segment"):
            inspect_elf(changed)

    def test_raster_commands_require_scene_and_cannot_use_gate_fixture(self):
        with self.assertRaisesRegex(ValueError, "require the scene-session"):
            compile_graphics("unused-no-output", raster_commands=True)
        with self.assertRaisesRegex(ValueError, "separate build profiles"):
            compile_graphics("unused-no-output", gate_fixture=True, scene_session=True, raster_commands=True)

    def test_scene_and_fixture_flags_cannot_be_combined(self):
        with self.assertRaisesRegex(ValueError, "separate build profiles"):
            compile_graphics("unused-no-output", gate_fixture=True, scene_session=True)

    def test_diagnostics_require_complete_text_profile(self):
        with self.assertRaisesRegex(ValueError, "require the text-commands"):
            compile_graphics("unused-no-output", diagnostic_commands=True)
        with self.assertRaisesRegex(ValueError, "require the command-bundles"):
            compile_graphics("unused-no-output", diagnostic_commands=True, text_commands=True)
        with self.assertRaisesRegex(ValueError, "separate build profiles"):
            compile_graphics("unused-no-output", gate_fixture=True, scene_session=True,
                             raster_commands=True, rect_copy=True,
                             command_bundles=True, text_commands=True,
                             diagnostic_commands=True)


if __name__ == "__main__":
    unittest.main()
