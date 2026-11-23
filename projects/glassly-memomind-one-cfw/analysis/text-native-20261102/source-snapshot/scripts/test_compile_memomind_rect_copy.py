"""Optional mode9 compiler dependency guards; no compilation or device access."""
from pathlib import Path
import tempfile
import unittest
from compile_memomind_graphics import compile_graphics

class RectCopyProfileTests(unittest.TestCase):
    def test_requires_raster_and_scene_before_creating_build_directory(self):
        for kwargs,reason in [({'rect_copy':True},'raster-commands'),
                              ({'rect_copy':True,'raster_commands':True},'scene-session'),
                              ({'rect_copy':True,'raster_commands':True,'scene_session':True,'gate_fixture':True},'separate build profiles')]:
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as folder:
                output=Path(folder)/'must-not-exist'
                with self.assertRaisesRegex(ValueError,reason):compile_graphics(output,**kwargs)
                self.assertFalse(output.exists())
if __name__=='__main__':unittest.main()
