#!/usr/bin/env python3
"""Record reviewed optional-backend edits against original pinned generation.

This maintenance command does not change production or upstream source. Normal
regression only checks the resulting exact overlay; it never refreshes it.
"""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('scene_generator',ROOT/'tests/prepare_scene_port.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base={}
module.emit=lambda path,text:base.__setitem__(path.name,module.native_opt_ins(path,text))
module.main()
result={}
for name in ('scene_internal.h','scene_shapes.inc','scene_cache.inc'):
    original=base[name];current=(ROOT/name).read_text()
    old=original.splitlines(keepends=True);new=current.splitlines(keepends=True)
    hunks=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(a=old,b=new,autojunk=False).get_opcodes():
        if tag!='equal':hunks.append({'start':a,'end':b,'before':old[a:b],'after':new[c:d]})
    result[name]={'base_sha256':hashlib.sha256(original.encode()).hexdigest(),
                  'result_sha256':hashlib.sha256(current.encode()).hexdigest(),'hunks':hunks}
(Path(__file__).parent/'generated-overlay.json').write_text(json.dumps(result,indent=2)+'\n')
