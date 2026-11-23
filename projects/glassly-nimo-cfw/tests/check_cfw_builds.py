#!/usr/bin/env python3
"""Rebuild every string-edit manifest under patches/ from its stock image in
captures/firmware and check the result (build_cfw.build verifies the edits,
the other streams and the staging fit). An existing output image there must
match byte for byte. Exits 77 when no stock image is present. Offline only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_cfw  # noqa: E402
import nimo_ota  # noqa: E402

SKIPPED = 77


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Directory for the rebuilt images")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    firmware = ROOT / "captures/firmware"
    rows, failed = [], False
    for path in sorted((ROOT / "patches").glob("*/*.json")):
        manifest = json.loads(path.read_text())
        source = firmware / manifest["source"]["file"]
        row = {"manifest": str(path.relative_to(ROOT)), "source": manifest["source"]["file"]}
        if not source.is_file():
            row["result"] = "skipped: image absent"
        else:
            try:
                image, verification = build_cfw.build(source.read_bytes(), manifest)
                (args.output / manifest["output"]).write_bytes(image)
                existing = firmware / manifest["output"]
                if existing.is_file() and existing.read_bytes() != image:
                    raise ValueError(f"{existing.name} differs from the rebuild")
                row.update(result="passed", output_sha256=verification["output_sha256"],
                           changed_body_bytes=verification["changed_body_bytes"],
                           matches_existing=existing.is_file())
            except ValueError as error:
                row.update(result="failed", error=str(error))
                failed = True
        rows.append(row)
        print(f"{row['manifest']}: {row['result']}")
    (args.output / "report.json").write_text(json.dumps(rows, indent=2) + "\n")
    if failed:
        return 1
    return 0 if any(r["result"] == "passed" for r in rows) else SKIPPED


if __name__ == "__main__":
    raise SystemExit(main())
