"""Pin the notification/settings candidate and reuse the independent OTA trace verifier."""
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
image = (ROOT / 'captures/firmware/notifications-settings-001/firmware.bin').read_bytes()
verifier.same(verifier.sha(image), '18959dcd3339667ffa82670843813349dbbc401b809e8c5fc12abcf56f39f719')
trace = (capture / 'trace.jsonl').read_bytes()
result = verifier.loads((capture / 'result.json').read_bytes())
verifier.same(result['releaseName'], 'notifications-settings-001')
report = verifier.verify([verifier.loads(row) for row in trace.splitlines()], image, result)
report.update(trace_sha256=verifier.sha(trace), capture=str(capture),
              verifier_sha256=verifier.sha(source.read_bytes()))
with output.open('x') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
print({key: report[key] for key in ('passed', 'image_sha256', 'reconstructed_bytes', 'blocks', 'chunks')})
