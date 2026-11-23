#!/usr/bin/env python3
"""Extract unchanged pinned G2 text implementation; no font/device execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('g2_inventory',ROOT/'tests/g2_compat/inventory.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
pin=json.loads((ROOT/'tests/g2_compat/UPSTREAM.json').read_text())
requested={'patches/utils.c':['bzero','rd16'],
 'patches/texture_cache.c':['cfw_texture_make_lut','cfw_texture_render_a4','cfw_texture_add_rect',
 'cfw_texture_utf8','cfw_texture_next_glyph','cfw_texture_s16','cfw_texture_s32',
 'cfw_builtin_glyph','cfw_builtin_draw_string_buf','cfw_builtin_draw_string']}
parts=['/* MIT; exact extracted G2 functions. See reference-manifest.json. */']
rows=[]
for name,functions in requested.items():
 path=ROOT/'tests/g2_compat/upstream'/name
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if digest!=pin['copied_files'][name]:raise RuntimeError('Pinned source changed: '+name)
 for function in functions:
  body,lo,hi=mod.function(path.read_text(),function)
  parts.append(body)
  rows.append({'function':function,'upstream_file':name,'source_sha256':digest,'first_line':lo,'end_line':hi,'function_sha256':hashlib.sha256(body.encode()).hexdigest()})
content='\n\n'.join(parts)+'\n';(OUT/'g2_text_reference.inc').write_text(content)
(OUT/'reference-manifest.json').write_text(json.dumps({'upstream_commit':pin['commit'],'functions':rows,'output_sha256':hashlib.sha256(content.encode()).hexdigest(),'executed':False,'font_api_and_dirty_list_shims_required':True},indent=2)+'\n')
print('Extracted12 original functions; no parser/renderer reimplementation.')
