"""Text profile dependency rejection before any build mutations."""
import tempfile,unittest
from pathlib import Path
from compile_memomind_graphics import compile_graphics
class TextProfileTests(unittest.TestCase):
    def test_dependencies(self):
        cases=[({},'command-bundles'),({'command_bundles':True},'rect-copy'),({'command_bundles':True,'rect_copy':True},'raster-commands'),({'command_bundles':True,'rect_copy':True,'raster_commands':True},'scene-session')]
        for flags,reason in cases:
            with self.subTest(flags=flags),tempfile.TemporaryDirectory() as d:
                out=Path(d)/'none'
                with self.assertRaisesRegex(ValueError,reason):compile_graphics(out,text_commands=True,**flags)
                self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
