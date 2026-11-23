"""Read-only RX96 admission and historical identity review; no device imports/actions."""
import hashlib
import json
from pathlib import Path
import sys
if not __debug__: raise SystemExit('Run without -O')
ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts'))
from memomind_flasher import validate_image
from compile_memomind_graphics import inspect_elf
from memomind_rx_profile import EXTENDED_RX_PROFILE

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
old = json.loads((ROOT/'analysis/regression-20261102-04/source-sha256.json').read_text())
paths = ['scripts/memomind_flasher.py', 'swift/MemoMindKit/Sources/MemoMindCore/FirmwareImage.swift', 'runtime/graphics/graphics.ld']
unchanged = {p: sha(ROOT/p) for p in paths}
assert all(old[p] == h for p,h in unchanged.items())
ld = (ROOT/paths[2]).read_text()
assert (ROOT/'runtime/graphics/graphics_rx96.ld').read_text() == ld.replace('LENGTH = 0x10000', 'LENGTH = 0x18000')
folder = ROOT/'captures/firmware/diagnostic-rx96-001'
image = (folder/'firmware.bin').read_bytes()
manifest = json.loads((folder/'manifest.json').read_text())
source = (ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
blob = (ROOT/'runtime/build/diagnostic-rx96-001/graphics.bin').read_bytes()
assert image == (ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
assert blob == (ROOT/'runtime/build/diagnostic-commands-001/graphics.bin').read_bytes()
assert blob == (ROOT/'runtime/build/diagnostic-rx64-reproduction-001/graphics.bin').read_bytes()
assert manifest['format'].endswith('-rx96') and manifest['live_flashing_enabled'] is False
failures = {}
for name, m in [('original', manifest), ('claimed_live',dict(manifest,live_flashing_enabled=True)), ('claimed_128k',dict(manifest,rx_limit_bytes=131072))]:
 try: validate_image(image,stock_source=source,runtime_manifest=m,runtime_blob=blob)
 except ValueError as e: failures[name]=str(e)
 else: raise AssertionError('Live validator admitted RX96 manifest '+name)
elf = (ROOT/'runtime/build/diagnostic-rx96-001/graphics.elf').read_bytes()
assert inspect_elf(elf)==inspect_elf(elf,rx_profile=EXTENDED_RX_PROFILE)
result=dict(passed=True,device_actions=False,unchanged_from_frozen_regression=unchanged,
 linker_only_length_changed=True,python_live_manifest_rejections=failures,
 historical_runtime_sha256=hashlib.sha256(blob).hexdigest(),historical_ota_sha256=hashlib.sha256(image).hexdigest(),
 caveat='Identical already-catalogued bytes retain existing eligibility; no new RX96 profile or larger image admitted.')
out=Path(__file__).with_name('admission-check.json')
if out.exists(): raise SystemExit('Refuse overwrite')
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
