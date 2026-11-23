"""Optional bundle compiler prerequisite guards; no device or compilation."""
from pathlib import Path
import tempfile
import unittest
from compile_memomind_graphics import compile_graphics
class BundleProfileTests(unittest.TestCase):
    def test_all_dependencies_rejected_before_output_creation(self):
        for kwargs,reason in [({'command_bundles':True},'rect-copy'),
                              ({'command_bundles':True,'rect_copy':True},'raster-commands'),
                              ({'command_bundles':True,'rect_copy':True,'raster_commands':True},'scene-session'),
                              ({'command_bundles':True,'rect_copy':True,'raster_commands':True,'scene_session':True,'gate_fixture':True},'separate build profiles')]:
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as folder:
                out=Path(folder)/'none'
                with self.assertRaisesRegex(ValueError,reason):compile_graphics(out,**kwargs)
                self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
