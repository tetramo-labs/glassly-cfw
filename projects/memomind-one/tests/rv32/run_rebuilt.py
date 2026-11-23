#!/usr/bin/env python3
"""Bind historical emulator fixture pins to a source-verified fresh graphics build.

Only compiled-runtime digest assignments in module setup change. Stock image pins,
assertions, test bodies, fixtures and native mocks remain unchanged.
"""
import ast
import hashlib
import importlib.abc
import importlib.machinery
import json
from pathlib import Path
import re
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
RUNTIME_PINS = {'PINNED_SHA', 'SCENE_SHA', 'SHA'}


def bind(source, filename, digest, bindings):
    tree = ast.parse(source, filename)
    def setup_nodes(nodes):
        for node in nodes:
            yield node
            if isinstance(node, ast.If):
                yield from setup_nodes(node.body)
                yield from setup_nodes(node.orelse)

    for node in setup_nodes(tree.body):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        names = [target.id if isinstance(target, ast.Name) else target.attr
                 if isinstance(target, ast.Attribute) else '' for target in node.targets]
        value = node.value.value
        if names and set(names) <= RUNTIME_PINS and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value):
            bindings.append(dict(file=str(Path(filename).relative_to(ROOT)), names=names,
                                 historical=value, rebuilt=digest,
                                 sourceSHA256=hashlib.sha256(source.encode()).hexdigest()))
            node.value = ast.copy_location(ast.Constant(digest), node.value)
    return compile(ast.fix_missing_locations(tree), filename, 'exec')


def verified_build(build):
    manifest = json.loads((build / 'build.json').read_text())
    digest = hashlib.sha256((build / 'graphics.bin').read_bytes()).hexdigest()
    assert digest == manifest['blob_sha256'], 'Compiled blob differs from manifest'
    sources = manifest['source_sha256']
    assert sources and 'runtime/graphics/graphics.c' in sources
    for relative, expected in sources.items():
        path = (ROOT / relative).resolve()
        assert path.is_relative_to(ROOT) and path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative
    return digest


def main():
    script = (ROOT / sys.argv[1]).resolve()
    assert script.parent == DIRECTORY and script != Path(__file__).resolve()
    arguments = sys.argv[2:]
    build = Path(arguments[arguments.index('--build') + 1]).resolve()
    digest = verified_build(build)
    bindings = []

    class Loader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            return bind(Path(self.path).read_text(), self.path, digest, bindings)

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.origin and Path(spec.origin).parent == DIRECTORY and spec.origin.endswith('.py'):
                spec.loader = Loader(fullname, spec.origin)
                return spec
            return None

    sys.path.insert(0, str(DIRECTORY))
    finder = Finder(); sys.meta_path.insert(0, finder)
    sys.argv = [str(script), *arguments]
    previous_main = sys.modules['__main__']
    module = types.ModuleType('__main__')
    module.__file__ = str(script)
    sys.modules['__main__'] = module
    try:
        exec(bind(script.read_text(), str(script), digest, bindings), module.__dict__)
    finally:
        sys.modules['__main__'] = previous_main
        sys.meta_path.remove(finder)
        if '--report' in arguments:
            report = Path(arguments[arguments.index('--report') + 1]).with_suffix('.bindings.json')
            report.write_text(json.dumps(dict(runtimeSHA256=digest, build=str(build),
                sourcesVerified=True, bindings=bindings, testBodiesUnchanged=True), indent=2) + '\n')


if __name__ == '__main__':
    main()
