import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_rebuilt as runner


class RebuiltFixtureTests(unittest.TestCase):
    def test_only_runtime_module_pins_change(self):
        old, new = 'a' * 64, 'b' * 64
        source = f'''SHA = PINNED_SHA = "{old}"
APP_SHA = "{old}"
import types
fixture = types.SimpleNamespace()
if True:
    fixture.SCENE_SHA = "{old}"
def nested():
    SHA = "{old}"
    assert SHA == "{old}"
    return SHA
'''
        bindings, namespace = [], {}
        exec(runner.bind(source, str(runner.DIRECTORY / 'fixture.py'), new, bindings), namespace)
        self.assertEqual(namespace['SHA'], new)
        self.assertEqual(namespace['PINNED_SHA'], new)
        self.assertEqual(namespace['APP_SHA'], old)
        self.assertEqual(namespace['nested'](), old)
        self.assertEqual(namespace['fixture'].SCENE_SHA, new)
        self.assertEqual(len(bindings), 2)
        self.assertEqual(bindings[0]['sourceSHA256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(bindings[0]['historical'], old)

    def test_blob_and_source_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'runtime/graphics/graphics.c'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'source')
            build = root / 'build'
            build.mkdir()
            blob = build / 'graphics.bin'
            blob.write_bytes(b'code')
            digest = hashlib.sha256(blob.read_bytes()).hexdigest()
            manifest = dict(blob_sha256=digest, source_sha256={
                'runtime/graphics/graphics.c': hashlib.sha256(source.read_bytes()).hexdigest()})
            (build / 'build.json').write_text(json.dumps(manifest))
            with patch.object(runner, 'ROOT', root):
                self.assertEqual(runner.verified_build(build), digest)
                blob.write_bytes(b'changed')
                with self.assertRaises(AssertionError):
                    runner.verified_build(build)
                blob.write_bytes(b'code')
                source.write_bytes(b'changed')
                with self.assertRaises(AssertionError):
                    runner.verified_build(build)


if __name__ == '__main__':
    unittest.main()
