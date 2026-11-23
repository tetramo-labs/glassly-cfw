"""Pin the background candidate and reuse the independent OTA trace verifier."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'analysis/minimal-owner-queue-fix-20261102/verify-ota.py'
spec = importlib.util.spec_from_file_location('ota_verifier', source)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
capture, output = map(Path, sys.argv[1:])
image = (ROOT / 'captures/firmware/wake-background-001/firmware.bin').read_bytes()
verifier.same(verifier.sha(image), '59abc5fa55be310c07886ab05fb713e6847a28632c75ead84cc76203d4d9a6d7')
trace = (capture / 'trace.jsonl').read_bytes()
result = verifier.loads((capture / 'result.json').read_bytes())
verifier.same(result['releaseName'], 'wake-background-001')
report = verifier.verify([verifier.loads(row) for row in trace.splitlines()], image, result)
report.update(trace_sha256=verifier.sha(trace), capture=str(capture),
              verifier_sha256=verifier.sha(source.read_bytes()))
with output.open('x') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
print({key: report[key] for key in ('passed', 'image_sha256', 'reconstructed_bytes', 'blocks', 'chunks')})
