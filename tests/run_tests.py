#!/usr/bin/env python3
"""Run the offline NIMO CFW suites as numbered stages, in order, and keep the
evidence. Never contacts a device.

  01_container          container parser/repacker (scripts/test_nimo_ota.py)
  02_cfw_string_builds  string-edit manifests rebuilt from captures/firmware
                        (optional: skipped when no stock image is present)
  03_runtime_build      build_runtime.py for --revision into this run's
                        directory: witnesses, hooks, data patches, disassembly
  04_portable_host      portable geometry/RLE/vector/scene suites against the
                        pinned G2 reference
  05_session_host       NIMO runtime adapter, demo scenes and breadcrumbs,
                        stock mocked
  06_rv32_emulator      the 03 blob under Unicorn as strict as the core
                        (RV32IMC, aligned, owned memory only), stock mocked,
                        the hardware step list replayed in order (optional:
                        skipped when the Unicorn venv is absent)

Each stage records passed/failed/skipped, its duration and its logs under
--output (which must not exist). summary.json holds every stage. Exit 0 only
when every required stage passed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "captures/firmware/ota-1.1.5.1-20261027111705-8e6f7a-vendor-app.bin"
SKIPPED = 77


def source_snapshot():
    paths = []
    for base in ("scripts", "runtime", "tests", "patches"):
        for path in (ROOT / base).rglob("*"):
            rel = path.relative_to(ROOT)
            if path.is_file() and path.suffix in (".py", ".c", ".h", ".inc", ".S", ".json") and \
                    not {"build", "__pycache__"} & set(rel.parts):
                paths.append(path)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    parser.add_argument("--revision", type=int, default=9)
    parser.add_argument("--rv32-python", type=Path,
                        default=Path.home() / "dev/glassly-memomind-one-cfw/.tools/rv32-tests-venv/bin/python")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    py = sys.executable
    build = out / "03_runtime_build"
    build_dir = build / "build" / f"glasslycfw-{args.revision}"
    stages = [
        ("01_container", True, "Container parse/repack/replace_body", None,
         [[py, "-I", "scripts/test_nimo_ota.py"]]),
        ("02_cfw_string_builds", False, "String-edit manifests rebuilt from the stock images", None,
         [[py, "-I", "tests/check_cfw_builds.py", "--output", out / "02_cfw_string_builds" / "images"]]),
        ("03_runtime_build", True, f"GLASSLYCFW/{args.revision} runtime image built and checked",
         None if STOCK.is_file() else "skipped: image absent",
         [[py, "-I", "scripts/build_runtime.py", STOCK, str(args.revision), "--out", build / "build",
           "--image", build / f"ota-1.1.5.1-glasslycfw-{args.revision}.bin"]]),
        ("04_portable_host", True, "Portable scene core vs the pinned G2 reference (ASan/UBSan)", None,
         [[py, "-I", "runtime/portable/tests/run_tests.py", "--output", out / "04_portable_host" / "geometry"],
          [py, "-I", "runtime/portable/tests/run_scene_tests.py", "--output", out / "04_portable_host" / "scene"]]),
        ("05_session_host", True, "NIMO adapter, scene session, demo scenes and breadcrumbs (ASan/UBSan)", None,
         [[py, "-I", "runtime/nimo/tests/run_session_tests.py", "--revision", str(args.revision),
           "--output", out / "05_session_host" / "session"]]),
        ("06_rv32_emulator", False, "Linked RV32 blob, gates and hardware steps under a strict Unicorn core",
         None if args.rv32_python.is_file() else "skipped: Unicorn venv absent",
         [[args.rv32_python, "-I", "tests/rv32/runtime_emulator_test.py", "--build", build_dir,
           "--report", out / "06_rv32_emulator" / "report.json"]]),
    ]
    started = datetime.now(timezone.utc).isoformat()
    before = source_snapshot()
    (out / "source-sha256.json").write_text(json.dumps(before, indent=2) + "\n")
    results = {}
    for name, required, scope, skip, commands in stages:
        stage = out / name
        stage.mkdir(exist_ok=True)
        if name == "06_rv32_emulator" and skip is None and results["03_runtime_build"]["result"] != "passed":
            skip = "skipped: 03_runtime_build did not pass"
        row = {"stage": name, "required": required, "scope": scope, "commands": [], "result": "passed"}
        begin = time.monotonic()
        print(f"{name}: {scope}", flush=True)
        if skip:
            row["result"] = skip
        for index, command in enumerate([] if skip else commands):
            command = [str(c) for c in command]
            log = stage / f"{index:02d}"
            try:
                with open(f"{log}.stdout", "wb") as stdout, open(f"{log}.stderr", "wb") as stderr:
                    code = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=900).returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                code, row["error"] = -1, str(error)
            row["commands"].append({"argv": command, "returncode": code, "log": f"{log.name}.stdout/.stderr"})
            if code == SKIPPED and len(commands) == 1:
                row["result"] = "skipped: image absent"
            elif code != 0:
                row["result"] = "failed"
                break
        row["seconds"] = round(time.monotonic() - begin, 3)
        results[name] = row
        print(f"{name}: {row['result']} ({row['seconds']} s)", flush=True)
    after = source_snapshot()
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    passed = all(r["result"] == "passed" for r in results.values() if r["required"]) and not changed
    summary = {"format": "nimo-offline-tests-v1", "revision": args.revision, "started_utc": started,
               "finished_utc": datetime.now(timezone.utc).isoformat(), "stages": list(results.values()),
               "all_required_passed": passed, "sources_changed_during_run": changed,
               "hardware_tested": False, "device_actions": 0}
    if (build_dir / "build.json").is_file():
        report = json.loads((build_dir / "build.json").read_text())
        summary["runtime"] = {k: report[k] for k in ("output_sha256", "runtime_bytes", "runtime_room", "runtime_free")}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{'PASS' if passed else 'FAIL'}: evidence in {out / 'summary.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
